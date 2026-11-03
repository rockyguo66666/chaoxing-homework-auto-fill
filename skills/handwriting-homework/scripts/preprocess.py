#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""preprocess.py —— 拍照 → 切字 → 归一化，产出可用的单字库。

原理
----
采样纸上的四角黑块是「锚点」。先在照片里找到 4 个实心黑块，算出单应矩阵，
把照片透视校正回模板坐标系；此后每一格的坐标是**已知**的（manifest.json 里写着），
切字就退化成「按坐标裁剪」，不依赖任何分割算法，稳得多。

产出（默认 --out data/）
--------------------
  glyphs/<字>.png        512×512，黑墨 + 透明底，肉眼可看
  glyphs_mask/<字>.png   512×512，二值掩码（白=墨），给 build_font 用
  manifest.json          每个字对应哪些文件、质检标记
  qc/contact_sheet.png   全部切出来的字拼一张，供你肉眼检查切歪没有
  qc/report.md           文字报告：缺了哪些字、哪些格判定为空/过脏

用法
----
  python3 preprocess.py --photo 页1.jpg --photo 页2.jpg --template 采样/manifest.json --out data/
  python3 preprocess.py --photo 页1.jpg --corners "120,90;2100,80;2120,3400;130,3410" --chars "明国和好" --out data/
