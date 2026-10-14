#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
CONDA_ROOT="${CONDA_ROOT:-/Users/a1234/Projects/miniconda3}"

echo "===================================="
echo "Heytea Painter"
echo "===================================="
echo

if [[ ! -x "$CONDA_ROOT/bin/conda" ]]; then
  echo "[ERROR] 未找到 Miniconda: $CONDA_ROOT"
  echo "请先安装 Miniconda，或设置 CONDA_ROOT"
  exit 1
fi

# shellcheck disable=SC1091
source "$CONDA_ROOT/etc/profile.d/conda.sh"
conda activate heytea-painter

cd "$ROOT"

if [[ ! -f "$ROOT/models/netG.pth" ]]; then
  echo "[WARN] 未找到 models/netG.pth，Anime2Sketch 将不可用"
  echo "      可从 Anime2Sketch 下载后放到 models/ 目录"
  echo
fi

if [[ "$(uname -s)" == "Darwin" ]]; then
  echo "[INFO] macOS 需要给终端 / Python 开启「辅助功能」权限才能控制鼠标"
  echo "      系统设置 → 隐私与安全性 → 辅助功能"
  echo
fi

echo "[INFO] 启动 Heytea Painter..."
python "$ROOT/heytea_modern.py"
