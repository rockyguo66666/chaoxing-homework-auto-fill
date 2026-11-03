#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""doctor.py —— 环境自检。出问题先跑这个。

用法
----
  python3 doctor.py
"""

from __future__ import annotations

import importlib
import os
import platform
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

SCRIPT_DIR = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPT_DIR))

OK = "OK  "
WARN = "WARN"
FAIL = "FAIL"
rows = []


def row(status, name, detail=""):
    rows.append((status, name, detail))


def check_deps():
    row(OK, "Python", "%s (%s)" % (platform.python_version(), sys.executable))
    if sys.version_info < (3, 8):
        row(FAIL, "Python 版本", "需要 3.8+")
    for mod, need in (("numpy", True), ("PIL", True), ("fontTools", True), ("scipy", False)):
        try:
            m = importlib.import_module(mod)
            row(OK, "依赖 %s" % mod, getattr(m, "__version__", "已安装"))
        except Exception as e:
            row(FAIL if need else WARN, "依赖 %s" % mod,
                ("必需，缺失：%s" % e) if need else "可选，装了会更快（没有也能跑）")


def check_fonts():
    import handlib as H
    for label, fn in (("内容源字体（楷体优先）", H.content_font), ("手写感字体", H.hand_font)):
        try:
            p, idx = fn()
            row(OK, label, "%s [index=%d]" % (Path(p).name, idx))
        except Exception as e:
            row(WARN, label, str(e))


def check_io():
    for label, p in (("技能目录", SCRIPT_DIR.parent), ("当前目录", Path.cwd())):
        row(OK if os.access(str(p), os.W_OK) else FAIL, "%s 可写" % label, str(p))


def check_smoke():
    """真建一个 2 字 TTF，确认 fontTools 组装 + PIL 回读没问题。"""
    import handlib as H
    from PIL import Image, ImageDraw, ImageFont
    try:
        tmp = Path(tempfile.mkdtemp(prefix="hand-doctor-"))
        fp, idx = H.hand_font()
        masks = {}
        for ch in ("永", "字"):
            f = ImageFont.truetype(fp, 380, index=idx)
            im = Image.new("L", (512, 512), 0)
            ImageDraw.Draw(im).text((40, 30), ch, font=f, fill=255)
            m, ok = H.normalize_glyph((np.asarray(im, dtype=np.float32) / 255.0) > 0.5, 512)
            if ok:
                masks[ch] = m
        ttf = tmp / "smoke.ttf"
        t0 = time.time()
        stats = H.build_ttf(masks, ttf, family_name="SmokeTest", verbose=False)
        back, ok = H.rasterize_glyph(ttf, "永", 256)
        score = H.align_and_iou(masks["永"], back) if ok else 0.0
        row(OK if score > 0.7 else WARN, "建字体冒烟测试",
            "%d 字形 / %.0f KB / 回读 IoU %.3f / %.1fs" %
            (stats["glyphs"], ttf.stat().st_size / 1024.0, score, time.time() - t0))
    except Exception as e:
        row(FAIL, "建字体冒烟测试", "%s: %s" % (type(e).__name__, e))


def check_net():
    import urllib.request
    url = "https://cdn.jsdelivr.net/gh/cjkvi/cjkvi-ids@master/ids.txt"
    try:
        req = urllib.request.Request(url, method="HEAD",
                                     headers={"User-Agent": "handwriting-homework/1.0"})
        with urllib.request.urlopen(req, timeout=8) as r:
            row(OK, "IDS 部件表可下载", "HTTP %s" % r.status)
    except Exception as e:
        row(WARN, "IDS 部件表可下载", "连不上也没关系：compose.py 可以用 --decompose 手写分解，或跳过")


def main():
    check_deps()
    check_fonts()
    check_io()
    check_smoke()
    check_net()
    width = max(len(r[1]) for r in rows) + 2
    print("=" * 72)
    print("手写体工具链 · 环境自检")
    print("=" * 72)
    for status, name, detail in rows:
        print("[%s] %-*s %s" % (status, width, name, detail))
    print("=" * 72)
    fails = [r for r in rows if r[0] == FAIL]
    if fails:
        print("有 %d 项硬伤，先按上面的提示修。" % len(fails))
        return 1
    warns = [r for r in rows if r[0] == WARN]
    print("基础环境可用%s。下一步：python3 make_template.py --from-text 你的作业.txt --out 采样/"
          % ("（有 %d 条提示，不阻塞）" % len(warns) if warns else ""))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
