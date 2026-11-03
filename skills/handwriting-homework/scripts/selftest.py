#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""selftest.py —— 端到端自测：用「合成手写」跑通整条流水线并给出量化结果。

说明（诚实版）
------------
本机没有你的真实笔迹，所以这里用系统里的手写感字体（HanziPen/手扎体）**假装**是你写的，
再故意模拟手机拍照（透视畸变 + 亮度不匀 + 噪点 + JPEG 压缩），然后跑完整流程：

  生成采样纸 → 合成笔迹 → 模拟拍照 → 切字 → 建 TTF → 渲染成图 → 逐字比对 IoU

它验证的是**流水线是否通**（切字准不准、cmap 有没有写对、字有没有变豆腐块），
不验证「像不像你」——那要等你交真实的采样照片。

用法
----
  python3 selftest.py --out /tmp/hand-selftest
"""

from __future__ import annotations

import argparse
import json
import random
import shutil
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

import handlib as H

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

import make_template as MT      # noqa: E402
import preprocess as PP         # noqa: E402
import build_font as BF         # noqa: E402

DEMO_TEXT = (
    "简述牛顿第一定律的内容及其物理意义。"
    "一切物体总保持匀速直线运动状态或静止状态，直到有外力迫使它改变这种状态为止。"
    "这一定律揭示了力不是维持运动的原因，而是改变物体运动状态的原因。"
)


# --------------------------------------------------------------------------
# 合成「手写」
# --------------------------------------------------------------------------

def draw_handwriting(page_path, cells, hand_font, rng):
    """在采样纸上逐格「写」字，返回 (写完的整页, 只含笔迹的墨迹页)。"""
    page = Image.open(page_path).convert("RGB")
    ink_layer = Image.new("L", page.size, 0)
    for cell in cells:
        ch = cell["char"]
        x0, y0, x1, y1 = cell["box"]
        cw, chh = x1 - x0, y1 - y0
        size = int(cw * rng.uniform(0.66, 0.74))
        try:
            f = ImageFont.truetype(hand_font[0], size, index=hand_font[1])
        except Exception:
            continue
        bbox = f.getbbox(ch)
        if bbox is None:
            continue
        gw, gh = bbox[2] - bbox[0], bbox[3] - bbox[1]
        if gw <= 0 or gh <= 0:
            continue
        layer = Image.new("L", (gw + 24, gh + 24), 0)
        ImageDraw.Draw(layer).text((12 - bbox[0], 12 - bbox[1]), ch, font=f, fill=255)
        layer = layer.rotate(rng.uniform(-3, 3), resample=Image.BICUBIC, expand=True, fillcolor=0)
        jx = rng.uniform(-0.03, 0.03) * cw
        jy = rng.uniform(-0.03, 0.03) * chh
        px = int(x0 + (cw - layer.width) / 2 + jx)
        py = int(y0 + (chh - layer.height) / 2 + jy)
        ink_layer.paste(layer, (px, py), layer)
    page.paste((16, 16, 24), (0, 0), ink_layer)
    return page, ink_layer


def simulate_photo(page, markers, rng, out_path, out_size=(2400, 3300), border=0.07):
    """把整页拍成照片：透视畸变 + 亮度不匀 + 噪点 + 模糊 + JPEG。"""
    W, Hh = out_size
    tx0, ty0 = W * border, Hh * border
    tx1, ty1 = W * (1 - border), Hh * (1 - border)
    dst = [(tx0, ty0), (tx1, ty0), (tx1, ty1), (tx0, ty1)]
    dst = [(float(x + rng.uniform(-45, 45)), float(y + rng.uniform(-45, 45))) for x, y in dst]
    src = np.array(markers, dtype=np.float64)
    Hp = H.homography(src, dst)                 # 页面坐标 -> 照片坐标
    Hinv = H.invert3x3(Hp)                      # 照片坐标 -> 页面坐标（PIL 要的）
    warped = page.transform((W, Hh), Image.PERSPECTIVE, H.pil_perspective_coeffs(Hinv),
                            resample=Image.BICUBIC, fillcolor=(206, 203, 197))
    arr = np.asarray(warped, dtype=np.float32)
    yy, xx = np.mgrid[0:Hh, 0:W]
    grad = 1.0 + 0.07 * ((xx / W) - 0.5) + 0.05 * ((yy / Hh) - 0.5) - 0.05 * (((xx / W) - 0.5) ** 2)
    nprng = np.random.default_rng(rng.randrange(1 << 30))
    arr = arr * grad[..., None] + nprng.normal(0, 3.2, arr.shape)
    warped = Image.fromarray(np.clip(arr + 0.5, 0, 255).astype(np.uint8), mode="RGB")
    warped = warped.filter(ImageFilter.GaussianBlur(0.6))
    warped.save(out_path, quality=88)
    return out_path


# --------------------------------------------------------------------------
# 主流程
# --------------------------------------------------------------------------

def run(out_dir, text, seed=7):
    out = Path(out_dir)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    rng = random.Random(seed)
    log = []

    def step(msg):
        print("  " + msg)
        log.append(msg)

    chars = H.unique_chars(text)
    print("[1/6] 生成采样纸（%d 个字）" % len(chars))
    sample = out / "sample"
    rc = MT.main(["--chars", "".join(chars), "--out", str(sample), "--cols", "8", "--rows", "10"])
    assert rc == 0, "make_template 失败"
    tpl = H.read_json(sample / "manifest.json")
    page1 = tpl["pages"][0]
    step("采样纸：%s（%d 格）" % (page1["file"], len(page1["cells"])))

    print("[2/6] 合成「手写」并模拟拍照")
    hand = H.hand_font()
    page, ink_layer = draw_handwriting(sample / page1["file"], page1["cells"], hand, rng)
    written = out / "written_page.png"
    page.save(written)
    photo = out / "photo_sim.jpg"
    simulate_photo(page, page1["markers"], rng, photo)
    step("合成笔迹字体：%s" % Path(hand[0]).name)
    step("模拟照片：%s" % photo.name)

    # 参考掩码（未经过拍照退化，用于给切字质量打分）
    refs = {}
    for cell in page1["cells"]:
        x0, y0, x1, y1 = cell["box"]
        sub = (np.asarray(ink_layer, dtype=np.uint8) / 255.0)[y0:y1, x0:x1] > 0.5
        norm, ok = H.normalize_glyph(sub, size=512, pad_ratio=0.06, min_area=8)
        if ok:
            refs[cell["char"]] = norm

    print("[3/6] 切字")
    data = out / "data"
    rc = PP.main(["--photo", str(photo), "--template", str(sample / "manifest.json"),
                  "--out", str(data)])
    assert rc == 0, "preprocess 失败"
    got = H.read_json(data / "manifest.json")
    step("切出 %d / %d 个字" % (len(got["chars"]), len(refs)))

    print("[4/6] 建字体")
    ttf = out / "myhandwriting.ttf"
    t0 = time.time()
    rc = BF.main(["--data", str(data), "--out", str(ttf), "--verify", "25"])
    assert rc == 0, "build_font 失败"
    step("TTF %.0f KB，耗时 %.1fs" % (ttf.stat().st_size / 1024.0, time.time() - t0))

    print("[5/6] 渲染成图")
    import render as RD
    png = out / "render.png"
    rc = RD.main(["--text", text, "--font", str(ttf), "--out", str(png),
                  "--chars-per-line", "26", "--rules", "line"])
    assert rc == 0, "render 失败"
    step("渲染：%s %s" % (png.name, Image.open(png).size))

    print("[6/6] 打分")
    scores = []
    for ch, ref in refs.items():
        if ch not in got["chars"]:
            continue
        gotmask = H.load_glyph_mask(data / got["chars"][ch][0]["mask"])
        scores.append((ch, H.align_and_iou(ref, gotmask)))
    scores.sort(key=lambda x: x[1])
    mean = float(np.mean([s for _, s in scores])) if scores else 0.0
    low = [s for s in scores if s[1] < 0.70]
    verdict = "通过" if (len(got["chars"]) >= len(refs) * 0.95 and mean >= 0.75) else "需要排查"

    rep = ["# 端到端自测报告\n",
           "- 结论：**%s**" % verdict,
           "- 采样字 %d，切出 %d，平均切字 IoU %.3f" % (len(refs), len(got["chars"]), mean),
           "- 字体大小 %.0f KB" % (ttf.stat().st_size / 1024.0),
           "- 产物：%s" % out, "",
           "## 逐字得分（最低 15 个）\n",
           "| 字 | IoU |", "| --- | --- |"]
    for ch, sc in scores[:15]:
        rep.append("| %s | %.3f |" % (ch, sc))
    if low:
        rep.append("\n低于 0.70 的字：%s" % "".join(c for c, _ in low))
    rep.append("\n> 说明：此自测用系统手写字体假装你的笔迹。IoU 反映的是「拍照→切字→矢量化」"
               "这一路的保真度；「像不像你」要用你的真实采样才能判断。")
    (out / "selftest_report.md").write_text("\n".join(rep) + "\n", encoding="utf-8")

    print()
    print("=" * 56)
    print("自测结论：%s" % verdict)
    print("  采样字 %d → 切出 %d，平均 IoU %.3f" % (len(refs), len(got["chars"]), mean))
    print("  报告：%s" % (out / "selftest_report.md"))
    print("  渲染样张：%s" % png)
    print("=" * 56)
    return 0 if verdict == "通过" else 1


def main(argv=None):
    ap = argparse.ArgumentParser(description="端到端自测")
    ap.add_argument("--out", default="/tmp/hand-selftest")
    ap.add_argument("--text", default=DEMO_TEXT)
    ap.add_argument("--seed", type=int, default=7)
    args = ap.parse_args(argv)
    return run(args.out, args.text, args.seed)


if __name__ == "__main__":
    raise SystemExit(main())
