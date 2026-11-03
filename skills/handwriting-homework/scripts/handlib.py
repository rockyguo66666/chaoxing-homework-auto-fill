#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""handlib —— 「个人手写字体」工具链共用底座。

依赖：numpy + Pillow（必需），fontTools（仅 build_font.py 需要），scipy（可选，加速连通域）。

三条设计原则
------------
1. 图像处理只用 numpy + Pillow，不依赖 opencv（macOS 上装 cv2 经常失败）。
2. 位图→矢量自带「裂缝跟随 + RDP 抽稀」实现，不依赖 vtracer / potrace。
3. 一律用 float32 的 0..1 灰度或 bool 掩码，避免 8bit 溢出与阈值歧义。

坐标约定
--------
* 图像坐标：x 向右、y 向下，原点左上。
* 字体坐标：x 向右、y 向上，原点在基线左端（upem=1000，ascent=880，descent=-120）。
* 轮廓方向：图像坐标下「外轮廓 shoelace 面积为正、孔洞为负」；
  翻转 y 进字体后自动满足 TrueType 约定（外轮廓顺时针）。
"""

from __future__ import annotations

import json
import math
import os
import random
import sys
from collections import deque
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

# --------------------------------------------------------------------------
# 路径与字体发现
# --------------------------------------------------------------------------

SKILL_DIR = Path(__file__).resolve().parent.parent
SCRIPTS_DIR = SKILL_DIR / "scripts"
ASSETS_DIR = SKILL_DIR / "assets"
REFERENCES_DIR = SKILL_DIR / "references"

_FONT_DIRS = [
    # macOS
    "/System/Library/Fonts",
    "/System/Library/Fonts/Supplemental",
    "/Library/Fonts",
    os.path.expanduser("~/Library/Fonts"),
    # Windows
    os.path.join(os.environ.get("WINDIR", "C:/Windows"), "Fonts"),
    os.path.expandvars(r"%LOCALAPPDATA%/Microsoft/Windows/Fonts"),
    # Linux
    "/usr/share/fonts",
    "/usr/local/share/fonts",
    os.path.expanduser("~/.fonts"),
    os.path.expanduser("~/.local/share/fonts"),
]

# 内容源字体（只提供「这个字长什么结构」）：楷体优先，最接近手写骨架。
CONTENT_FONT_CANDIDATES = [
    # macOS
    ("Kaiti.ttc", 0), ("Kai.ttf", 0), ("STKaiti.ttf", 0), ("BiauKai.ttc", 0),
    ("Songti.ttc", 0), ("Hiragino Sans GB.ttc", 0), ("PingFang.ttc", 0),
    ("Arial Unicode.ttf", 0), ("STHeiti Medium.ttc", 0),
    # Windows
    ("simkai.ttf", 0), ("KaiTi.ttf", 0), ("simsun.ttc", 0), ("msyh.ttc", 0),
    ("simhei.ttf", 0), ("Deng.ttf", 0),
    # Linux
    ("NotoSansCJK-Regular.ttc", 0), ("NotoSerifCJK-Regular.ttc", 0),
    ("SourceHanSansSC-Regular.otf", 0), ("wqy-zenhei.ttc", 0),
    ("wqy-microhei.ttc", 0), ("DroidSansFallbackFull.ttf", 0),
]
# 手写感字体：只用于 selftest.py 合成假样本，以及极端情况下的兜底。
HAND_FONT_CANDIDATES = [
    ("Hanzipen.ttc", 0), ("Hannotate.ttc", 0), ("Xingkai.ttc", 0),
    ("Kaiti.ttc", 0), ("BiauKai.ttc", 0),
    ("FZShuTi.ttf", 0), ("STXingkai.ttc", 0), ("LXGW WenKai.ttf", 0),
    ("simkai.ttf", 0), ("KaiTi.ttf", 0), ("msyh.ttc", 0),
    ("LXGWWenKai-Regular.ttf", 0), ("NotoSansCJK-Regular.ttc", 0),
    ("wqy-zenhei.ttc", 0), ("DroidSansFallbackFull.ttf", 0),
]


def _font_search_roots():
    roots = list(_FONT_DIRS)
    # macOS 按需下载的字体（楷体/翩翩体/手扎体等）藏在 AssetsV2 的 asset bundle 里
    assets = Path("/System/Library/AssetsV2")
    if assets.is_dir():
        for p in sorted(assets.glob("com_apple_MobileAsset_Font*/*/AssetData")):
            roots.append(str(p))
    return roots


def find_font_file(filename):
    """按文件名在系统字体目录里找；找不到返回 None。"""
    for root in _font_search_roots():
        p = os.path.join(root, filename)
        if os.path.isfile(p):
            return p
    return None


def resolve_font(candidates, what="字体"):
    """candidates: [(文件名, ttc索引), ...]；返回 (路径, 索引)。全找不到时抛错。"""
    for name, idx in candidates:
        p = find_font_file(name)
        if p:
            return p, idx
    raise FileNotFoundError(
        "%s 一个都没找到，试过：%s" % (what, ", ".join(n for n, _ in candidates))
    )


def content_font():
    """内容源字体（楷体优先）。"""
    return resolve_font(CONTENT_FONT_CANDIDATES, "内容源字体（楷体/宋体）")


def hand_font():
    """手写感字体（仅测试/兜底用）。"""
    return resolve_font(HAND_FONT_CANDIDATES, "手写感字体")


def load_pil_font(path, size, index=0):
    return ImageFont.truetype(path, size, index=index)


# --------------------------------------------------------------------------
# 基础图像 I/O
# --------------------------------------------------------------------------

def read_gray(path, max_dim=None):
    """读图为 float32 灰度 0..1，自动按 EXIF 旋转。"""
    im = Image.open(path)
    im = ImageOps.exif_transpose(im)
    im = im.convert("L")
    if max_dim and max(im.size) > max_dim:
        scale = max_dim / float(max(im.size))
        im = im.resize((max(1, int(im.width * scale)), max(1, int(im.height * scale))), Image.LANCZOS)
    return np.asarray(im, dtype=np.float32) / 255.0


def save_gray(arr, path):
    a = np.clip(arr * 255.0 + 0.5, 0, 255).astype(np.uint8)
    Image.fromarray(a, mode="L").save(path)


def save_mask_png(mask, path):
    a = (mask.astype(np.uint8) * 255)
    Image.fromarray(a, mode="L").save(path)


def load_mask_png(path):
    im = Image.open(path).convert("L")
    return (np.asarray(im, dtype=np.float32) / 255.0) > 0.5


def load_glyph_mask(path, thr=127):
    """读字形 PNG：RGBA 用 alpha 通道，L/RGB 用灰度。"""
    im = Image.open(path)
    if im.mode in ("RGBA", "LA"):
        a = np.asarray(im.convert("RGBA"), dtype=np.uint8)[..., 3]
        return a > thr
    g = np.asarray(im.convert("L"), dtype=np.uint8)
    return g > thr


def local_background(gray, radius=None):
    """估计纸张底色（低频分量）。用 Pillow 的 BoxBlur 做，不依赖 scipy。"""
    h, w = gray.shape
    if radius is None:
        radius = max(8, int(min(h, w) / 24))
    im = Image.fromarray((np.clip(gray, 0, 1) * 255).astype(np.uint8), mode="L")
    bg = im.filter(ImageFilter.BoxBlur(radius))
    return np.asarray(bg, dtype=np.float32) / 255.0


def binarize(gray, bg=None, drop=0.20, radius=None):
    """把「比纸面暗 drop 以上」的像素判为墨迹。

    手写：墨约 0.05~0.25，田字格辅助线约 0.75~0.85，纸约 0.9~1.0。
    drop=0.20 时阈值≈0.7~0.8，正好卡掉格线与浅灰字模，保留笔迹。
    """
    if bg is None:
        bg = local_background(gray, radius)
    return gray < (bg - drop)


def ink_ratio(mask):
    return float(mask.mean()) if mask.size else 0.0


# --------------------------------------------------------------------------
# 透视校正（四角定位块）
# --------------------------------------------------------------------------

def homography(src, dst):
    """求 3x3 H，使 H·src ≈ dst（四点对应）。src/dst 为 4x2。"""
    src = np.asarray(src, dtype=np.float64)
    dst = np.asarray(dst, dtype=np.float64)
    A = np.zeros((8, 8), dtype=np.float64)
    b = np.zeros(8, dtype=np.float64)
    for i in range(4):
        x, y = src[i]
        X, Y = dst[i]
        A[2 * i] = [x, y, 1, 0, 0, 0, -X * x, -X * y]
        A[2 * i + 1] = [0, 0, 0, x, y, 1, -Y * x, -Y * y]
        b[2 * i] = X
        b[2 * i + 1] = Y
    h = np.linalg.solve(A, b)
    return np.array([[h[0], h[1], h[2]],
                     [h[3], h[4], h[5]],
                     [h[6], h[7], 1.0]])


def invert3x3(H):
    return np.linalg.inv(H)


def apply_h(H, pts):
    pts = np.asarray(pts, dtype=np.float64)
    ones = np.ones((pts.shape[0], 1))
    v = np.hstack([pts, ones]) @ H.T
    return v[:, :2] / v[:, 2:3]


def pil_perspective_coeffs(H_out2in):
    """PIL Image.transform(PERSPECTIVE) 用的 8 个系数（从输出坐标映射到输入坐标）。"""
    h = H_out2in.flatten()
    return (h[0], h[1], h[2], h[3], h[4], h[5], h[6], h[7])


def warp_perspective(im, H_out2in, out_size):
    return im.transform(out_size, Image.PERSPECTIVE, pil_perspective_coeffs(H_out2in),
                        resample=Image.BICUBIC, fillcolor=255)


def find_markers(gray, expect_pts, search_ratio=0.22, dark_quantile=0.25):
    """在 4 个预期位置附近各找一个实心黑块中心。

    expect_pts: 4x2 的「预期相对位置」比例坐标（0..1），顺序 TL,TR,BR,BL。
    返回 4x2 的像素坐标，顺序同上；找不到的返回 None。
    """
    h, w = gray.shape
    dark = gray < np.quantile(gray, dark_quantile)
    found = []
    for rx, ry in expect_pts:
        cx, cy = rx * w, ry * h
        rw, rh = search_ratio * w, search_ratio * h
        x0 = int(max(0, cx - rw)); x1 = int(min(w, cx + rw))
        y0 = int(max(0, cy - rh)); y1 = int(min(h, cy + rh))
        if x1 - x0 < 4 or y1 - y0 < 4:
            found.append(None); continue
        sub = gray[y0:y1, x0:x1]
        m = dark[y0:y1, x0:x1]
        if m.sum() < 12:
            found.append(None); continue
        ys, xs = np.nonzero(m)
        # 黑块是实心大团，用中位数中心抗噪（笔迹是细线，不会整体碾压中点）
        mx = float(np.median(xs)) + x0
        my = float(np.median(ys)) + y0
        found.append((mx, my))
    return found


# --------------------------------------------------------------------------
# 连通域（scipy 可选）
# --------------------------------------------------------------------------

def label_components(mask):
    """4 连通标记。返回 (labels int32, n)。有 scipy 用 scipy，否则纯 numpy BFS。"""
    try:
        from scipy import ndimage  # type: ignore
        lab, n = ndimage.label(mask)
        return lab.astype(np.int32), int(n)
    except Exception:
        pass
    h, w = mask.shape
    lab = np.zeros((h, w), dtype=np.int32)
    cur = 0
    ys, xs = np.nonzero(mask)
    for sy, sx in zip(ys.tolist(), xs.tolist()):
        if lab[sy, sx]:
            continue
        cur += 1
        q = deque([(sy, sx)])
        lab[sy, sx] = cur
        while q:
            y, x = q.popleft()
            if y > 0 and mask[y - 1, x] and not lab[y - 1, x]:
                lab[y - 1, x] = cur; q.append((y - 1, x))
            if y + 1 < h and mask[y + 1, x] and not lab[y + 1, x]:
                lab[y + 1, x] = cur; q.append((y + 1, x))
            if x > 0 and mask[y, x - 1] and not lab[y, x - 1]:
                lab[y, x - 1] = cur; q.append((y, x - 1))
            if x + 1 < w and mask[y, x + 1] and not lab[y, x + 1]:
                lab[y, x + 1] = cur; q.append((y, x + 1))
    return lab, cur


def despeckle(mask, min_area=12):
    """丢掉面积小于 min_area 的孤立小块（灰尘、纸纹）。"""
    if not mask.any():
        return mask
    lab, n = label_components(mask)
    if n == 0:
        return mask
    counts = np.bincount(lab.ravel(), minlength=n + 1)
    keep = counts >= min_area
    keep[0] = False
    return keep[lab]


def ink_bbox(mask):
    ys, xs = np.nonzero(mask)
    if len(ys) == 0:
        return None
    return int(xs.min()), int(ys.min()), int(xs.max()) + 1, int(ys.max()) + 1


def crop_to_content(mask, min_area=12):
    """去噪 + 紧致裁剪。返回 (裁剪后的掩码, 是否有效)。"""
    m = despeckle(mask, min_area=min_area)
    bb = ink_bbox(m)
    if bb is None:
        return np.zeros((1, 1), dtype=bool), False
    x0, y0, x1, y1 = bb
    if (x1 - x0) < 3 or (y1 - y0) < 3:
        return np.zeros((1, 1), dtype=bool), False
    return m[y0:y1, x0:x1], True


def normalize_glyph(mask, size=512, pad_ratio=0.06, min_area=12):
    """紧致裁剪 → 等比缩放 → 居中放进 size×size 画布。返回 (掩码, 有效标志)。"""
    crop, ok = crop_to_content(mask, min_area=min_area)
    if not ok:
        return np.zeros((size, size), dtype=bool), False
    h, w = crop.shape
    inner = max(4, int(round(size * (1.0 - 2 * pad_ratio))))
    scale = inner / float(max(h, w))
    nw, nh = max(1, int(round(w * scale))), max(1, int(round(h * scale)))
    im = Image.fromarray((crop.astype(np.uint8) * 255), mode="L").resize((nw, nh), Image.LANCZOS)
    small = (np.asarray(im, dtype=np.float32) / 255.0) > 0.45
    out = np.zeros((size, size), dtype=bool)
    ox = (size - nw) // 2
    oy = (size - nh) // 2
    out[oy:oy + nh, ox:ox + nw] = small
    return out, True


def mask_to_rgba(mask, color=(28, 28, 34)):
    """bool 掩码 → 黑墨 + 透明底的 RGBA。"""
    h, w = mask.shape
    rgba = np.zeros((h, w, 4), dtype=np.uint8)
    rgba[..., 0] = color[0]; rgba[..., 1] = color[1]; rgba[..., 2] = color[2]
    rgba[..., 3] = np.where(mask, 255, 0).astype(np.uint8)
    return Image.fromarray(rgba, mode="RGBA")


# --------------------------------------------------------------------------
# 位图 → 矢量轮廓（裂缝跟随 + RDP）
# --------------------------------------------------------------------------

_DIRS = {"E": (1, 0), "S": (0, 1), "W": (-1, 0), "N": (0, -1)}

def _preference(direction):
    """给定来向，按「尽量右转」排出的优先方向序列。

    右转优先 = 对角接触的两个墨块各走各的轮廓，不会产生自相交的八字形轮廓。
    """
    # 屏幕坐标（y 向下）里，顺时针转 90° 就是「向右转」
    right_of = {"E": "S", "S": "W", "W": "N", "N": "E"}
    left_of = {"E": "N", "N": "W", "W": "S", "S": "E"}
    back_of = {"E": "W", "W": "E", "N": "S", "S": "N"}
    return [right_of[direction], direction, left_of[direction], back_of[direction]]


def _pixel_edge_map(mask):
    m = mask.astype(bool)
    pad = np.zeros((m.shape[0] + 2, m.shape[1] + 2), dtype=bool)
    pad[1:-1, 1:-1] = m
    c = pad[1:-1, 1:-1]
    up = pad[:-2, 1:-1]; down = pad[2:, 1:-1]
    left = pad[1:-1, :-2]; right = pad[1:-1, 2:]
    edges = {}
    def add(p, q):
        edges.setdefault(p, []).append(q)
    ys, xs = np.nonzero(c & ~up)
    for y, x in zip(ys.tolist(), xs.tolist()):
        add((x, y), (x + 1, y))
    ys, xs = np.nonzero(c & ~down)
    for y, x in zip(ys.tolist(), xs.tolist()):
        add((x + 1, y + 1), (x, y + 1))
    ys, xs = np.nonzero(c & ~left)
    for y, x in zip(ys.tolist(), xs.tolist()):
        add((x, y + 1), (x, y))
    ys, xs = np.nonzero(c & ~right)
    for y, x in zip(ys.tolist(), xs.tolist()):
        add((x + 1, y), (x + 1, y + 1))
    return edges


def trace_contours(mask, min_points=4):
    """掩码 → 闭合轮廓列表（图像坐标，y 向下）。外轮廓面积为正，孔洞为负。"""
    edges = _pixel_edge_map(mask)
    contours = []
    guard = 0
    limit = 40 * (mask.sum() + 16)
    while True:
        start = None
        for p, outs in edges.items():
            if outs:
                start = p
                break
        if start is None:
            break
        path = [start]
        p = start
        prev = None
        while True:
            outs = edges.get(p)
            if not outs:
                break
            if prev is None:
                q = outs[0]
            else:
                pref = _preference(prev)
                chosen = None
                for d in pref:
                    step = _DIRS[d]
                    cand = (p[0] + step[0], p[1] + step[1])
                    if cand in outs:
                        chosen = cand
                        break
                q = chosen if chosen is not None else outs[0]
            outs.remove(q)
            if not outs:
                del edges[p]
            guard += 1
            if guard > limit:
                raise RuntimeError("轮廓追踪超限，疑似掩码异常")
            if q == start:
                break
            path.append(q)
            prev = _dir_of(p, q)
            p = q
        if len(path) >= min_points:
            contours.append(np.asarray(path, dtype=np.float64))
    return contours


def _dir_of(p, q):
    dx, dy = q[0] - p[0], q[1] - p[1]
    for k, v in _DIRS.items():
        if v == (dx, dy):
            return k
    raise ValueError("非法邻接 %s -> %s" % (p, q))


def polygon_area(pts):
    x = pts[:, 0]; y = pts[:, 1]
    return 0.5 * float(np.dot(x, np.roll(y, -1)) - np.dot(np.roll(x, -1), y))


def simplify_rdp(pts, eps):
    """Ramer–Douglas–Peucker 抽稀（迭代实现，避免递归爆栈）。闭合折线按开放段处理。"""
    n = len(pts)
    if n <= 3 or eps <= 0:
        return pts
    keep = np.zeros(n, dtype=bool)
    keep[0] = True
    keep[-1] = True
    stack = [(0, n - 1)]
    while stack:
        i, j = stack.pop()
        if j <= i + 1:
            continue
        seg = pts[i + 1:j]
        a = pts[i]; b = pts[j]
        ab = b - a
        L = math.hypot(ab[0], ab[1])
        if L < 1e-9:
            d = np.hypot(seg[:, 0] - a[0], seg[:, 1] - a[1])
        else:
            d = np.abs((seg[:, 0] - a[0]) * ab[1] - (seg[:, 1] - a[1]) * ab[0]) / L
        k = int(np.argmax(d))
        if d[k] > eps:
            m = i + 1 + k
            keep[m] = True
            stack.append((i, m))
            stack.append((m, j))
    return pts[keep]


def point_in_polygon(pt, poly):
    x, y = pt
    xp = poly[:, 0]; yp = poly[:, 1]
    n = len(poly)
    inside = False
    j = n - 1
    for i in range(n):
        xi, yi = xp[i], yp[i]
        xj, yj = xp[j], yp[j]
        if ((yi > y) != (yj > y)) and (x < (xj - xi) * (y - yi) / (yj - yi + 1e-12) + xi):
            inside = not inside
        j = i
    return inside


def contour_depths(contours):
    """每个轮廓的嵌套深度（0=最外层）。用「面积绝对值更大的容器」判定。"""
    areas = [abs(polygon_area(c)) for c in contours]
    order = sorted(range(len(contours)), key=lambda i: -areas[i])
    depth = [0] * len(contours)
    for a in range(len(order)):
        ia = order[a]
        for b in range(a + 1, len(order)):
            ib = order[b]
            if point_in_polygon(contours[ib][0], contours[ia]):
                depth[ib] = max(depth[ib], depth[ia] + 1)
    return depth


# --------------------------------------------------------------------------
# 打包 TTF
# --------------------------------------------------------------------------

# 字符在 em 方框里的位置：880×880，水平居中，垂直略偏上（中文重心）
GLYPH_BOX = (60.0, -40.0, 940.0, 840.0)  # x0, y0, x1, y1（字体坐标，y 向上）
UPEM = 1000
ASCENT = 880
DESCENT = -120


def glyph_name(ch):
    return "uni%04X" % ord(ch)


def outline_glyph(mask, eps_px=1.1, min_area_px=10.0):
    """512 掩码 → 简化的字体坐标轮廓列表。"""
    contours = trace_contours(mask)
    out = []
    for c in contours:
        if len(c) < 3:
            continue
        c = simplify_rdp(c, eps_px)
        if len(c) < 3:
            continue
        if abs(polygon_area(c)) < min_area_px:
            continue
        out.append(c)
    if not out:
        return []
    bb = ink_bbox(mask)
    x0, y0, x1, y1 = bb
    bw = max(1.0, x1 - x0)
    bh = max(1.0, y1 - y0)
    TX0, TY0, TX1, TY1 = GLYPH_BOX
    s = min((TX1 - TX0) / bw, (TY1 - TY0) / bh)
    ox = TX0 + ((TX1 - TX0) - bw * s) / 2.0
    oy = TY0 + ((TY1 - TY0) - bh * s) / 2.0
    scaled = []
    for c in out:
        X = ox + (c[:, 0] - x0) * s
        Y = oy + ((y1) - c[:, 1]) * s  # 翻转 y
        scaled.append(np.stack([X, Y], axis=1))
    return scaled


def build_ttf(glyph_masks, out_path, family_name="MyHandwriting", style_name="Regular",
              advance_width=UPEM, ascii_widths=None, verbose=True):
    """glyph_masks: {字符: bool 掩码} → 写出 TTF。返回统计字典。"""
    from fontTools.fontBuilder import FontBuilder
    from fontTools.pens.ttGlyphPen import TTGlyphPen

    glyph_order = [".notdef"]
    glyf = {}
    metrics = {}

    pen = TTGlyphPen(None)
    glyf[".notdef"] = pen.glyph()
    metrics[".notdef"] = (advance_width, 0)

    failed = []
    for ch, mask in sorted(glyph_masks.items()):
        name = glyph_name(ch)
        contours = outline_glyph(mask)
        if not contours:
            failed.append(ch)
            continue
        pen = TTGlyphPen(None)
        for c in contours:
            pen.moveTo((float(c[0][0]), float(c[0][1])))
            for p in c[1:]:
                pen.lineTo((float(p[0]), float(p[1])))
            pen.closePath()
        glyf[name] = pen.glyph()
        aw = advance_width
        if ascii_widths and ch in ascii_widths:
            aw = ascii_widths[ch]
        metrics[name] = (int(round(aw)), 0)
        glyph_order.append(name)

    if len(glyph_order) <= 1:
        raise ValueError("没有任何可用字形，检查 glyphs 目录")

    cmap = {ord(ch): glyph_name(ch) for ch in glyph_masks if glyph_name(ch) in glyf}

    fb = FontBuilder(UPEM, isTTF=True)
    fb.setupGlyphOrder(glyph_order)
    fb.setupCharacterMap(cmap)
    fb.setupGlyf(glyf)
    fb.setupHorizontalMetrics(metrics)
    fb.setupHorizontalHeader(ascent=ASCENT, descent=DESCENT, lineGap=0)
    fb.setupNameTable({
        "familyName": family_name,
        "styleName": style_name,
        "uniqueFontIdentifier": "%s-%s" % (family_name, style_name),
        "fullName": "%s %s" % (family_name, style_name),
        "psName": "%s-%s" % (family_name.replace(" ", ""), style_name),
        "version": "Version 1.000",
    })
    fb.setupOS2(sTypoAscender=ASCENT, sTypoDescender=DESCENT, sTypoLineGap=0,
                usWinAscent=ASCENT, usWinDescent=-DESCENT, achVendID="HAND")
    fb.setupPost()
    fb.save(str(out_path))
    if verbose:
        print("[handlib] 写出 %s：%d 个真实字形" % (out_path, len(glyf) - 1))
        if failed:
            print("[handlib] 轮廓为空被跳过：%s" % "".join(failed))
    return {"glyphs": len(glyf) - 1, "failed": failed, "cmap": len(cmap)}


def rasterize_glyph(ttf_path, ch, size=512, index=0):
    """用刚建好的 TTF 反渲染一个字，返回 (掩码, 有效)。用于校验矢量质量。"""
    f = ImageFont.truetype(ttf_path, size, index=index)
    im = Image.new("L", (size * 2, size * 2), 0)
    d = ImageDraw.Draw(im)
    d.text((size // 2, size // 2), ch, font=f, fill=255)
    arr = np.asarray(im, dtype=np.float32) / 255.0 > 0.5
    return crop_to_content(arr, min_area=4)


def iou(a, b):
    if a.shape != b.shape:
        h = min(a.shape[0], b.shape[0]); w = min(a.shape[1], b.shape[1])
        a = a[:h, :w]; b = b[:h, :w]
    inter = np.logical_and(a, b).sum()
    union = np.logical_or(a, b).sum()
    return float(inter) / float(union) if union else 0.0


def align_and_iou(mask_a, mask_b):
    """各自紧致裁剪后等比缩放到同一尺寸再算 IoU，抵消位置/尺度差异。"""
    a, ok1 = crop_to_content(mask_a, 4)
    b, ok2 = crop_to_content(mask_b, 4)
    if not ok1 or not ok2:
        return 0.0
    S = 128
    def fit(m):
        im = Image.fromarray((m.astype(np.uint8) * 255), mode="L")
        sc = S / float(max(m.shape))
        im = im.resize((max(1, int(m.shape[1] * sc)), max(1, int(m.shape[0] * sc))), Image.LANCZOS)
        arr = np.asarray(im, dtype=np.float32) / 255.0 > 0.5
        out = np.zeros((S, S), dtype=bool)
        oy = (S - arr.shape[0]) // 2; ox = (S - arr.shape[1]) // 2
        out[oy:oy + arr.shape[0], ox:ox + arr.shape[1]] = arr
        return out
    return iou(fit(a), fit(b))


# --------------------------------------------------------------------------
# 文字与字符集
# --------------------------------------------------------------------------

def unique_chars(text, keep_ascii=True, keep_punct=True):
    """按首次出现顺序去重。默认保留中文、英文数字、常用标点。"""
    seen = set()
    out = []
    for ch in text:
        if ch in seen:
            continue
        if ch == "\n" or ch == "\r":
            continue
        o = ord(ch)
        is_cjk = 0x3400 <= o <= 0x9FFF or 0xF900 <= o <= 0xFAFF
        if is_cjk:
            pass
        elif ch.isascii() and ch.isprintable():
            if not keep_ascii:
                continue
            if not (ch.isalnum() or (keep_punct and ch in "，。！？；：、（）【】《》“”‘’—…·,.!?;:()[]{}\"'+-*/=%$#@&<>_~^|\\")):
                continue
        elif not keep_punct:
            continue
        seen.add(ch)
        out.append(ch)
    return out


COMMON_PUNCT = "，。！？；：、（）《》“”‘’—…·"


def load_char_file(path):
    """读字符表：每行一个字符或一串字符，忽略 # 注释与空白。"""
    chars = []
    with open(path, "r", encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            for ch in line:
                if ch.isspace():
                    continue
                chars.append(ch)
    seen = set(); out = []
    for ch in chars:
        if ch not in seen:
            seen.add(ch); out.append(ch)
    return out


def write_json(path, obj):
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=2)
    return path


def read_json(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def fit_rect(w, h, box_w, box_h):
    s = min(box_w / max(1.0, w), box_h / max(1.0, h))
    return w * s, h * s
