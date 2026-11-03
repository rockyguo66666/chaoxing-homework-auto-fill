#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""render.py —— 把任意文字用你的手写体渲染成图片。

特性
----
* 逐字抖动（旋转/位移/字号/字距微随机）——人写字天然不齐，全对齐反而假。
* 纸感底纹（米黄/白/扫描件），可选横线、田字格。
* 缺字如实报告：字库里没有的字会用楷体顶替，并明确列出是哪几个。

用法
----
  python3 render.py --text "今天天气很好" --font myhandwriting.ttf --out out.png
  python3 render.py --text-file 段落.txt --font myhandwriting.ttf --out out.png \
      --paper a4 --dpi 300 --chars-per-line 28 --rules line --jitter mid
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import handlib as H
import renderlib as R

PAPERS = {72: (595, 842), 150: (1240, 1754), 200: (1654, 2339), 300: (2480, 3508)}
PRESET_KEYS = ["chars_per_line", "line_spacing", "rules", "jitter", "paper_style",
               "ink_color", "ink_alpha", "font_index"]

JITTERS = {
    "none": {"rot": 0, "dx": 0, "dy": 0, "size": 0, "kern": 0},
    "low": {"rot": 0.8, "dx": 0.018, "dy": 0.014, "size": 0.010, "kern": 0.010},
    "mid": dict(R.DEFAULT_JITTER),
    "high": {"rot": 2.6, "dx": 0.055, "dy": 0.045, "size": 0.035, "kern": 0.030},
}


def page_size(spec, dpi):
    spec = (spec or "a4").lower()
    if spec in ("a4", "auto", ""):
        return PAPERS.get(dpi, (int(round(8.268 * dpi)), int(round(11.693 * dpi))))
    if spec == "letter":
        return (int(round(8.5 * dpi)), int(round(11.0 * dpi)))
    if "x" in spec:
        w, h = spec.split("x")
        return (int(w), int(h))
    raise ValueError("不认识的纸张：%s" % spec)


def parse_color(s):
    if not s:
        return R.DEFAULT_INK
    parts = [int(float(x)) for x in s.replace(" ", "").split(",")]
    if len(parts) != 3:
        raise ValueError("颜色要写成 r,g,b")
    return tuple(parts)


