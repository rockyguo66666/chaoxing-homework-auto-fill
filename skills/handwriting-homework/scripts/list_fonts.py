#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""list_fonts.py —— 列出本机可用的中文字体，并把手写体候选挑出来。

为什么要用它：macOS 的中文字体散落在 /System/Library/Fonts、
/System/Library/Fonts/Supplemental、/Library/Fonts、~/Library/Fonts，以及
/System/Library/AssetsV2/com_apple_MobileAsset_Font*（按需下载的字体藏在这里）。
.ttc 是字体集合，同一个文件里可能有 8 个不同字重的脸，用错了就是另一种字。

覆盖率的判定用 fontTools 读真实 cmap。**不要用 PIL 的 getmask 判断**——
缺字时它会返回 .notdef 的方框，看起来"有字形"，实际渲染出来是豆腐块。

用法
----
  python3 list_fonts.py                      # 手写/书法候选 + 覆盖率
  python3 list_fonts.py --all                # 连黑体宋体一起列
  python3 list_fonts.py --json out.json      # 给 font_samples.py 用
"""

from __future__ import annotations

import argparse
import glob
import json
import logging
import os
import warnings
from pathlib import Path

warnings.filterwarnings("ignore")
logging.getLogger("fontTools").setLevel(logging.ERROR)

# 已知的手写 / 书法 / 学生感字体（家族名关键词，命中即算候选）
HANDWRITING_HINTS = [
    ("hanzipen", "翩翩体", "像学生随手写的圆珠笔字，圆润、笔画独立，最接近日常作业"),
    ("hannotate", "手札体", "手写感强，笔画有粗细变化，像用钢笔写的"),
    ("xingkai", "行楷", "行书偏楷，成熟流畅，像练过字的大人写的"),
    ("kaiti", "楷体", "标准学生正楷，端正，但偏「印刷感」，是老师最熟的字形"),
    ("stkaiti", "华文楷体", "楷体的另一个版本"),
    ("biaukai", "标楷体", "繁体字形为主，简体覆盖不全"),
    ("weibei", "魏碑", "书法味重，方笔粗壮，像毛笔碑帖"),
    ("baoli", "报隶", "隶书，蚕头燕尾，正式但不像学生字"),
    ("libian", "隶变", "隶书变体，比报隶现代一点"),
    ("yuppy", "雅痞", "设计感的手写潮字，个性强"),
    ("wawati", "娃娃体", "圆胖可爱，低龄感"),
    ("yuanti", "圆体", "圆润无衬线，不像手写但很柔"),
    ("klee", "Klee", "日文教科书体，有手写骨架，个别字形是日式写法"),
    ("lingwai", "凌鲑", "设计体，偏可爱"),
    ("xiaolai", "小赖字体", "第三方开源手写体（需自行安装）"),
    ("lxgw", "霞鹜文楷", "第三方开源楷体（需自行安装）"),
    ("yozai", "悠哉字体", "第三方开源手写体（需自行安装）"),
]


def gb2312_level1():
    out = []
    for hi in range(0xB0, 0xF8):
        for lo in range(0xA1, 0xFF):
            try:
                out.append(bytes([hi, lo]).decode("gb2312"))
            except Exception:
                pass
    return list(dict.fromkeys(out))


def font_paths():
    pats = []
    for root in ["/System/Library/Fonts", "/System/Library/Fonts/Supplemental",
                 "/Library/Fonts", os.path.expanduser("~/Library/Fonts")]:
        pats += [os.path.join(root, "**", "*.ttf"), os.path.join(root, "**", "*.ttc"),
                 os.path.join(root, "**", "*.otf")]
    pats += ["/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*/AssetData/*.ttf",
             "/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*/AssetData/*.ttc",
             "/System/Library/AssetsV2/com_apple_MobileAsset_Font*/*/AssetData/*.otf"]
    seen, out = set(), []
    for pat in pats:
        for p in glob.glob(pat, recursive=True):
            rp = os.path.realpath(p)
            if rp in seen:
                continue
            seen.add(rp)
            out.append(p)
    return sorted(out)


def face_info(path, index, sample):
    """返回 (family, style, coverage)。"""
    from fontTools.ttLib import TTFont
    try:
        f = TTFont(path, fontNumber=index, lazy=True)
    except Exception:
        return None
    try:
        cmap = set()
        for t in f["cmap"].tables:
            cmap.update(t.cmap.keys())
        name = f["name"]
        def get(nid):
            for rec in name.names:
                if rec.nameID == nid:
                    try:
                        v = rec.toUnicode()
                    except Exception:
                        continue
                    if v:
                        return v
            return "?"
        fam = get(1)
        sty = get(2)
        cov = sum(1 for ch in sample if ord(ch) in cmap)
        return fam, sty, cov, len(cmap)
    finally:
        try:
            f.close()
        except Exception:
            pass


def main(argv=None):
    ap = argparse.ArgumentParser(description="列出本机中文字体 / 手写体候选")
    ap.add_argument("--all", action="store_true", help="列出全部中文字体（不只手写候选）")
    ap.add_argument("--min-coverage", type=float, default=0.95, help="GB2312 一级字覆盖率下限")
    ap.add_argument("--json", default=None, help="把结果写成 JSON")
    args = ap.parse_args(argv)

    sample = gb2312_level1()
    rows = []
    for p in font_paths():
        n_face = 12 if p.lower().endswith(".ttc") else 1
        for idx in range(n_face):
            info = face_info(p, idx, sample)
            if info is None:
                break
            fam, sty, cov, total = info
            if total < 500:
                continue
            rows.append({"family": fam, "style": sty, "path": p, "index": idx,
                         "coverage": cov / float(len(sample)), "codepoints": total})
            if not p.lower().endswith(".ttc"):
                break

    def hint_of(family):
        low = (family or "").lower().replace(" ", "")
        for key, cn, why in HANDWRITING_HINTS:
            if key in low:
                return cn, why
        return None, None

    cands, others = [], []
    for r in rows:
        cn, why = hint_of(r["family"])
        r["cn"] = cn
        r["why"] = why
        if cn and r["coverage"] >= args.min_coverage:
            cands.append(r)
        elif r["coverage"] >= args.min_coverage:
            others.append(r)

    order = {k: i for i, (k, _, _) in enumerate(HANDWRITING_HINTS)}
    def rank(r):
        low = r["family"].lower().replace(" ", "")
        for k, _, _ in HANDWRITING_HINTS:
            if k in low:
                return (order[k], r["index"])
        return (999, r["index"])
    cands.sort(key=rank)

    print("=" * 78)
    print("手写 / 书法体候选（GB2312 一级字覆盖率 ≥ %.0f%%）" % (args.min_coverage * 100))
    print("=" * 78)
    if not cands:
        print("（没有命中候选。可以换 --all 看全部中文字体，或安装第三方开源手写体）")
    for r in cands:
        print("\n【%s】%s  %s" % (r["cn"], r["family"], r["style"]))
        print("    覆盖 %.1f%%   下标 index=%d" % (r["coverage"] * 100, r["index"]))
        print("    %s" % r["path"])
        if r["why"]:
            print("    特点：%s" % r["why"])

    if args.all:
        print()
        print("=" * 78)
        print("其他非手写中文字体（%d 个）" % len(others))
        print("=" * 78)
        for r in others[:60]:
            print("  %-28s %-10s cov=%.0f%%  %s [%d]" % (
                r["family"], r["style"], r["coverage"] * 100, Path(r["path"]).name, r["index"]))

    if args.json:
        Path(args.json).write_text(json.dumps({"candidates": cands, "others": others},
                                              ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n已写出 %s" % args.json)
    print("\n下一步：python3 font_samples.py --from-json <上面的 json> --out <输出目录>")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
