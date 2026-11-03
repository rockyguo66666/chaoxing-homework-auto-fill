#!/usr/bin/env bash
# 把本仓库安装成智能体技能（DeepSeek Harness / Claude Code 等）。
# 用法:
#   bash scripts/install-skill.sh                 # 装到 ~/.dsh/skills 与 ~/.claude/skills
#   bash scripts/install-skill.sh <目标目录>       # 装到指定目录
#
# 已存在同名技能时自动备份成 <目录>.bak-<时间戳>，不覆盖用户正在用的版本。
set -euo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

if [ $# -ge 1 ]; then
  TARGETS=("$@")
else
  TARGETS=()
  mkdir -p "$HOME/.dsh/skills"
  TARGETS+=("$HOME/.dsh/skills/chaoxing-homework")
  mkdir -p "$HOME/.claude/skills"
  TARGETS+=("$HOME/.claude/skills/chaoxing-homework")
fi

for T in "${TARGETS[@]}"; do
  echo "→ 安装到 $T"
  if [ -f "$T/SKILL.md" ]; then
    BAK="$T.bak-$(date +%Y%m%d-%H%M%S)"
    mv "$T" "$BAK"
    echo "  已存在旧版本，备份到 $BAK"
  fi
  mkdir -p "$T"
  cp -R "$SRC/SKILL.md" "$T/"
  cp -R "$SRC/scripts" "$T/"
  cp -R "$SRC/lib" "$T/"
  cp -R "$SRC/bin" "$T/"
  cp -R "$SRC/references" "$T/"
  mkdir -p "$T/skills"
  cp -R "$SRC/skills/handwriting-homework" "$T/skills/"
  rm -rf "$T/skills/handwriting-homework/.venv"
  find "$T" -name '__pycache__' -type d -exec rm -rf {} + 2>/dev/null || true
  chmod +x "$T"/scripts/*.js "$T"/bin/*.js 2>/dev/null || true
  echo "  完成"
done

echo
echo "装好后："
echo "  · 智能体：直接加载该技能目录里的 SKILL.md 即可"
echo "  · 命令行：cd $(basename "$SRC") && npm link   # 之后可直接用 cx 命令"
