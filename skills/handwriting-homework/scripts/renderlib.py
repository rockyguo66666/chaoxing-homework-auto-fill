#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""renderlib —— 把文字排成「像人写的」图片。

用到的手感开关（jitter）：
  rot   每个字 ±旋转角（度）
  dx/dy 每字水平/垂直抖动（相对字号的倍数）
  size  每字字号微随机幅度
  kern  字距微随机幅度
人写字天然不齐；全关掉就是「字体感」，开太大又会抖成机器故障。默认值经过一轮实测。
"""

from __future__ import annotations

import math
import random
from pathlib import Path

import numpy as np
from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

import handlib as H

DEFAULT_INK = (32, 32, 44)          # 中性偏蓝的黑（圆珠笔感）
PAPER_WHITE = (253, 252, 250)
PAPER_CREAM = (250, 246, 232)
RULE_COLOR = (176, 190, 205)        # 淡蓝横线
GRID_COLOR = (200, 205, 210)        # 田字格

DEFAULT_JITTER = {"rot": 1.6, "dx": 0.035, "dy": 0.028, "size": 0.022, "kern": 0.02}


# --------------------------------------------------------------------------
# 纸
# --------------------------------------------------------------------------

def _np_rng(rng):
    """兼容 random.Random 与 numpy Generator：需要生成数组时统一拿到 numpy 版。"""
    if rng is None:
        return np.random.default_rng()
    if hasattr(rng, "integers"):
        return rng
    return np.random.default_rng(rng.randrange(1 << 30))


def make_paper(w, h, rng, style="paper", base=None):
    """造一张纸：基色 + 低频不匀 + 轻微暗角 + 极细颗粒。"""
    if base is None:
        base = PAPER_CREAM if style in ("paper", "cream", "ruled", "grid") else PAPER_WHITE
    npr = _np_rng(rng)
    small_w, small_h = max(2, w // 24), max(2, h // 24)
    noise = npr.random((small_h, small_w))
    noise_img = Image.fromarray((noise * 255).astype(np.uint8), mode="L").resize((w, h), Image.BICUBIC)
    n = np.asarray(noise_img, dtype=np.float32) / 255.0
    n = (n - n.mean()) * 10.0                                  # 低频不匀 ±10 级
    grain = (npr.random((h, w)).astype(np.float32) - 0.5) * 5.0  # 颗粒噪点
    yy, xx = np.mgrid[0:h, 0:w]
    cx, cy = w / 2.0, h / 2.0
    r = np.sqrt(((xx - cx) / cx) ** 2 + ((yy - cy) / cy) ** 2)
    vign = -6.0 * np.clip(r - 0.75, 0, None) ** 1.5            # 边缘略暗
    arr = np.zeros((h, w, 3), dtype=np.float32)
    for i in range(3):
        arr[..., i] = base[i] + n + grain + vign
    paper = Image.fromarray(np.clip(arr + 0.5, 0, 255).astype(np.uint8), mode="RGB")
    if style in ("scan", "photo"):
        paper = paper.filter(ImageFilter.GaussianBlur(0.4))
    return paper


def draw_rules(paper, box, line_height, style="none", color=None, rng=None, line_y0=None):
    """在纸上画横线 / 田字格。box = (x0, y0, x1, y1)。"""
    if style in (None, "none"):
        return paper
    d = ImageDraw.Draw(paper)
    x0, y0, x1, y1 = box
    col = color or (RULE_COLOR if style == "line" else GRID_COLOR)
    if style == "line":
        y = (line_y0 if line_y0 is not None else y0) + line_height
        while y < y1:
            d.line([(x0, y), (x1, y)], fill=col, width=2)
            y += line_height
    elif style == "grid":
        cell = line_height
        y = (line_y0 if line_y0 is not None else y0)
        while y <= y1:
            d.line([(x0, y), (x1, y)], fill=col, width=2)
            y += cell
        x = x0
        while x <= x1:
            d.line([(x, y0), (x, y1)], fill=col, width=2)
            x += cell
    return paper


# --------------------------------------------------------------------------
# 单字贴图
# --------------------------------------------------------------------------

class FontBook:
    """按字号缓存 FreeTypeFont，并记录哪些字在字库里（缺字要如实报告）。"""

    def __init__(self, ttf_path, index=0, fallback_path=None, fallback_index=0):
        self.ttf_path = str(ttf_path)
        self.index = index
        self._cache = {}
        self.fallback_path = fallback_path
        self.fallback_index = fallback_index
        self._fb_cache = {}
        # .ttc 是字体集合，索引不同字也不同（例如 Kaiti.ttc[0]=楷体SC、[1]=华文楷体）
        self.covered = self._read_cmap(self.ttf_path, index)
        self.fallback_covered = self._read_cmap(fallback_path, fallback_index) if fallback_path else set()

    @staticmethod
    def _read_cmap(path, index=0):
        if not path:
            return set()
        try:
            from fontTools.ttLib import TTFont
            f = TTFont(str(path), fontNumber=index, lazy=True)
            cps = set()
            for t in f["cmap"].tables:
                cps.update(t.cmap.keys())
            f.close()
            return cps
        except Exception:
            return set()

    def font(self, size):
        size = max(1, int(round(size)))
        f = self._cache.get(size)
        if f is None:
            f = ImageFont.truetype(self.ttf_path, size, index=self.index)
            self._cache[size] = f
        return f

    def fallback_font(self, size):
        size = max(1, int(round(size)))
        f = self._fb_cache.get(size)
        if f is None:
            f = ImageFont.truetype(self.fallback_path, size, index=self.fallback_index)
            self._fb_cache[size] = f
        return f

    def classify(self, ch):
        """返回 'hand' | 'fallback' | 'missing'。"""
        if ord(ch) in self.covered:
            return "hand"
        if self.fallback_path and ord(ch) in self.fallback_covered:
            return "fallback"
        return "missing"


def _char_mask(font, ch):
    bbox = font.getbbox(ch)
    if bbox is None:
        return None, None
    w = int(math.ceil(bbox[2] - bbox[0]))
    h = int(math.ceil(bbox[3] - bbox[1]))
    if w <= 0 or h <= 0:
        return None, None
    im = Image.new("L", (w, h), 0)
    ImageDraw.Draw(im).text((-bbox[0], -bbox[1]), ch, font=font, fill=255)
    return im, bbox


def _stamp(ink, ch, book, x, y, size, rng, jitter, use_fallback=True):
    """把一个字画进 ink 图层。x,y 是「字形框左上角」的标称位置。"""
    kind = book.classify(ch)
    if kind == "hand":
        font = book.font(size)
    elif kind == "fallback" and use_fallback:
        font = book.fallback_font(size)
    elif kind == "missing" and use_fallback and book.fallback_path:
        font = book.fallback_font(size)
        kind = "fallback"
    else:
        return kind
    mask, bbox = _char_mask(font, ch)
    if mask is None:
        return kind
    j = jitter or {}
    rot = rng.uniform(-j.get("rot", 0), j.get("rot", 0))
    if abs(rot) > 0.05:
        mask = mask.rotate(rot, resample=Image.BICUBIC, expand=True, fillcolor=0)
    dx = rng.uniform(-j.get("dx", 0), j.get("dx", 0)) * size
    dy = rng.uniform(-j.get("dy", 0), j.get("dy", 0)) * size
    # bbox 偏移：把「字形框左上」换算成「墨迹左上」
    px = int(round(x + bbox[0] + dx))
    py = int(round(y + bbox[1] + dy))
    # 旋转后 expand 会让中心漂移，按中心对齐回来
    px -= int(round((mask.width - (bbox[2] - bbox[0])) / 2.0))
    py -= int(round((mask.height - (bbox[3] - bbox[1])) / 2.0))
    if px > ink.width or py > ink.height or px + mask.width < 0 or py + mask.height < 0:
        return kind
    ink.paste(mask, (px, py), mask)
    return kind


# --------------------------------------------------------------------------
# 段落排版
# --------------------------------------------------------------------------

NO_LINE_START = "，。！？；：、）》」』”’…·%"
NO_LINE_END = "（《「『“‘"


def wrap_text(text, chars_per_line):
    """按字数硬换行，带最基本的避头尾（行首不放收尾标点）。"""
    lines = []
    for para in text.split("\n"):
        if para == "":
            lines.append("")
            continue
        cur = ""
        for ch in para:
            if len(cur) >= chars_per_line and ch not in NO_LINE_START:
                lines.append(cur)
                cur = ""
            cur += ch
        lines.append(cur)
    return lines


def render_lines(ink, lines, book, origin, size, line_height, chars_per_line,
                 rng, jitter, use_fallback=True, font_scale=1.0):
    """把多行文字画进 ink 图层。返回 (统计, 每行的 y 基线顶)。"""
    x0, y0 = origin
    stats = {"hand": 0, "fallback": 0, "missing": 0}
    missing_chars = set()
    ys = []
    for li, line in enumerate(lines):
        y = y0 + li * line_height
        ys.append(y)
        x = x0
        for ch in line:
            s = size * font_scale * (1.0 + rng.uniform(-jitter.get("size", 0), jitter.get("size", 0)))
            kind = _stamp(ink, ch, book, x, y, s, rng, jitter, use_fallback=use_fallback)
            stats[kind] = stats.get(kind, 0) + 1
            if kind == "missing":
                missing_chars.add(ch)
            adv = book.font(s).getlength(ch) if kind == "hand" else (
                book.fallback_font(s).getlength(ch) if book.fallback_path else s)
            x += adv * (1.0 + rng.uniform(-jitter.get("kern", 0), jitter.get("kern", 0)))
    stats["missing_chars"] = "".join(sorted(missing_chars))
    return stats, ys


def render_blocks(ink, blocks, book, origin, size, line_height, chars_per_line,
                 rng, jitter, use_fallback=True):
    """blocks: [(文本, 缩进字数)]。缩进按字数右移，不靠空格字符（字库未必有空格字形）。"""
    x0, y0 = origin
    stats = {"hand": 0, "fallback": 0, "missing": 0}
    missing_chars = set()
    li = 0
    for text, indent in blocks:
        for para in str(text).split("\n"):
            if para == "":
                li += 1
                continue
            wrapped = wrap_text(para, max(2, chars_per_line - indent))
            for sub in wrapped:
                y = y0 + li * line_height
                x = x0 + indent * size
                for ch in sub:
                    s = size * (1.0 + rng.uniform(-jitter.get("size", 0), jitter.get("size", 0)))
                    kind = _stamp(ink, ch, book, x, y, s, rng, jitter, use_fallback=use_fallback)
                    stats[kind] = stats.get(kind, 0) + 1
                    if kind == "missing":
                        missing_chars.add(ch)
                    if kind == "hand":
                        adv = book.font(s).getlength(ch)
                    elif book.fallback_path:
                        adv = book.fallback_font(s).getlength(ch)
                    else:
                        adv = s
                    x += adv * (1.0 + rng.uniform(-jitter.get("kern", 0), jitter.get("kern", 0)))
                li += 1
    stats["missing_chars"] = "".join(sorted(missing_chars))
    stats["lines"] = li
    return stats


def composite(paper, ink, color=DEFAULT_INK, alpha=0.92):
    """ink 图层（L，255=满墨）压到纸上。"""
    a = ink.point(lambda v: int(v * alpha))
    layer = Image.new("RGB", paper.size, color)
    return Image.composite(layer, paper, a)


# --------------------------------------------------------------------------
# 作业答题纸
# --------------------------------------------------------------------------

QA_ANSWER_PREFIXES = ("答：", "答:", "答.", "A:", "A：", "答案：", "答案:")


def parse_qa(text):
    """极简解析：支持「1. 题干」+「答：内容」，也支持只有答案的编号段落。

    返回 [{"no": "1", "question": "...", "answer": "..."}]
    """
    import re
    items = []
    cur = None
    buf_q = []
    buf_a = []
    state = None
    for raw in text.split("\n"):
        line = raw.rstrip()
        stripped = line.strip()
        if not stripped:
            continue
        m = re.match(r"^\s*(\d{1,3})\s*[.、)）]\s*(.*)$", line)
        if m and not stripped.startswith(QA_ANSWER_PREFIXES):
            if cur is not None:
                cur["question"] = " ".join(buf_q).strip()
                cur["answer"] = " ".join(buf_a).strip()
                items.append(cur)
            cur = {"no": m.group(1), "question": m.group(2).strip(), "answer": ""}
            buf_q = [m.group(2).strip()] if m.group(2).strip() else []
            buf_a = []
            state = "q"
            continue
        hit = None
        for p in QA_ANSWER_PREFIXES:
            if stripped.startswith(p):
                hit = p
                break
        if hit is not None:
            if cur is None:
                cur = {"no": str(len(items) + 1), "question": "", "answer": ""}
            buf_a.append(stripped[len(hit):].strip())
            state = "a"
            continue
        if cur is None:
            cur = {"no": str(len(items) + 1), "question": "", "answer": ""}
        if state == "a":
            buf_a.append(stripped)
        else:
            buf_q.append(stripped)
    if cur is not None:
        cur["question"] = " ".join(buf_q).strip()
        cur["answer"] = " ".join(buf_a).strip()
        items.append(cur)
    return items


def homework_plan(items, chars_per_line, with_question=False, indent="　　"):
    """把 Q&A 变成 (行文本, 缩进级别) 列表。缩进用全角空格，更像手写。"""
    lines = []
    for it in items:
        if with_question and it.get("question"):
            qline = "%s. %s" % (it["no"], it["question"])
            for sub in wrap_text(qline, chars_per_line):
                lines.append((sub, 0))
        ans = it.get("answer") or ""
        body = "答：%s" % ans if it.get("question") or it.get("no") else ans
        wrapped = wrap_text(body, chars_per_line - 2)
        for i, sub in enumerate(wrapped):
            lines.append((sub, 0 if i == 0 else 1))
        lines.append(("", 0))
    return lines

# --------------------------------------------------------------------------
# 字体预设（assets/presets.json）
# --------------------------------------------------------------------------

PRESET_PATH = H.ASSETS_DIR / "presets.json"


def load_presets():
    """读字体预设。返回 {名字: {...}}。"""
    if not PRESET_PATH.is_file():
        return {}
    try:
        return H.read_json(PRESET_PATH).get("presets", {})
    except Exception:
        return {}


def describe_presets():
    p = load_presets()
    if not p:
        return "（没有找到 %s）" % PRESET_PATH
    width = max(len(k) for k in p) + 2
    lines = ["可用预设（%s）：" % PRESET_PATH]
    for k, v in p.items():
        src = v.get("font_file") or v.get("ttf") or "?"
        lines.append("  %-*s %-22s %s" % (width, k, src, v.get("note", "")))
    return "\n".join(lines)


def resolve_font_spec(spec, base_dir="."):
    """字体描述 → (绝对路径, index)。

    spec 里优先用 ttf（自己生成的字体，相对 base_dir），否则用 font_file
    （系统字体，按文件名在系统目录里找——不写死 AssetsV2 里的 hash 路径，
    因为字体重新下载后 hash 会变）。
    """
    import os
    import sys
    idx = int(spec.get("font_index", 0) or 0)
    ttf = spec.get("ttf")
    if ttf:
        p = ttf if os.path.isabs(ttf) else str(Path(base_dir) / ttf)
        if not Path(p).is_file():
            raise FileNotFoundError("预设里的字体文件不存在：%s" % p)
        return p, idx
    fname = spec.get("font_file")
    if not fname:
        raise ValueError("预设里既没有 ttf 也没有 font_file")
    p = H.find_font_file(fname)
    if p is None:
        # 预设字体（多半是 macOS 自带）在本机不存在时，自动降级到本机可用的中文字体，
        # 保证任何系统上都能出图，只是手写观感差一点。
        try:
            fp, fidx = H.resolve_font(H.CONTENT_FONT_CANDIDATES, "中文字体")
            sys.stderr.write(
                "提示：本机没有字体 %s，已自动改用 %s（手写观感会弱一些）。\n"
                "      想保持原样：安装该字体，或用 --font 指定你自己的字库。\n"
                % (fname, os.path.basename(fp)))
            return fp, fidx
        except FileNotFoundError:
            raise FileNotFoundError(
                "系统里找不到字体 %s，本机也没有可用的中文字体。\n"
                "请安装任一中文字体（如 Noto Sans CJK / 微软雅黑 / 苹方），"
                "或用 --font 指定 .ttf/.ttc 文件。" % fname)
    return p, idx


def apply_preset(args, preset_name, keys, base_dir="."):
    """把预设值填进 args 里那些为 None 的项。命令行显式给的值优先。"""
    presets = load_presets()
    if preset_name not in presets:
        raise KeyError("没有名为 %s 的预设。\n%s" % (preset_name, describe_presets()))
    spec = presets[preset_name]
    for k in keys:
        if getattr(args, k, None) is None and spec.get(k) is not None:
            setattr(args, k, spec[k])
    if getattr(args, "font", None) is None:
        args.font, idx = resolve_font_spec(spec, base_dir)
        if getattr(args, "font_index", None) is None:
            args.font_index = idx
    return spec

