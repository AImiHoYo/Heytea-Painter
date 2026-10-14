#!/usr/bin/env bash
# 双击此文件即可启动 Heytea Painter（会打开「终端」窗口）

set -u

ROOT="$(cd "$(dirname "$0")" && pwd)"
cd "$ROOT" || exit 1

"$ROOT/start.sh"
STATUS=$?

echo
if [[ $STATUS -ne 0 ]]; then
  echo "[ERROR] 程序异常退出，错误代码: $STATUS"
else
  echo "程序已退出。"
fi
echo
read -r -p "按回车关闭窗口..."
exit "$STATUS"
