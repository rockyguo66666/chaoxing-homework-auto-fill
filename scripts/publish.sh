#!/usr/bin/env bash
# 一键发布到 GitHub（公开仓库）。
# 用法: bash scripts/publish.sh [仓库名]
#   仓库名默认用中文「学习通作业自动化填写」；若 GitHub 不接受非 ASCII 名字，
#   自动回退到 chaoxing-homework-auto-fill，并把中文名写进仓库简介。
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SRC"

PROXY="${CX_PROXY:-http://127.0.0.1:7897}"
export https_proxy="$PROXY" http_proxy="$PROXY"
git config http.proxy "$PROXY"

NAME="${1:-学习通作业自动化填写}"
SLUG="$NAME"
if ! printf '%s' "$NAME" | LC_ALL=C grep -qE '^[A-Za-z0-9._-]+$'; then
  SLUG="chaoxing-homework-auto-fill"
  echo "提示：GitHub 仓库名只接受 ASCII 字母/数字/.-_，改用 $SLUG（中文名写入仓库简介）"
fi

echo "==> 检查登录态"
gh auth status >/dev/null 2>&1 || { echo '未登录：请先执行 gh auth login'; exit 2; }
USER="$(gh api user --jq .login)"
echo "  已登录：$USER"

echo "==> 创建公开仓库 $SLUG"
if gh repo view "$USER/$SLUG" >/dev/null 2>&1; then
  echo "  仓库已存在，直接用"
else
  gh repo create "$SLUG" --public --description "$NAME：学习通(超星)作业自动化 —— 扫描未交作业、抓题、按题型分流作答(选择直填/物理数学出手写答题纸/长解答直接打字)、只暂存不提交；附模拟笔迹渲染管线" --source=. --remote=origin >/dev/null
  echo "  已创建"
fi

echo "==> 推送"
git push -u origin main

echo
echo "完成：https://github.com/$USER/$SLUG"
