#!/usr/bin/env bash
# 依赖准备：一条命令装好全部依赖（Node 依赖 + 浏览器 + Python 渲染依赖）。
# 用法: bash scripts/setup.sh
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$SRC"
RUNTIME="${CX_HOME:-$HOME/.chaoxing-homework}"

echo "==> 1/3 检查 node / python3"
command -v node >/dev/null || { echo '缺少 node，请先装 Node.js 18+'; exit 1; }
command -v python3 >/dev/null || echo '  提示：没找到 python3，模拟笔迹渲染将不可用（选择/打字作答不受影响）'
node -v

echo "==> 2/3 安装 Node 依赖"
mkdir -p "$RUNTIME"

# 2a) 共享运行目录：playwright 装在这里。装成技能后技能目录本身零依赖，多份安装共享同一份。
if [ -d "$RUNTIME/node_modules/playwright" ]; then
  echo "  共享运行目录已有 playwright，跳过（$RUNTIME/node_modules）"
else
  npm install --prefix "$RUNTIME" --no-audit --no-fund playwright
fi

# 2b) 仓库自身依赖（CLI 用）
if [ -d node_modules/playwright ]; then
  echo "  仓库依赖已就绪，跳过"
else
  npm install --no-audit --no-fund
fi

# 2c) 浏览器二进制（Playwright 缓存目录全局共享，只需一次）
if [ ! -d "$HOME/Library/Caches/ms-playwright" ] && [ ! -d "$HOME/.cache/ms-playwright" ]; then
  echo "  下载浏览器…"
  ( npx --prefix "$RUNTIME" playwright install chromium \
    || npx playwright install chromium \
    || echo '  （下载失败；可用系统 Chrome/Edge，设 CX_CHANNEL=chrome 或 msedge）' )
fi

echo "==> 3/3 环境自检"
node scripts/doctor.js

echo
echo "准备完成。接下来："
echo "  1) bash scripts/install-skill.sh      # 把本文件夹装成 DSH 技能"
echo "  2) node scripts/relogin.js           # 扫码登录学习通"
