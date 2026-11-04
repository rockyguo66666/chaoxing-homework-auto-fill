#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""answer_sheet.py —— 简答题作业：题目+答案 → 一张手写答题纸图片。

输入格式（宽松，下面几种都认）
----------------------------
  1. 简述牛顿第一定律。
  答：一切物体总保持匀速直线运动状态或静止状态，直到有外力迫使它改变这种状态为止。

  2、什么是惯性？
  答：物体保持原有运动状态不变的性质叫惯性。

也支持只有答案的编号段落。

用法
----
  # 用预设（推荐，一套字体+排版手感）
  python3 answer_sheet.py --preset 娃娃体 --qa 作业.txt --out 答题.png --report 报告.md
  python3 answer_sheet.py --list-presets

  # 用你自己生成的字体
  python3 answer_sheet.py --qa 作业.txt --font 作业目录/myhandwriting.ttf --out 答题.png

  # 命令行参数会覆盖预设里的同名项
  python3 answer_sheet.py --preset 娃娃体 --qa 作业.txt --out 答题.png --rules none --jitter high
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PIL import Image

import handlib as H
import renderlib as R
from render import page_size, JITTERS, render_blocks_to_image

# 预设/命令行都没有时用的兜底值
DEFAULTS = {
    "font": None, "font_index": 0, "chars_per_line": 28, "line_spacing": 1.55,
    "rules": "none", "jitter": "mid", "paper_style": "paper",
    "ink_color": "32,32,44", "ink_alpha": 0.92,
}
PRESET_KEYS = ["chars_per_line", "line_spacing", "rules", "jitter", "paper_style",
               "ink_color", "ink_alpha", "font_index"]


def build_blocks(items, indent, with_question, answer_prefix):
    blocks = []
    for it in items:
        if with_question and it.get("question"):
            blocks.append(("%s. %s" % (it["no"], it["question"]), 0))
        ans = (it.get("answer") or "").strip()
        if not ans:
            continue
        body = (answer_prefix + ans) if (answer_prefix and with_question) else ans
        # 按源文件的换行拆块：一行一步，段落之间留空行（不要挤成一段）
        for ln in body.split(chr(10)):
            blocks.append((ln.strip(), indent))
        blocks.append(("", 0))
    return blocks


def main(argv=None):
    ap = argparse.ArgumentParser(description="简答题作业 → 手写答题纸")
    src = ap.add_mutually_exclusive_group()
    src.add_argument("--qa", help="题目+答案的文本文件")
    src.add_argument("--qa-text", help="直接给文本")
    ap.add_argument("--preset", default=None, help="字体预设名（见 --list-presets）")
    ap.add_argument("--list-presets", action="store_true", help="列出可用预设后退出")
    ap.add_argument("--base-dir", default=".", help="预设里 ttf 相对谁的路径（默认当前目录）")
    ap.add_argument("--font", default=None, help="字体文件；给了它就忽略预设里的字体")
    ap.add_argument("--font-index", type=int, default=None, help=".ttc 字体集合的下标")
    ap.add_argument("--out", default=None)
    ap.add_argument("--title", default=None)
    ap.add_argument("--with-question", action="store_true", help="把题干也写上去（默认只写答案）")
    ap.add_argument("--answer-prefix", default="答：")
    ap.add_argument("--indent", type=int, default=2, help="答案缩进几个字")
    ap.add_argument("--chars-per-line", type=int, default=None)
    ap.add_argument("--line-spacing", type=float, default=None)
    ap.add_argument("--paper", default="a4")
    ap.add_argument("--dpi", type=int, default=300)
    ap.add_argument("--margin", type=int, default=200)
    ap.add_argument("--size", type=int, default=0)
    ap.add_argument("--paper-style", default=None, choices=[None, "paper", "white", "scan"])
    ap.add_argument("--rules", default=None, choices=[None, "none", "line", "grid"])
    ap.add_argument("--jitter", default=None, choices=[None] + list(JITTERS.keys()))
    ap.add_argument("--ink-color", default=None)
    ap.add_argument("--ink-alpha", type=float, default=None)
    ap.add_argument("--fallback-font", default="auto")
    ap.add_argument("--composed", default=None)
    ap.add_argument("--seed", type=int, default=42)
    ap.add_argument("--pdf", action="store_true")
    ap.add_argument("--report", default=None, help="把报告写到这里（markdown）")
    args = ap.parse_args(argv)

    if args.list_presets:
        print(R.describe_presets())
        return 0

    if not args.qa and not args.qa_text:
        print("要给 --qa 文件或 --qa-text 文本", file=sys.stderr)
        return 2
    if not args.out:
        print("要给 --out 输出路径", file=sys.stderr)
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

    for k, v in DEFAULTS.items():
        if getattr(args, k, None) is None:
            setattr(args, k, v)
    args.font_index = args.font_index or 0

    text = args.qa_text if args.qa_text is not None else Path(args.qa).read_text(encoding="utf-8")
    items = R.parse_qa(text, keep_lines=True)
    if not items:
        print("没解析出任何题目，检查一下输入格式", file=sys.stderr)
        return 2
    blocks = build_blocks(items, args.indent, args.with_question, args.answer_prefix)

    composed = set()
    if args.composed and Path(args.composed).is_file():
        composed = set(H.read_json(args.composed).get("order", []))

    rep = render_blocks_to_image(blocks, args.font, args.out, args,
                                 page_size(args.paper, args.dpi), args.margin, composed=composed)
    w, h = Image.open(rep["out"]).size
    used = spec.get("label") or Path(args.font).name
    print("已输出 %s（%d×%d，%d 题）" % (rep["out"], w, h, len(items)))
    print("  字体：%s%s" % (used, "（预设 %s）" % args.preset if args.preset else ""))
    print("  真迹字 %d，楷体顶替 %d，缺字 %d" %
          (rep["hand"], rep["fallback"], rep["missing"]))
    if not spec.get("ttf") and args.preset:
        print("  ⚠ 这是「%s」这个字体的字，不是用户本人的字迹。" % used)
    if rep.get("composed_chars"):
        print("  ⚠ 部件拼接（非真迹）的字：%s" % rep["composed_chars"])
    if rep["missing_chars"]:
        print("  ⚠ 字库缺失且未兜底：%s" % rep["missing_chars"])

    if args.report:
        lines = ["# 渲染报告\n",
                 "- 输出：%s" % rep["out"],
                 "- 尺寸：%d×%d @%ddpi" % (w, h, args.dpi),
                 "- 字体：%s%s" % (used, "（预设 %s）" % args.preset if args.preset else ""),
                 "- 题目数：%d" % len(items),
                 "- 真迹字：%d" % rep["hand"],
                 "- 非真迹（预设字体或楷体顶替）：%d" % rep["fallback"],
                 "- 完全缺失：%d" % rep["missing"]]
        if rep.get("composed_chars"):
            lines.append("- 部件拼接（非真迹）：%s" % rep["composed_chars"])
        if rep["missing_chars"]:
            lines.append("- 缺失字：%s" % rep["missing_chars"])
        lines.append("\n> 说明：本图使用现成字体渲染，不是用户本人的字迹。" if spec.get("font_file")
                     else "\n> 说明：本图使用从用户手写采样生成的字库渲染。")
        Path(args.report).write_text("\n".join(lines) + "\n", encoding="utf-8")
        print("  报告：%s" % args.report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
