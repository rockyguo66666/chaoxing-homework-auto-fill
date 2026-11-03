#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""build_font.py —— 单字位图 → 矢量 → 真正的 .ttf

流程
----
  512 掩码 → 裂缝跟随取轮廓 → RDP 抽稀 → 缩放平移进 em 方框
           → fontTools 组装 glyf/cmap/hmtx/head/hhea/maxp/OS2/name/post → .ttf
再用 Pillow 把刚建好的字反渲染回来，和原图算 IoU 做自检（这一步不能省，
中文码点/cmap 写错的话，字会变成豆腐块，肉眼不一定第一时间发现）。

用法
----
  python3 build_font.py --data data/ --out myhandwriting.ttf
  python3 build_font.py --data data/ --out myhandwriting.ttf --verify 40
"""

from __future__ import annotations

import argparse
import re
import sys
from collections import defaultdict
from pathlib import Path

import numpy as np

import handlib as H


def parse_stem(stem):
    """文件名 → 字。支持 u4E00 / 明 / 明_2 / A / A_2 / u002C。"""
    m = re.match(r"^u([0-9A-Fa-f]{4,6})(?:_\d+)?$", stem)
    if m:
        return chr(int(m.group(1), 16))
    m = re.match(r"^(.)(?:_\d+)?$", stem, flags=re.UNICODE)
    if m:
        return m.group(1)
    return None


def load_glyphs(data_dir, pick="first"):
    mask_dir = Path(data_dir) / "glyphs_mask"
    if not mask_dir.is_dir():
        raise FileNotFoundError("找不到 %s（先跑 preprocess.py）" % mask_dir)
    groups = defaultdict(list)
    for p in sorted(mask_dir.glob("*.png")):
        ch = parse_stem(p.stem)
        if ch is None:
            continue
        groups[ch].append(p)
    glyphs = {}
    for ch, paths in groups.items():
        if pick == "first":
            p = paths[0]
        else:
            # 选「墨量中位数」的那个样本，避免挑到过粗/过细的
            ratios = []
            for q in paths:
                m = H.load_glyph_mask(q)
                ratios.append(m.mean())
            med = float(np.median(ratios))
            p = min(paths, key=lambda q: abs(H.load_glyph_mask(q).mean() - med))
        glyphs[ch] = H.load_glyph_mask(p)
    return glyphs


def verify_font(ttf_path, glyphs, limit=30, rng_seed=0):
    import random
    keys = sorted(glyphs.keys())
    rnd = random.Random(rng_seed)
    if len(keys) > limit:
        keys = rnd.sample(keys, limit)
    rows = []
    for ch in sorted(keys):
        try:
            got, ok = H.rasterize_glyph(ttf_path, ch, 512)
        except Exception as e:
            rows.append((ch, 0.0, "rasterize error: %s" % e))
            continue
        score = H.align_and_iou(glyphs[ch], got) if ok else 0.0
        rows.append((ch, score, "" if score >= 0.75 else "偏低"))
    scores = [r[1] for r in rows]
    return rows, (float(np.mean(scores)) if scores else 0.0)


def main(argv=None):
    ap = argparse.ArgumentParser(description="位图字库 → TTF")
    ap.add_argument("--data", default="data", help="preprocess.py 的输出目录")
    ap.add_argument("--out", default="myhandwriting.ttf")
    ap.add_argument("--family", default="MyHandwriting")
    ap.add_argument("--eps", type=float, default=1.1, help="轮廓抽稀容差（512 尺度下的像素）")
    ap.add_argument("--pick", choices=["first", "median"], default="first")
    ap.add_argument("--verify", type=int, default=0, help="抽 N 个字做反渲染自检")
    ap.add_argument("--report", default=None, help="自检报告写到哪（默认 data/qc/font_report.md）")
    args = ap.parse_args(argv)

    glyphs = load_glyphs(args.data, pick=args.pick)
    if not glyphs:
        print("没有读到任何字形，检查 %s/glyphs_mask" % args.data, file=sys.stderr)
        return 2
    print("读到 %d 个字形" % len(glyphs))

    old = H.outline_glyph
    H.outline_glyph = lambda mask, eps_px=args.eps, min_area_px=10.0: old(mask, eps_px, min_area_px)
    try:
        stats = H.build_ttf(glyphs, args.out, family_name=args.family)
    finally:
        H.outline_glyph = old

    out_path = Path(args.out).resolve()
    print("字体：%s（%.0f KB）" % (out_path, out_path.stat().st_size / 1024.0))

    if args.verify:
        rows, mean = verify_font(args.out, glyphs, limit=args.verify)
        bad = [r for r in rows if r[1] < 0.75]
        print("反渲染自检：抽 %d 字，平均 IoU %.3f，低于 0.75 的有 %d 个" % (len(rows), mean, len(bad)))
        rep = Path(args.report) if args.report else (Path(args.data) / "qc" / "font_report.md")
        lines = ["# 字体自检报告\n",
                 "- 字体：%s" % out_path,
                 "- 字形数：%d（cmap 条目 %d）" % (stats["glyphs"], stats["cmap"]),
                 "- 抽检：%d 字，平均 IoU %.3f" % (len(rows), mean), ""]
        if stats["failed"]:
            lines.append("- 轮廓为空被跳过：%s" % "".join(stats["failed"]))
        if bad:
            lines.append("\n## IoU 偏低的字（轮廓丢细节，或采样本身糊了）\n")
            lines.append("| 字 | IoU | 说明 |")
            lines.append("| --- | --- | --- |")
            for ch, sc, note in bad:
                lines.append("| %s | %.3f | %s |" % (ch, sc, note))
        lines.append("\n> IoU 在 0.85~0.97 属正常：位图取轮廓时本来就会掉一点笔锋。")
        Path(rep).parent.mkdir(parents=True, exist_ok=True)
        Path(rep).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("报告：%s" % rep)

    cmap_chars = set(glyphs.keys()) - set(stats["failed"])
    print("覆盖 %d 个字。渲染时若缺字，render.py 会列出来。" % len(cmap_chars))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
