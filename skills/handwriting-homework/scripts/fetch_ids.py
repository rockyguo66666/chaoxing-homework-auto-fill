#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""fetch_ids.py —— 下载汉字部件分解表（IDS，表意文字描述序列）。

用途：某个字你没写过，但它的部件你写过（比如你写过「日」和「月」，
要写「明」），compose.py 就能用你的真迹部件拼出来。

数据来源：cjkvi-ids（基于 CHISE IDS 数据库）。国内直连 GitHub 常失败，
所以按 jsDelivr → GitHub → 镜像 的顺序依次尝试。

用法
----
  python3 fetch_ids.py --out data/ids.txt
  python3 fetch_ids.py --from-file /path/to/ids.txt --out data/ids.txt
"""

from __future__ import annotations

import argparse
import shutil
import sys
import urllib.request
from pathlib import Path

MIRRORS = [
    "https://cdn.jsdelivr.net/gh/cjkvi/cjkvi-ids@master/ids.txt",
    "https://raw.githubusercontent.com/cjkvi/cjkvi-ids/master/ids.txt",
    "https://ghproxy.net/https://raw.githubusercontent.com/cjkvi/cjkvi-ids/master/ids.txt",
    "https://raw.gitmirror.com/cjkvi/cjkvi-ids/master/ids.txt",
]


def download(url, dest, timeout=60):
    req = urllib.request.Request(url, headers={"User-Agent": "handwriting-homework/1.0"})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        data = resp.read()
    if len(data) < 100000:
        raise ValueError("内容太小（%d 字节），不像 IDS 表" % len(data))
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(data)
    return len(data)


def main(argv=None):
    ap = argparse.ArgumentParser(description="下载 IDS 部件分解表")
    ap.add_argument("--out", default="data/ids.txt")
    ap.add_argument("--from-file", default=None, help="已有副本，直接拷贝")
    args = ap.parse_args(argv)
    dest = Path(args.out)

    if args.from_file:
        shutil.copyfile(args.from_file, dest)
        print("已拷贝 %s → %s" % (args.from_file, dest))
        return 0

    for url in MIRRORS:
        print("尝试 %s ..." % url)
        try:
            n = download(url, dest)
        except Exception as e:
            print("  失败：%s" % e, file=sys.stderr)
            continue
        print("成功：%s（%.1f MB）" % (dest, n / 1048576.0))
        return 0
    print("全部镜像都失败。可以手动下载 ids.txt 后用 --from-file 指定。", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
