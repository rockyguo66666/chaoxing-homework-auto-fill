#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""font_samples.py —— 把本机的手写体候选渲染成对比样张，让人挑一个。

产出：
  00-总览.png        所有候选各写同样一段话，横条并排，先扫一眼
  NN-<名字>.png      每个候选一整页 A4 300dpi，可以放大细看
  候选清单.md        每个候选的字体名、路径、index、覆盖率

用法
----
  python3 list_fonts.py --json fonts.json
  python3 font_samples.py --from-json fonts.json --out 手写体候选/
  python3 font_samples.py --text-file 答案.txt --out 手写体候选/ --limit 6
"""

from __future__ import annotations

import argparse
import random
import sys
from pathlib import Path
from types import SimpleNamespace

from PIL import Image, ImageDraw, ImageFont

import handlib as H
import renderlib as R
from render import page_size, parse_color, JITTERS, render_blocks_to_image

DEMO_TEXT = """1. 简述牛顿第一定律的内容。
答：一切物体总保持匀速直线运动状态或静止状态，直到有外力迫使它改变这种状态为止。
2. 为什么说力是改变物体运动状态的原因？
答：物体不受力时运动状态不变，只有受外力作用才被迫改变，所以力不是维持运动的原因。"""

# 默认短名单：只保留简体（SC），且风格彼此不同
DEFAULT_PICK = [
    ("hanzipen sc", "regular"),
    ("hannotate sc", "regular"),
    ("kaiti sc", "regular"),
    ("xingkai sc", "bold"),
    ("wawati sc", "regular"),
    ("yuppy sc", "regular"),
    ("weibei sc", "bold"),
    ("libian sc", "regular"),
    ("yuanti sc", "regular"),
]

CN = {"hanzipen": "翩翩体", "hannotate": "手札体", "kaiti": "楷体", "xingkai": "行楷",
      "wawati": "娃娃体", "yuppy": "雅痞", "weibei": "魏碑", "libian": "隶变",
      "yuanti": "圆体", "biaukai": "标楷体", "baoli": "报隶", "lingwai": "凌鲑",
      "klee": "Klee", "kai": "楷体(华文)"}

TIP = {
    "hanzipen": "★ 最像学生随手写的字，推荐首选",
    "hannotate": "★ 钢笔手写感，笔画有粗细",
    "kaiti": "★ 端正的学生楷书，但偏「印刷感」",
    "xingkai": "★ 行书，成熟流畅，像大人写的",
    "wawati": "圆胖可爱，偏低龄",
    "yuppy": "设计感潮字，个性强",
    "weibei": "毛笔碑帖味，方笔粗壮",
    "libian": "隶书，蚕头燕尾",
    "yuanti": "圆润无衬线，不太像手写",
    "biaukai": "繁体字形为主",
    "baoli": "隶书，正式",
    "lingwai": "设计体，偏可爱",
}


def pick_from_json(path, limit):
    data = H.read_json(path)
    cands = data.get("candidates", [])
    picked = []
    for key, style in DEFAULT_PICK:
        for c in cands:
            fam = (c.get("family") or "").lower()
            if key in fam and style in (c.get("style") or "").lower():
                if c not in picked:
                    picked.append(c)
                break
    if not picked:
        picked = [c for c in cands if "SC" in (c.get("family") or "")]
    return picked[:limit] if limit else picked


def label_of(c, n):
    fam = c.get("family", "?")
    key = next((k for k in CN if k in fam.lower()), None)
    cn = CN.get(key, c.get("cn") or "")
    tip = TIP.get(key, c.get("why") or "")
    return "%s %s %s" % (cn, fam, c.get("style", "")), tip


def make_strip(c, idx, text_lines, label, tip, out_size=1700):
    size = 50
    line_h = size * 1.65
    head = size * 2.6
    h = int(head + line_h * len(text_lines) + size)
    rng = random.Random(100 + idx)
    paper = R.make_paper(out_size, h, rng, style="paper")
    d = ImageDraw.Draw(paper)
    lab_path, lab_idx = H.content_font()
    lf = ImageFont.truetype(lab_path, 40, index=lab_idx)
    sf = ImageFont.truetype(lab_path, 30, index=lab_idx)
    d.text((28, 22), "%d. %s" % (idx, label), font=lf, fill=(20, 20, 20))
    if tip:
        d.text((28 + int(lf.getlength("%d. %s" % (idx, label))) + 24, 32), tip, font=sf, fill=(170, 60, 60))
    d.line([(24, head - 12), (out_size - 24, head - 12)], fill=(210, 210, 214), width=2)

    ink = Image.new("L", (out_size, h), 0)
    book = R.FontBook(c["path"], index=c.get("index", 0))
    fbc, fbi = H.content_font()
    book.fallback_path, book.fallback_index = fbc, fbi
    book.fallback_covered = R.FontBook._read_cmap(fbc, fbi)
    chars = max(1, int((out_size - 48) / size))
    R.render_blocks(ink, [(ln, 0) for ln in text_lines], book, (28, int(head)), size,
                    line_h, chars, rng, JITTERS["mid"])
    return R.composite(paper, ink, color=R.DEFAULT_INK, alpha=0.92)


def main(argv=None):
    ap = argparse.ArgumentParser(description="生成手写体候选对比样张")
    ap.add_argument("--from-json", default=None, help="list_fonts.py 的输出")
    ap.add_argument("--text", default=None)
    ap.add_argument("--text-file", default=None)
    ap.add_argument("--out", required=True)
    ap.add_argument("--limit", type=int, default=0)
    ap.add_argument("--no-fullpage", action="store_true", help="只出总览，不出一整页")
    ap.add_argument("--dpi", type=int, default=300)
    args = ap.parse_args(argv)

    text = args.text or (Path(args.text_file).read_text(encoding="utf-8") if args.text_file else DEMO_TEXT)
    lines = [l for l in text.split("\n") if l.strip()]

    if args.from_json:
        cands = pick_from_json(args.from_json, args.limit)
    else:
        print("需要 --from-json（先跑 list_fonts.py --json）", file=sys.stderr)
        return 2
    if not cands:
        print("没有候选字体", file=sys.stderr)
        return 2

    out = Path(args.out)
    out.mkdir(parents=True, exist_ok=True)

    strips = []
    manifest = []
    for i, c in enumerate(cands, start=1):
        label, tip = label_of(c, i)
        try:
            strip = make_strip(c, i, lines[:3], label, tip)
        except Exception as e:
            print("  跳过 %s：%s" % (c.get("family"), e), file=sys.stderr)
            continue
        strips.append(strip)
        manifest.append({"no": i, "label": label, "tip": tip, "path": c["path"],
                         "index": c.get("index", 0), "family": c.get("family"),
                         "style": c.get("style"), "coverage": c.get("coverage")})
        print("  [%d] %s" % (i, label))

    if strips:
        W = max(s.width for s in strips)
        Hh = sum(s.height for s in strips) + 90 * (len(strips) - 1) + 120
        sheet = Image.new("RGB", (W, Hh), (236, 236, 238))
        y = 70
        d = ImageDraw.Draw(sheet)
        lab_path, lab_idx = H.content_font()
        hf = ImageFont.truetype(lab_path, 44, index=lab_idx)
        d.text((28, 14), "手写体候选总览（同样一段话，同样排版参数）", font=hf, fill=(30, 30, 30))
        for s in strips:
            sheet.paste(s, (0, y))
            y += s.height + 90
        sheet.save(out / "00-总览.png")
        print("总览：%s" % (out / "00-总览.png"))

    if not args.no_fullpage:
        ns = SimpleNamespace(chars_per_line=28, size=0, line_spacing=1.55, seed=42,
                             fallback_font="auto", paper_style="paper", rules="line",
                             jitter="mid", ink_color="32,32,44", ink_alpha=0.92,
                             title=None, pdf=False, dpi=args.dpi, font_index=0)
        for m in manifest:
            ns.font_index = m["index"]
            ns.title = m["label"]
            fn = out / ("%02d-%s.png" % (m["no"], m["label"].split()[0]))
            try:
                render_blocks_to_image([(l, 0) for l in lines], m["path"], str(fn), ns,
                                       page_size("a4", args.dpi), 200)
                print("  整页：%s" % fn.name)
            except Exception as e:
                print("  整页失败 %s：%s" % (m["label"], e), file=sys.stderr)

    lines_md = ["# 手写体候选清单", "",
                "> 全部来自本机已装字体，简体常用字覆盖率 100%。",
                "> 想用哪个，把这个编号告诉我即可。", "",
                "| # | 字体 | 家族 | 样式 | 特点 | index |", "| --- | --- | --- | --- | --- | --- |"]
    for m in manifest:
        lines_md.append("| %d | %s | %s | %s | %s | %d |" % (
            m["no"], m["label"].split()[0], m["family"], m["style"], m["tip"], m["index"]))
    (out / "候选清单.md").write_text("\n".join(lines_md) + "\n", encoding="utf-8")
    H.write_json(out / "候选清单.json", {"fonts": manifest})
    print("清单：%s" % (out / "候选清单.md"))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
