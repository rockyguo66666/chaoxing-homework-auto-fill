#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""compose.py —— 部件拼接：用你写过的部件，拼出你没写过的字。

适用场景：作业里有个别字你没写进采样纸。如果这个字的部件你写过，
就用**你的真迹部件**按结构拼出来，比用楷体顶替像得多。

数据来源（按优先级）：
  1. --decompose 指定的文件（Agent 可以当场手写，格式：字<TAB>IDS，或 U+XXXX<TAB>字<TAB>IDS）
  2. --ids 指定的 IDS 表（fetch_ids.py 下载的 cjkvi-ids）

诚实声明：拼出来的字会写进 data/composed.json。render.py 会把
「真迹 / 拼接 / 顶替」三类字分别报给你，不要把拼接字当成你真写的。

用法
----
  python3 compose.py --data data/ --targets "明暗国" --out data/
  python3 compose.py --data data/ --from-text 作业.txt --ids data/ids.txt --out data/
  python3 compose.py --data data/ --targets "明" --decompose 手写分解.txt --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image

import handlib as H

OPERATORS = "⿰⿱⿲⿳⿴⿵⿶⿷⿸⿹⿺⿻"
ARITY = {"⿰": 2, "⿱": 2, "⿲": 3, "⿳": 3, "⿴": 2, "⿵": 2, "⿶": 2,
         "⿷": 2, "⿸": 2, "⿹": 2, "⿺": 2, "⿻": 2}

# 各结构下每个部件占的子框（x0, y0, x1, y1，0..1），以及内层缩放
LAYOUTS = {
    "⿰": [(0.00, 0.06, 0.48, 0.96), (0.52, 0.06, 1.00, 0.96)],
    "⿱": [(0.06, 0.00, 0.94, 0.48), (0.06, 0.52, 0.94, 1.00)],
    "⿲": [(0.00, 0.08, 0.32, 0.94), (0.34, 0.08, 0.66, 0.94), (0.68, 0.08, 1.00, 0.94)],
    "⿳": [(0.08, 0.00, 0.92, 0.32), (0.08, 0.34, 0.92, 0.66), (0.08, 0.68, 0.92, 1.00)],
}
INNER = {  # 包围结构：外框全尺寸，内心按比例居中/偏移
    "⿴": (0.58, 0.50, 0.50),
    "⿵": (0.62, 0.52, 0.58),
    "⿶": (0.62, 0.52, 0.42),
    "⿷": (0.58, 0.42, 0.50),
    "⿸": (0.66, 0.62, 0.60),
    "⿹": (0.66, 0.38, 0.60),
    "⿺": (0.66, 0.62, 0.40),
    "⿻": (1.00, 0.50, 0.50),
}


# --------------------------------------------------------------------------
# IDS 解析
# --------------------------------------------------------------------------

def parse_ids(s, pos=0):
    """把 IDS 串解析成嵌套元组。容忍括号注释与占位符。失败返回 None。"""
    if pos >= len(s):
        return None
    ch = s[pos]
    if ch in OPERATORS:
        k = ARITY[ch]
        parts = []
        p = pos + 1
        for _ in range(k):
            got = parse_ids(s, p)
            if got is None:
                return None
            node, p = got
            parts.append(node)
        if len(parts) < 2:
            return None
        return (ch, parts), p
    if ch in "([":
        close = ")" if ch == "(" else "]"
        depth = 0
        for i in range(pos, len(s)):
            if s[i] in "([":
                depth += 1
            elif s[i] in ")]":
                depth -= 1
                if depth == 0:
                    return ("?", []), i + 1
        return None
    if ch in ")|]?*":
        return None
    return ("leaf", ch), pos + 1


def load_ids(path):
    m = {}
    p = Path(path)
    if not p.is_file():
        return m
    for line in p.read_text(encoding="utf-8", errors="ignore").split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 2:
            continue
        key = parts[0].strip()
        if key.startswith("U+"):
            try:
                ch = chr(int(key[2:], 16))
            except ValueError:
                continue
            ids = parts[-1].strip()
        else:
            ch = key[0]
            ids = parts[-1].strip()
        if ids and ids != ch and ids != key:
            m[ch] = ids
    return m


# --------------------------------------------------------------------------
# 拼接
# --------------------------------------------------------------------------