"""

from __future__ import annotations

import argparse
import math
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import handlib as H


# --------------------------------------------------------------------------
# 找四角定位块
# --------------------------------------------------------------------------

def _order_markers(pts):
    """4 个中心点 → TL, TR, BR, BL。"""
    pts = sorted(pts, key=lambda p: p[1])
    top = sorted(pts[:2], key=lambda p: p[0])
    bot = sorted(pts[2:], key=lambda p: p[0])
    return [top[0], top[1], bot[1], bot[0]]


def find_markers_auto(gray, expect_area, relax=False):
    """在照片里找 4 个「实心、近正方」的黑块，返回 TL,TR,BR,BL 顺序的 4 点。"""
    q = 0.16 if relax else 0.12
    dark = gray < np.quantile(gray, q)
    lab, n = H.label_components(dark)
    if n == 0:
        return None
    h, w = gray.shape
    cands = []
    for i in range(1, n + 1):
        sel = (lab == i)
        area = int(sel.sum())
        if area < 30:
            continue
        ys, xs = np.nonzero(sel)
        bh = ys.max() - ys.min() + 1
        bw = xs.max() - xs.min() + 1
        if bh < 3 or bw < 3:
            continue
        ar = bw / float(bh)
        fill = area / float(bw * bh)
        if not (0.6 <= ar <= 1.7):
            continue
        if fill < (0.72 if relax else 0.85):
            continue
        if not relax and expect_area > 0:
            if not (expect_area / 8.0 <= area <= expect_area * 8.0):
                continue
        cands.append({"area": area, "cx": float(xs.mean()), "cy": float(ys.mean()),
                      "w": bw, "h": bh, "fill": fill})
    if len(cands) < 4:
        return None
    # 黑块应在四角：贪心挑 4 个彼此最分散的
    cands.sort(key=lambda c: -c["area"])
    pool = cands[:max(24, len(cands))]
    import itertools
    best = None
    for combo in itertools.combinations(range(len(pool)), 4):
        pts = [(pool[i]["cx"], pool[i]["cy"]) for i in combo]
        dmin = min(math.hypot(pts[a][0] - pts[b][0], pts[a][1] - pts[b][1])
                   for a in range(4) for b in range(a + 1, 4))
        area_sum = sum(pool[i]["area"] for i in combo)
        score = dmin + area_sum / 1000.0
        if best is None or score > best[0]:
            best = (score, pts)
    if best is None:
        return None
    return _order_markers(best[1])


def parse_corners(spec):
    pts = []
    for chunk in spec.split(";"):
        chunk = chunk.strip()
        if not chunk:
            continue
        x, y = chunk.split(",")
        pts.append((float(x), float(y)))
    if len(pts) != 4:
        raise ValueError("--corners 需要 4 组 x,y，用分号隔开")
    return pts


# --------------------------------------------------------------------------
# 无模板模式：倾斜校正 + 投影切分
# --------------------------------------------------------------------------

def estimate_skew(mask_small):
    best = (0.0, -1.0)
    for a in np.arange(-5.0, 5.01, 0.5):
        im = Image.fromarray((mask_small.astype(np.uint8) * 255), mode="L")
        rot = im.rotate(float(a), resample=Image.BILINEAR, fillcolor=0, expand=False)
        proj = np.asarray(rot, dtype=np.float32).sum(axis=1)
        score = float(np.var(np.diff(proj)))
        if score > best[1]:
            best = (float(a), score)
    return best[0]


def split_by_projection(mask, axis, min_gap=3):
    proj = mask.sum(axis=1 if axis == 0 else 0)
    if proj.size == 0 or proj.max() <= 0:
        return []
    on = proj > max(1.0, proj.max() * 0.02)
    spans = []
    start = None
    gap = 0
    for i, v in enumerate(on.tolist()):
        if v:
            if start is None:
                start = i
            gap = 0
        else:
            if start is not None:
                gap += 1
                if gap >= min_gap:
                    spans.append((start, i - gap + 1))
                    start = None
    if start is not None:
        spans.append((start, len(on)))
    return [s for s in spans if s[1] - s[0] > 0]


# --------------------------------------------------------------------------
# 质检
# --------------------------------------------------------------------------

def drop_rule_remnants(mask, min_len_ratio=0.8, max_thick=4):
    """丢掉「横贯/竖贯整格而且很细」的连通块——那是格线残留，不是笔画。"""
    h, w = mask.shape
    if not mask.any():
        return mask
    lab, n = H.label_components(mask)
    if n == 0:
        return mask
    keep = np.zeros(n + 1, dtype=bool)
    for i in range(1, n + 1):
        ys, xs = np.nonzero(lab == i)
        bh = ys.max() - ys.min() + 1
        bw = xs.max() - xs.min() + 1
        if bw >= min_len_ratio * w and bh <= max_thick:
            continue
        if bh >= min_len_ratio * h and bw <= max_thick:
            continue
        keep[i] = True
    return keep[lab]


def cell_quality(mask):
    area = int(mask.sum())
    h, w = mask.shape
    ratio = area / float(h * w)
    flags = []
    if area < 40:
        flags.append("empty")
    if ratio > 0.45:
        flags.append("tooblack")
    if area:
        rows = mask.sum(axis=1)
        cols = mask.sum(axis=0)
        if int((rows > 0.75 * w).sum()) > 2 or int((cols > 0.75 * h).sum()) > 2:
            flags.append("gridline")
    return ratio, flags


def make_contact_sheet(items, out_path, cols=12, cell=96, label_h=30, title=""):
    if not items:
        return None
    rows = int(math.ceil(len(items) / float(cols)))
    W = cols * cell
    Hh = rows * (cell + label_h) + (40 if title else 0)
    sheet = Image.new("RGB", (W, Hh), (255, 255, 255))
    d = ImageDraw.Draw(sheet)
    try:
        fp, idx = H.content_font()
        f = ImageFont.truetype(fp, 20, index=idx)
    except Exception:
        f = ImageFont.load_default()
    if title:
        d.text((6, 8), title, font=f, fill=(0, 0, 0))
    y_off = 40 if title else 0
    for i, (ch, mask, flags) in enumerate(items):
        r = i // cols
        c = i % cols
        x = c * cell
        y = y_off + r * (cell + label_h)
        img = H.mask_to_rgba(mask).convert("RGB")
        img = img.resize((cell - 8, cell - 8), Image.LANCZOS)
        sheet.paste(Image.new("RGB", (cell - 8, cell - 8), (255, 255, 255)), (x + 4, y))
        sheet.paste(img, (x + 4, y + 3))
        bad = any(fl in ("empty", "tooblack", "gridline") for fl in flags)
        d.text((x + 4, y + cell - 4), ch, font=f, fill=(200, 0, 0) if bad else (60, 60, 60))
    sheet.save(out_path)
    return out_path


def extract_cells(gray_rect, cells, drop, size, pad_ratio):
    """在已校正到模板坐标系的灰图上按坐标裁格。"""
    results = {}
    page_h, page_w = gray_rect.shape
    for cell in cells:
        ch = cell["char"]
        x0, y0, x1, y1 = cell["box"]
        inset = max(2, int(round(min(x1 - x0, y1 - y0) * 0.02)))
        x0i = max(0, int(x0) + inset); x1i = min(page_w, int(x1) - inset)
        y0i = max(0, int(y0) + inset); y1i = min(page_h, int(y1) - inset)
        if x1i - x0i < 8 or y1i - y0i < 8:
            continue
        sub = gray_rect[y0i:y1i, x0i:x1i]
        bg = float(np.percentile(sub, 90))
        mask = H.despeckle(sub < (bg - drop), min_area=8)
        mask = drop_rule_remnants(mask)
        ratio, flags = cell_quality(mask)
        norm = np.zeros((size, size), dtype=bool)
        ok = bool(mask.any())
        if ok:
            norm, ok = H.normalize_glyph(mask, size=size, pad_ratio=pad_ratio, min_area=8)
        if not ok:
            flags = sorted(set(flags + ["empty"]))
        results.setdefault(ch, []).append({"mask": norm, "ratio": ratio, "flags": flags, "ok": ok})
    return results


def main(argv=None):
    ap = argparse.ArgumentParser(description="手写采样照片 → 单字库")
    ap.add_argument("--photo", action="append", default=[], help="照片路径，可重复；顺序对应模板页序")
    ap.add_argument("--template", default=None, help="make_template.py 生成的 manifest.json")
    ap.add_argument("--chars", default=None, help="无模板模式：按阅读顺序给出字表")
    ap.add_argument("--corners", default=None, help="手填四角黑块中心：x,y;x,y;x,y;x,y（TL,TR,BR,BL）")
    ap.add_argument("--out", default="data", help="输出目录")
    ap.add_argument("--size", type=int, default=512)
    ap.add_argument("--pad", type=float, default=0.06)
    ap.add_argument("--drop", type=float, default=0.20, help="墨迹判定：比纸面暗多少（0..1）")
    ap.add_argument("--work-dim", type=int, default=2600, help="照片处理时的最长边")
    args = ap.parse_args(argv)

    if not args.photo:
        print("至少要给一张 --photo", file=sys.stderr)
        return 2
    if not args.template and not args.chars:
        print("模板模式要给 --template；无模板模式要给 --chars", file=sys.stderr)
        return 2

    out = Path(args.out)
    (out / "glyphs").mkdir(parents=True, exist_ok=True)
    (out / "glyphs_mask").mkdir(parents=True, exist_ok=True)
    (out / "qc").mkdir(parents=True, exist_ok=True)

    manifest_out = {
        "version": 1, "kind": "handwriting-glyphs", "size": args.size,
        "source": {"template": args.template, "photos": args.photo, "drop": args.drop},
        "chars": {}, "order": [], "pages": [],
    }
    missing_report = []
    qc_items = []

    tpl = H.read_json(args.template) if args.template else None
    corners = parse_corners(args.corners) if args.corners else None

    for pi, photo in enumerate(args.photo):
        gray = H.read_gray(photo, max_dim=args.work_dim)
        page_tpl = None
        if tpl is not None:
            pages = tpl["pages"]
            page_tpl = pages[pi] if pi < len(pages) else pages[-1]

        detected = None
        if corners is not None:
            detected = [tuple(p) for p in corners]
        if detected is None and page_tpl is not None:
            tpl_w, tpl_h = tpl["page_size"]
            scale = max(gray.shape) / float(max(tpl_w, tpl_h))
            expect_area = (tpl["marker"] * scale) ** 2
            detected = find_markers_auto(gray, expect_area)
            if detected is None:
                print("  [页%d] 严格条件没找到黑块，放宽阈值重试" % (pi + 1), file=sys.stderr)
                detected = find_markers_auto(gray, expect_area, relax=True)
        if detected is None:
            print("  [页%d] 自动定位失败，退回「整页铺满」假设（不够准，建议用 --corners 手填）" % (pi + 1),
                  file=sys.stderr)
            h, w = gray.shape
            detected = [(w * 0.04, h * 0.022), (w * 0.96, h * 0.022),
                        (w * 0.96, h * 0.978), (w * 0.04, h * 0.978)]

        if page_tpl is not None:
            W, Hh = tpl["page_size"]
            src = np.array(detected, dtype=np.float64)
            dst = np.array(page_tpl["markers"], dtype=np.float64)
            Hp = H.homography(src, dst)
            Hinv = H.invert3x3(Hp)
            img = Image.fromarray((np.clip(gray, 0, 1) * 255).astype(np.uint8), mode="L")
            rect = H.warp_perspective(img, Hinv, (W, Hh))
            rect_arr = np.asarray(rect, dtype=np.float32) / 255.0
            rect.save(out / "qc" / ("rectified_p%02d.png" % (pi + 1)))
            res = extract_cells(rect_arr, page_tpl["cells"], args.drop, args.size, args.pad)
            manifest_out["pages"].append({"page": pi + 1, "photo": photo,
                                          "markers": [list(map(float, p)) for p in detected],
                                          "rectified": "qc/rectified_p%02d.png" % (pi + 1)})
        else:
            chars = H.unique_chars(args.chars)
            mask, bg, thr = (gray < (float(np.percentile(gray, 88)) - args.drop)), None, None
            ang = estimate_skew(mask[::4, ::4])
            img = Image.fromarray((mask.astype(np.uint8) * 255), mode="L")
            rot = img.rotate(ang, resample=Image.BILINEAR, fillcolor=0, expand=True)
            rm = np.asarray(rot, dtype=np.uint8) > 127
            cells = []
            idx = 0
            for (y0, y1) in split_by_projection(rm, axis=0):
                band = rm[y0:y1]
                for (x0, x1) in split_by_projection(band, axis=1):
                    if idx >= len(chars):
                        break
                    cells.append({"char": chars[idx], "box": [x0, y0, x1, y1]})
                    idx += 1
            print("  [页%d] 倾斜 %.1f 度，切出 %d 格（给了 %d 个字）" % (pi + 1, ang, len(cells), len(chars)))
            rr = np.asarray(rot, dtype=np.float32) / 255.0
            res = extract_cells(rr, cells, args.drop, args.size, args.pad)
            manifest_out["pages"].append({"page": pi + 1, "photo": photo, "skew": ang,
                                          "markers": None, "rectified": None})

        for ch, samples in res.items():
            for k, s in enumerate(samples):
                if not s["ok"]:
                    missing_report.append((pi + 1, ch, s["flags"]))
                    continue
                base = ch if (ord(ch) > 127 or ch.isalnum()) else ("u%04X" % ord(ch))
                name = base if k == 0 else ("%s_%d" % (base, k + 1))
                H.mask_to_rgba(s["mask"]).save(out / "glyphs" / ("%s.png" % name))
                H.save_mask_png(s["mask"], out / "glyphs_mask" / ("%s.png" % name))
                manifest_out["chars"].setdefault(ch, []).append({
                    "file": "glyphs/%s.png" % name, "mask": "glyphs_mask/%s.png" % name,
                    "ratio": round(s["ratio"], 4), "flags": s["flags"], "page": pi + 1,
                })
                if ch not in manifest_out["order"]:
                    manifest_out["order"].append(ch)
                qc_items.append((ch, s["mask"], s["flags"]))

    H.write_json(out / "manifest.json", manifest_out)
    make_contact_sheet(qc_items, out / "qc" / "contact_sheet.png",
                       title="切出来的字（红色=判定有问题的格子）")

    rep = []
    rep.append("# 预处理报告\n")
    rep.append("- 照片：%d 张" % len(args.photo))
    rep.append("- 成功切字：%d 个不重复字，共 %d 个样本" %
               (len(manifest_out["chars"]), sum(len(v) for v in manifest_out["chars"].values())))
    if missing_report:
        rep.append("\n## 需要补写的格子\n")
        rep.append("| 页 | 字 | 判定 |")
        rep.append("| --- | --- | --- |")
        for pg, ch, fl in missing_report[:200]:
            rep.append("| %d | %s | %s |" % (pg, ch, ",".join(fl)))
    rep.append("\n## 质检图\n")
    rep.append("- qc/contact_sheet.png （逐字检查切得正不正）")
    if any(p.get("rectified") for p in manifest_out["pages"]):
        rep.append("- qc/rectified_p*.png （校正后的整页，四角黑块贴没贴齐一眼可见）")
    (out / "qc" / "report.md").write_text("\n".join(rep) + "\n", encoding="utf-8")

    print("预处理完成：%s" % out)
    print("  不重复字 %d，样本 %d" % (len(manifest_out["chars"]),
                                    sum(len(v) for v in manifest_out["chars"].values())))
    if missing_report:
        print("  有问题的格子 %d 个，详见 qc/report.md" % len(missing_report))
    print("  请打开 %s 肉眼确认切字质量" % (out / "qc" / "contact_sheet.png"))
    print("  下一步：python3 build_font.py --data %s --out myhandwriting.ttf" % out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