def render_blocks_to_image(blocks, font_path, out_path, args, page_size_px, margin,
                           size_pt=None, dpi_factor=None, composed=None):
    W, Hh = page_size_px
    content_w = W - 2 * margin
    content_h = Hh - 2 * margin
    chars_per_line = args.chars_per_line
    if args.size and args.size > 0:
        size = int(args.size)
    else:
        size = int(round(content_w / float(max(4, chars_per_line))))
    line_height = size * args.line_spacing
    rng = random.Random(args.seed)

    fb_path = None
    fb_index = 0
    if args.fallback_font != "none":
        if args.fallback_font == "auto":
            try:
                fb_path, fb_index = H.content_font()
            except Exception:
                fb_path = None
        else:
            fb_path, fb_index = args.fallback_font, 0

    book = R.FontBook(font_path, index=getattr(args, "font_index", 0),
                      fallback_path=fb_path, fallback_index=fb_index)
    paper = R.make_paper(W, Hh, rng, style=args.paper_style)
    ink = Image.new("L", (W, Hh), 0)
    jitter = JITTERS.get(args.jitter, R.DEFAULT_JITTER)

    origin = (margin, margin)
    if args.title:
        tblocks = [(args.title, 0), ("", 0)]
        blocks = tblocks + blocks
    stats = R.render_blocks(ink, blocks, book, origin, size, line_height,
                            chars_per_line, rng, jitter,
                            use_fallback=(args.fallback_font != "none"))

    if args.rules != "none":
        paper = R.draw_rules(paper, (margin, margin, W - margin, Hh - margin),
                             line_height, style=args.rules, rng=rng, line_y0=margin)

    img = R.composite(paper, ink, color=parse_color(args.ink_color), alpha=args.ink_alpha)
    out_path = Path(out_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    img.save(out_path)
    if args.pdf:
        img.save(out_path.with_suffix(".pdf"), "PDF", resolution=args.dpi)

    report = {"out": str(out_path), "size_px": size, "line_height": line_height,
              "lines": stats["lines"], "hand": stats["hand"],
              "fallback": stats["fallback"], "missing": stats["missing"],
              "missing_chars": stats["missing_chars"]}
    if composed:
        used = set()
        for blk, _indent in blocks:
            used.update(ch for ch in blk if ch in composed)
        report["composed_chars"] = "".join(sorted(used))
    return report


def main(argv=None):
    ap = argparse.ArgumentParser(description="手写体渲染")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--text")
    src.add_argument("--text-file")
    ap.add_argument("--preset", default=None, help="字体预设名（见 --list-presets）")
    ap.add_argument("--list-presets", action="store_true")
    ap.add_argument("--base-dir", default=".", help="预设里 ttf 相对谁的路径")
    ap.add_argument("--font", default=None, help="字体文件（你的 ttf，或系统 .ttc/.otf）")
    ap.add_argument("--font-index", type=int, default=None,
                    help=".ttc 字体集合的下标（楷体等需要指定，见 list_fonts.py）")
    ap.add_argument("--out", default=None)
    ap.add_argument("--paper", default="a4")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--margin", type=int, default=200)
    ap.add_argument("--chars-per-line", type=int, default=None)
    ap.add_argument("--line-spacing", type=float, default=None)
    ap.add_argument("--size", type=int, default=0, help="字号(px@dpi)，0=按每行字数自动")
    ap.add_argument("--paper-style", default=None, choices=[None, "paper", "white", "scan"])
    ap.add_argument("--rules", default=None, choices=[None, "none", "line", "grid"])
    ap.add_argument("--jitter", default=None, choices=[None] + list(JITTERS.keys()))
    ap.add_argument("--ink-color", default=None)
    ap.add_argument("--ink-alpha", default=None)
    ap.add_argument("--fallback-font", default="auto", help="auto=用楷体顶替缺字；none=缺字留白")
    ap.add_argument("--composed", default=None, help="compose.py 产出的 composed.json")
    ap.add_argument("--title", default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--pdf", action="store_true")
    args = ap.parse_args(argv)

    if args.list_presets:
        print(R.describe_presets())
        return 0
    if not args.out:
        print("要给 --out", file=sys.stderr)
        return 2

    spec = {}
    if args.preset:
        try:
            spec = R.apply_preset(args, args.preset, PRESET_KEYS, base_dir=args.base_dir)
        except Exception as e:
            print("预设出错：%s" % e, file=sys.stderr)
            return 2
    elif args.font is None:
        print("要么给 --preset，要么给 --font。\n\n%s" % R.describe_presets(), file=sys.stderr)
        return 2
    for k, v in {"font_index": 0, "chars_per_line": 28, "line_spacing": 1.55,
                 "paper_style": "paper", "rules": "none", "jitter": "mid",
                 "ink_color": "32,32,44", "ink_alpha": 0.92}.items():
        if getattr(args, k, None) is None:
            setattr(args, k, v)
    args.font_index = args.font_index or 0

    text = args.text if args.text is not None else Path(args.text_file).read_text(encoding="utf-8")
    blocks = [(line, 0) for line in text.split("\n")]
    composed = set()
    if args.composed and Path(args.composed).is_file():
        composed = set(H.read_json(args.composed).get("order", []))
    rep = render_blocks_to_image(blocks, args.font, args.out, args, page_size(args.paper, args.dpi),
                                 args.margin, composed=composed)
    print("已输出 %s（%d×%d）" % (rep["out"], *Image.open(rep["out"]).size))
    print("  字号 %dpx，行数 %d，真迹字 %d，楷体顶替 %d" %
          (rep["size_px"], rep["lines"], rep["hand"], rep["fallback"]))
    if rep["missing_chars"]:
        print("  字库缺失且无兜底：%s" % rep["missing_chars"])
    if rep.get("composed_chars"):
        print("  其中「部件拼接」的字（非真迹）：%s" % rep["composed_chars"])
    if rep["fallback"]:
        print("  ⚠ 有 %d 个字是楷体顶替，要更真就得把这几个字补写进采样纸。" % rep["fallback"])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
