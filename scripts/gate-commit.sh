#!/usr/bin/env bash
# ゲートが通った時だけ commit する（「ゲート付き commit」を機構にする）。
# 使い方: bash scripts/gate-commit.sh <commit-message-file>
# 背景: gate.sh の後ろに echo/grep を挟んだ手連鎖で && の起点がずれ、ゲート失敗のまま commit が
# 通った事故が 2026-09-30 に起きた（同型の事故は通算 4 回目）。ゲートと commit を 1 本にする。
set -euo pipefail
cd "$(dirname "$0")/.."
[ -f "${1:-}" ] || { echo "usage: bash scripts/gate-commit.sh <commit-message-file>" >&2; exit 2; }
bash scripts/gate.sh
git add -A
git commit -F "$1"
git log --oneline -1
