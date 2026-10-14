#!/usr/bin/env bash
set -euo pipefail

ROOT="$(cd "$(dirname "$0")" && pwd)"
CONDA_ROOT="${CONDA_ROOT:-/Users/a1234/Projects/miniconda3}"

echo "===================================="
echo "Heytea Painter - 环境安装"
echo "===================================="
echo

if [[ ! -x "$CONDA_ROOT/bin/conda" ]]; then
  echo "[ERROR] 未找到 Miniconda: $CONDA_ROOT"
  exit 1
fi

# shellcheck disable=SC1091
source "$CONDA_ROOT/etc/profile.d/conda.sh"

if conda env list | awk '{print $1}' | grep -qx "heytea-painter"; then
  echo "[INFO] 环境已存在: heytea-painter"
else
  echo "[INFO] 创建 conda 环境 heytea-painter..."
  conda create -n heytea-painter python=3.10 pip --override-channels -c conda-forge -y
fi

conda activate heytea-painter
python -m pip install --upgrade pip
python -m pip install \
  customtkinter==5.2.2 \
  pyside6==6.7.3 \
  opencv-contrib-python==4.8.1.78 \
  numpy==1.24.3 \
  pillow==10.1.0 \
  torch==2.1.0 \
  torchvision==0.16.0 \
  scipy==1.11.4 \
  pynput==1.7.6 \
  huggingface_hub==0.25.2

if [[ "$(uname -s)" == "MINGW"* || "$(uname -s)" == "CYGWIN"* ]]; then
  python -m pip install pydirectinput==1.0.4 keyboard==0.13.5 || true
fi

echo
echo "安装完成。启动: ./start.sh"
echo "激活环境: conda activate heytea-painter"
