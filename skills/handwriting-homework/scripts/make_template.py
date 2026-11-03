#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""make_template.py —— 生成「手写采样纸」。

为什么要采样纸：纸上固定了田字格、浅灰字模和四角黑块。
  * 田字格 + 浅灰字模 → 你不用想「下一格写什么」，照着描就行，字迹更匀。
  * 四角黑块 → 拍照后可以自动做透视校正，格子位置在数学上是已知的，
    切字不用靠猜（这是整条链子最稳的一环）。
  * manifest.json → 记录每一格的坐标和对应的字，和照片一一对应。

用法
----
  # 只写作业里真正用到的那批字（推荐，保真度最高、写字最少）
  python3 make_template.py --from-text 作业.txt --out 采样/

  # 写一套固定常用字（想以后随便写什么都像你的字）
  python3 make_template.py --chars-file ../assets/常用部件表.txt --out 采样/

  # 直接给字
  python3 make_template.py --chars "明国和好" --out 采样/
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

import handlib as H

A4 = {72: (595, 842), 150: (1240, 1754), 200: (1654, 2339), 300: (2480, 3508)}

MARKER_REL = [(0.040, 0.022), (0.960, 0.022), (0.960, 0.978), (0.040, 0.978)]


def page_size(dpi):
    if dpi in A4:
        return A4[dpi]
    w = int(round(8.268 * dpi)); h = int(round(11.693 * dpi))
    return w, h


def build_pages(chars, cols, rows_per_page):
    per = cols * rows_per_page
    pages = []
    for i in range(0, len(chars), per):
        chunk = chars[i:i + per]
        grid = []
        for r in range(rows_per_page):
            row = chunk[r * cols:(r + 1) * cols]
            if not row:
                break
            grid.append(row)
        pages.append(grid)
    return pages or [[]]


