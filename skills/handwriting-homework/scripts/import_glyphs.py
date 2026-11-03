#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""import_glyphs.py —— 把「外部生成的字图」导进本工具的流水线。

用途：FontDiffuser / zi2zi / 甚至你自己在画图软件里描的字，只要是
「一张图一个字」，都能用这个脚本转成 data/glyphs_mask/ 下的标准掩码，
之后直接 build_font.py 打包——不必关心它是怎么来的。

用法
----
  # 目录里是 明.png 国.png 和.png，白底黑字
  python3 import_glyphs.py --from-dir <生成结果目录> --out <作业目录>/data --source fontdiffuser

  # 黑底白字（很多生成模型的输出是这种）
  python3 import_glyphs.py --from-dir <目录> --out <作业目录>/data --invert

  # 文件名不是字，用清单文件指定顺序（每行一个字，与图片排序后一一对应）
  python3 import_glyphs.py --from-dir <目录> --labels 字表.txt --out <作业目录>/data
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import handlib as H

EXTS = (".png", ".jpg", ".jpeg", ".bmp", ".webp", ".tif", ".tiff")


def char_from_stem(stem):
    m = re.match(r"^u([0-9A-Fa-f]{4,6})(?:_\d+)?$", stem)
    if m:
        return chr(int(m.group(1), 16))
    m = re.match(r"^(.)(?:_\d+)?$", stem, re.UNICODE)
    if m:
        return m.group(1)
    return None


def to_mask(path, size, invert, drop):
    im = Image.open(path)
    if im.mode in ("RGBA", "LA"):
        a = np.asarray(im.convert("RGBA"), dtype=np.float32)[..., 3] / 255.0
        if a.max() > 0.02 and a.min() < 0.98:
            return a > 0.5
    g = np.asarray(im.convert("L"), dtype=np.float32) / 255.0
    if invert:
        g = 1.0 - g
        return g > (1.0 - drop)
    bg = float(np.percentile(g, 90))
    return g < (bg - drop)


def main(argv=None):
    ap = argparse.ArgumentParser(description="导入外部生成的字图")
    ap.add_argument("--from-dir", required=True)
    ap.add_argument("--out", required=True, help="本工具的 data/ 目录")
    ap.add_argument("--labels", default=None, help="字表文件（每行一个字，按文件名排序一一对应）")
    ap.add_argument("--source", default="external", help="来源标记，写进 manifest")
    ap.add_argument("--invert", action="store_true", help="黑底白字")
    ap.add_argument("--drop", type=float, default=0.20)
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--pad", type=float, default=0.06)
    args = ap.parse_args(argv)

    src = Path(args.from_dir)
    if not src.is_dir():
        print("找不到目录 %s" % src, file=sys.stderr)
        return 2
    files = sorted(p for p in src.iterdir() if p.suffix.lower() in EXTS)
    if not files:
        print("%s 里没有图片" % src, file=sys.stderr)
        return 2

    labels = None
    if args.labels:
        labels = H.load_char_file(args.labels)
        if len(labels) < len(files):
            print("字表只有 %d 个字，但有 %d 张图；按较小的数量处理" % (len(labels), len(files)),
                  file=sys.stderr)

    out = Path(args.out)
    (out / "glyphs_mask").mkdir(parents=True, exist_ok=True)
    (out / "glyphs").mkdir(parents=True, exist_ok=True)

    manifest_path = out / "manifest.json"
    manifest = H.read_json(manifest_path) if manifest_path.is_file() else {
        "version": 1, "kind": "handwriting-glyphs", "size": args.size,
        "source": {}, "chars": {}, "order": [], "pages": []}
    manifest.setdefault("chars", {})
    manifest.setdefault("order", [])
    manifest.setdefault("source", {})
    manifest["source"]["imported_%s" % args.source] = str(src)

    ok, skipped = 0, []
    for i, p in enumerate(files):
        ch = labels[i] if labels and i < len(labels) else char_from_stem(p.stem)
        if ch is None:
            skipped.append(p.name)
            continue
        try:
            raw = to_mask(p, args.size, args.invert, args.drop)
            m, good = H.normalize_glyph(raw, size=args.size, pad_ratio=args.pad, min_area=8)
        except Exception as e:
            skipped.append("%s(%s)" % (p.name, e))
            continue
        if not good:
            skipped.append("%s(空图)" % p.name)
            continue
        base_name = ch if (ord(ch) > 127 or ch.isalnum()) else ("u%04X" % ord(ch))
        k = len(manifest["chars"].get(ch, []))
        name = base_name if k == 0 else ("%s_%d" % (base_name, k + 1))
        H.save_mask_png(m, out / "glyphs_mask" / ("%s.png" % name))
        H.mask_to_rgba(m, color=(30, 30, 60)).save(out / "glyphs" / ("%s.png" % name))
        manifest["chars"].setdefault(ch, []).append({
            "file": "glyphs/%s.png" % name, "mask": "glyphs_mask/%s.png" % name,
            "ratio": round(float(m.mean()), 4), "flags": ["imported"], "source": args.source})
        if ch not in manifest["order"]:
            manifest["order"].append(ch)
        ok += 1

    H.write_json(manifest_path, manifest)
    print("导入 %d 个字（来源：%s）→ %s" % (ok, args.source, out / "glyphs_mask"))
    if skipped:
        print("跳过 %d 个：%s" % (len(skipped), ", ".join(skipped[:10])))
    print("注意：这些字不是用户真迹（flags=imported），渲染报告里会算进「非真迹」一类。")
    print("下一步：python3 build_font.py --data %s --out myhandwriting.ttf --verify 30" % out)
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