def fit_into(mask, box, canvas=512):
    """把 mask 等比放进 box=(x0,y0,x1,y1)（0..1 比例），返回 canvas 大小的掩码。"""
    crop, ok = H.crop_to_content(mask, min_area=4)
    if not ok:
        return np.zeros((canvas, canvas), dtype=bool)
    x0 = int(round(box[0] * canvas)); y0 = int(round(box[1] * canvas))
    x1 = int(round(box[2] * canvas)); y1 = int(round(box[3] * canvas))
    bw = max(2, x1 - x0); bh = max(2, y1 - y0)
    h, w = crop.shape
    s = min(bw / float(w), bh / float(h))
    nw, nh = max(1, int(round(w * s))), max(1, int(round(h * s)))
    im = Image.fromarray((crop.astype(np.uint8) * 255), mode="L").resize((nw, nh), Image.LANCZOS)
    small = (np.asarray(im, dtype=np.float32) / 255.0) > 0.45
    out = np.zeros((canvas, canvas), dtype=bool)
    ox = x0 + (bw - nw) // 2
    oy = y0 + (bh - nh) // 2
    ox = max(0, min(canvas - nw, ox)); oy = max(0, min(canvas - nh, oy))
    out[oy:oy + nh, ox:ox + nw] = small
    return out


class Composer:
    def __init__(self, real, ids_map, content_font, canvas=512, max_depth=4):
        self.real = real                      # 字 -> 掩码（用户真迹）
        self.ids = ids_map
        self.content_font = content_font      # (path, index)
        self.canvas = canvas
        self.max_depth = max_depth
        self.cache = {}
        self.provenance = {}
        self._font_cache = {}

    def _font(self, size):
        f = self._font_cache.get(size)
        if f is None:
            f = H.load_pil_font(self.content_font[0], size, self.content_font[1])
            self._font_cache[size] = f
        return f

    def content_mask(self, ch):
        """用楷体渲染部件，作为最后兜底。"""
        from PIL import ImageDraw
        f = self._font(int(self.canvas * 0.80))
        im = Image.new("L", (self.canvas, self.canvas), 0)
        bbox = f.getbbox(ch)
        if bbox is None or bbox[2] <= bbox[0] or bbox[3] <= bbox[1]:
            return None
        x = (self.canvas - (bbox[2] - bbox[0])) / 2 - bbox[0]
        y = (self.canvas - (bbox[3] - bbox[1])) / 2 - bbox[1]
        ImageDraw.Draw(im).text((x, y), ch, font=f, fill=255)
        arr = (np.asarray(im, dtype=np.float32) / 255.0) > 0.5
        if arr.sum() < 20:
            return None
        return arr

    def render(self, ch, depth=0):
        """返回 (掩码, 来源)，来源 ∈ real/mixed/synthetic/None。"""
        if ch in self.cache:
            return self.cache[ch], self.provenance.get(ch, "synthetic")
        if ch in self.real:
            self.cache[ch] = self.real[ch]; self.provenance[ch] = "real"
            return self.real[ch], "real"
        if depth >= self.max_depth:
            return None, "none"
        ids = self.ids.get(ch)
        node = None
        if ids:
            parsed = parse_ids(ids)
            if parsed:
                node = parsed[0]
        if node is None or node[0] != "leaf":
            if node is None:
                # 没有分解信息：用楷体整体兜底（来源记 synthetic）
                m = self.content_mask(ch)
                if m is not None:
                    self.cache[ch] = m; self.provenance[ch] = "synthetic"
                    return m, "synthetic"
                return None, "none"
        op, parts = node
        if op == "leaf":
            m = self.content_mask(parts[0]) if parts else None
            if m is None:
                return None, "none"
            return m, "synthetic"

        sub_masks = []
        kinds = []
        for sub in parts:
            if sub[0] == "leaf":
                s = sub[1]
                m, k = self.render(s, depth + 1)
            else:
                m = self._render_node(sub, depth + 1)
                k = "mixed"
            if m is None:
                return None, "none"
            sub_masks.append(m)
            kinds.append(k)

        canvas = self.canvas
        out = np.zeros((canvas, canvas), dtype=bool)
        if op in LAYOUTS:
            boxes = LAYOUTS[op]
            for m, box in zip(sub_masks, boxes):
                out |= fit_into(m, box, canvas)
        elif op in INNER:
            scale, ix, iy = INNER[op]
            out |= fit_into(sub_masks[0], (0.02, 0.02, 0.98, 0.98), canvas)
            half = scale / 2.0
            box = (ix - half, iy - half, ix + half, iy + half)
            box = (max(0.0, box[0]), max(0.0, box[1]), min(1.0, box[2]), min(1.0, box[3]))
            out |= fit_into(sub_masks[1], box, canvas)
        else:
            return None, "none"

        if out.sum() < 30:
            return None, "none"
        kind = "real" if all(k == "real" for k in kinds) else (
            "mixed" if any(k in ("real", "mixed") for k in kinds) else "synthetic")
        self.cache[ch] = out
        self.provenance[ch] = kind
        return out, kind

    def _render_node(self, node, depth):
        op, parts = node
        if op == "leaf":
            return self.render(parts[1] if len(parts) > 1 else parts[0], depth)[0]
        subs = []
        for sub in parts:
            if sub[0] == "leaf":
                subs.append(self.render(sub[1], depth + 1)[0])
            else:
                subs.append(self._render_node(sub, depth + 1))
        if any(s is None for s in subs):
            return None
        out = np.zeros((self.canvas, self.canvas), dtype=bool)
        if op in LAYOUTS:
            for m, box in zip(subs, LAYOUTS[op]):
                out |= fit_into(m, box, self.canvas)
        elif op in INNER:
            scale, ix, iy = INNER[op]
            out |= fit_into(subs[0], (0.02, 0.02, 0.98, 0.98), self.canvas)
            half = scale / 2.0
            box = (max(0.0, ix - half), max(0.0, iy - half),
                   min(1.0, ix + half), min(1.0, iy + half))
            out |= fit_into(subs[1], box, self.canvas)
        else:
            return None
        return out if out.sum() >= 30 else None