def render_page(grid, page_no, total_pages, args, guide_font_path, guide_index, head_font_path, head_index):
    W, H = page_size(args.dpi)
    img = Image.new("RGB", (W, H), (255, 255, 255))
    d = ImageDraw.Draw(img)

    cell = args.cell
    ncols = args.cols
    grid_w = ncols * cell
    grid_h = len(grid) * cell
    x0 = (W - grid_w) // 2
    y0 = (H - grid_h) // 2 + args.grid_shift
    if y0 < args.top_margin:
        y0 = args.top_margin
    # 表头必须完整落在网格上方：曾经把说明文字压在网格第一行上，
    # 结果那几行字被当成「笔迹」，第一行所有格子的字全废。别删这段。
    head_block = args.head_size * 3.0
    head_top = y0 - head_block
    if head_top < 60:
        head_top = 60
        y0 = max(y0, head_top + head_block + 30)
    assert head_top + head_block <= y0, "表头与网格重叠"

    # ---- 四角定位块（实心黑，预处理靠它做透视校正）----
    m = args.marker
    marker_pts = []
    for rx, ry in MARKER_REL:
        cx, cy = rx * W, ry * H
        d.rectangle([cx - m / 2, cy - m / 2, cx + m / 2, cy + m / 2], fill=(0, 0, 0))
        marker_pts.append([float(cx), float(cy)])

    # ---- 表头 ----
    head = ImageFont.truetype(head_font_path, args.head_size, index=head_index)
    title = args.title or "手写采样纸"
    d.text((x0, head_top), "%s  第 %d/%d 页" % (title, page_no, total_pages),
           font=head, fill=(40, 40, 40))
    d.text((x0 + grid_w - args.head_size * 9.5, head_top),
           "姓名：________  日期：____", font=head, fill=(90, 90, 90))
    tip = "说明：格中浅灰字是模板，请用你平时的笔照写；整页拍全（四角黑块必须入镜），光线均匀、别开闪光灯。"
    d.text((x0, head_top + args.head_size * 1.55), tip, font=head, fill=(150, 150, 150))

    # ---- 格子 ----
    guide = ImageFont.truetype(guide_font_path, int(cell * 0.78), index=guide_index)
    # 这两个灰度很关键：必须比二值化阈值（约 0.75 灰）浅得多，否则拍照模糊后
    # 格线会变成「墨」，切字时把整格撑满，字就废了。实测 234/224 有 0.10+ 的安全余量。
    gcol = (234, 234, 238)     # 浅灰字模
    lcol = (224, 228, 234)     # 田字格线
    cells = []
    for r, row in enumerate(grid):
        for c, ch in enumerate(row):
            cx0 = x0 + c * cell
            cy0 = y0 + r * cell
            cx1 = cx0 + cell
            cy1 = cy0 + cell
            d.rectangle([cx0 + 1, cy0 + 1, cx1 - 2, cy1 - 2], outline=lcol, width=2)
            d.line([(cx0 + cell // 2, cy0 + 1), (cx0 + cell // 2, cy1 - 2)], fill=lcol, width=1)
            d.line([(cx0 + 1, cy0 + cell // 2), (cx1 - 2, cy0 + cell // 2)], fill=lcol, width=1)
            bbox = guide.getbbox(ch)
            gw = bbox[2] - bbox[0]
            gh = bbox[3] - bbox[1]
            gx = cx0 + (cell - gw) / 2 - bbox[0]
            gy = cy0 + (cell - gh) / 2 - bbox[1]
            d.text((gx, gy), ch, font=guide, fill=gcol)
            cells.append({"char": ch, "box": [cx0, cy0, cx1, cy1], "row": r, "col": c})
    return img, cells, marker_pts


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成手写采样纸")
    src = ap.add_mutually_exclusive_group(required=True)
    src.add_argument("--chars", help="直接给一串字，例如 明国和好")
    src.add_argument("--from-text", help="从文本（比如作业答案）里提取用到的全部字")
    src.add_argument("--chars-file", help="字符表文件，每行若干字")
    ap.add_argument("--out", required=True, help="输出目录")
    ap.add_argument("--cols", type=int, default=8)
    ap.add_argument("--rows", type=int, default=10)
    ap.add_argument("--cell", type=int, default=240)
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--marker", type=int, default=96, help="四角定位块边长(px)")
    ap.add_argument("--title", default=None)
    ap.add_argument("--head-size", type=int, default=34)
    ap.add_argument("--top-margin", type=int, default=380)
    ap.add_argument("--grid-shift", type=int, default=0)
    ap.add_argument("--limit", type=int, default=0, help="只取前 N 个字（调试用）")
    ap.add_argument("--ascii", action="store_true", help="保留英文数字标点（默认保留）")
    args = ap.parse_args(argv)

    if args.chars:
        chars = H.unique_chars(args.chars)
    elif args.from_text:
        text = Path(args.from_text).read_text(encoding="utf-8")
        chars = H.unique_chars(text)
    else:
        chars = H.load_char_file(args.chars_file)
    if args.limit:
        chars = chars[:args.limit]
    if not chars:
        print("没有可写的字，检查输入", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    guide_path, guide_index = H.content_font()
    head_path, head_index = H.content_font()

    pages = build_pages(chars, args.cols, args.rows)
    manifest = {
        "version": 1,
        "kind": "handwriting-sample-template",
        "dpi": args.dpi,
        "page_size": list(page_size(args.dpi)),
        "cell": args.cell,
        "marker": args.marker,
        "marker_order": "TL,TR,BR,BL",
        "marker_rel": MARKER_REL,
        "chars": chars,
        "pages": [],
        "files": [],
    }
    for i, grid in enumerate(pages, start=1):
        img, cells, marker_pts = render_page(grid, i, len(pages), args, guide_path, guide_index,
                                             head_path, head_index)
        fname = "template_p%02d.png" % i
        img.save(out / fname)
        manifest["pages"].append({"page": i, "file": fname, "markers": marker_pts, "cells": cells})
        manifest["files"].append(fname)

    H.write_json(out / "manifest.json", manifest)
    total_cells = sum(len(p["cells"]) for p in manifest["pages"])
    print("采样纸已生成：%s" % out)
    print("  共 %d 个字，%d 页，每页 %d 格（%d×%d）" % (len(chars), len(pages), args.cols * args.rows, args.cols, args.rows))
    print("  格数 %d（多余格留空即可）" % total_cells)
    print("  清单：%s" % (out / "manifest.json"))
    print()
    print("接下来：打印 → 用平时的笔逐格照写 → 整页拍照（四角黑块入镜、光线均匀、别开闪光灯）")
    print("          → python3 preprocess.py --photo 照片.jpg --template %s" % (out / "manifest.json"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
