# Release Notes — v1.1.4

## 变更摘要
- **Windows 便携 zip 打包**：新增 `packaging/` 脚本与 `portable-windows` CI，可产出引导包（bootstrap）与一键包（embeddable Python + `env\`）
- GitHub Releases 可直接下载 Windows 便携 zip（非安装程序）；模型权重仍需自行放入 `models\netG.pth`
- `start.bat`：兼容 `env\python.exe`（嵌入式）与 `env\Scripts\python.exe`（venv）；默认启动正式 Qt 入口 `heytea_qt.py`
- `setup_env.bat`：补齐 Windows 键鼠依赖（`pynput` / `pydirectinput` / `keyboard`）
- **一键包补齐 Tcl/Tk**：官方 embeddable Python 不含 tkinter；打包时从同版本 `tcltk.msi` 放入 `env\`（`_tkinter.pyd`、`tcl86t.dll`、`tk86t.dll`、`tcl\`、`Lib\tkinter`），`customtkinter` 可导入。`start.bat` 在存在该目录时设置 `TCL_LIBRARY` / `TK_LIBRARY`

## 已知问题
- 首次加载模型仍需等待；缓存仅在同图同推理键下有效（沿用 v1.1.2）
- 强制重推理只清边图缓存，模型本身仍常驻（属预期）
- 一键 zip 体积较大（含 CPU PyTorch），CI 仅在 `v*` 标签或手动 workflow 构建

## 升级注意事项
- Windows：从 [Releases](https://github.com/AImiHoYo/Heytea-Painter/releases) 下载便携 zip → 解压 → 放置 `models\netG.pth` → `start.bat`
- 引导包需先运行 `setup_env.bat`（需本机 Python 3.10+）
- 网盘一键包仍可用作备选（见 README）