def main(argv=None):
    ap = argparse.ArgumentParser(description="部件拼接补齐未写过的字")
    ap.add_argument("--data", default="data")
    ap.add_argument("--out", default=None, help="输出目录（默认与 --data 相同）")
    ap.add_argument("--ids", default=None, help="IDS 表路径（默认 data/ids.txt）")
    ap.add_argument("--decompose", default=None, help="临时分解表（优先于 --ids）")
    ap.add_argument("--targets", default=None, help="要补的字")
    ap.add_argument("--from-text", default=None, help="从这篇文本里找出要补的字")
    ap.add_argument("--dry-run", action="store_true", help="只报告，不落盘")
    ap.add_argument("--radius", type=int, default=2, help="只处理缺少部件数不超过 N 的字")
    args = ap.parse_args(argv)

    data = Path(args.data)
    out = Path(args.out) if args.out else data
    mask_dir = data / "glyphs_mask"
    if not mask_dir.is_dir():
        print("找不到 %s（先跑 preprocess.py）" % mask_dir, file=sys.stderr)
        return 2

    real = {}
    for p in sorted(mask_dir.glob("*.png")):
        stem = p.stem
        ch = None
        import re
        m = re.match(r"^u([0-9A-Fa-f]{4,6})(?:_\d+)?$", stem)
        if m:
            ch = chr(int(m.group(1), 16))
        else:
            m2 = re.match(r"^(.)(?:_\d+)?$", stem, re.UNICODE)
            if m2:
                ch = m2.group(1)
        if ch:
            real.setdefault(ch, H.load_glyph_mask(p))

    ids_map = {}
    if args.decompose:
        ids_map.update(load_ids(args.decompose))
    ids_path = Path(args.ids) if args.ids else (data / "ids.txt")
    if ids_path.is_file():
        ids_map.update(load_ids(ids_path))

    if args.targets:
        targets = H.unique_chars(args.targets)
    elif args.from_text:
        targets = H.unique_chars(Path(args.from_text).read_text(encoding="utf-8"))
    else:
        targets = sorted(ids_map.keys())

    todo = [c for c in targets if c not in real]
    if not todo:
        print("没有需要补的字：目标字你全都写过。")
        return 0

    cfont = H.content_font()
    comp = Composer(real, ids_map, cfont)
    made, failed = {}, {}
    for ch in todo:
        m, kind = comp.render(ch, 0)
        if m is None:
            failed[ch] = "无分解信息，部件也没写过"
            continue
        made[ch] = (m, kind)

    by_kind = {}
    for ch, (_, k) in made.items():
        by_kind.setdefault(k, []).append(ch)

    print("需要补 %d 个字，成功 %d，失败 %d" % (len(todo), len(made), len(failed)))
    for k in ("real", "mixed", "synthetic"):
        if by_kind.get(k):
            print("  %-9s %d 个：%s" % (
                {"real": "真迹部件", "mixed": "混合", "synthetic": "纯楷体"}[k],
                len(by_kind[k]), "".join(by_kind[k])[:60]))
    if failed:
        print("  失败：%s" % "".join(failed.keys())[:60])

    if args.dry_run:
        return 0

    (out / "glyphs_mask").mkdir(parents=True, exist_ok=True)
    (out / "glyphs").mkdir(parents=True, exist_ok=True)
    composed_path = out / "composed.json"
    composed = H.read_json(composed_path) if composed_path.is_file() else {"chars": {}, "order": []}
    for ch, (m, kind) in made.items():
        H.save_mask_png(m, out / "glyphs_mask" / ("%s.png" % ch))
        H.mask_to_rgba(m, color=(30, 30, 60)).save(out / "glyphs" / ("%s.png" % ch))
        composed["chars"][ch] = {"kind": kind}
        if ch not in composed["order"]:
            composed["order"].append(ch)
    H.write_json(composed_path, composed)
    print("已写入 %s（%d 个拼接字）" % (composed_path, len(made)))
    print("提示：这些字不是你的真迹，render.py 会把它们单独列出来。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
