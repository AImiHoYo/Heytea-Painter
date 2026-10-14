# Heytea Painter — Windows 便携包使用说明

解压后即可使用（无需安装程序）。本包**不含** AI 模型权重。

## 快速开始

### A. 一键环境包（zip 内已有 `env\`）

1. 解压到任意英文或中文路径（避免极端特殊字符）。
2. 下载 `netG.pth`，放到本目录的 `models\` 下（见下方「模型」）。
3. 双击 `start.bat` 启动。一键包已带上与嵌入式 Python 同版本的 Tcl/Tk，备用 CustomTkinter 界面可以导入。

### B. 引导包（zip 内没有 `env\`）

1. 安装 [Python 3.10+](https://www.python.org/downloads/)，勾选 **Add Python to PATH**。
2. 双击 `setup_env.bat`，等待依赖安装完成（约 5–10 分钟，含 PyTorch CPU）。
3. 下载 `netG.pth` 放到 `models\`。
4. 双击 `start.bat`。

也可使用本机已安装的 Miniconda：创建名为 `heytea-painter` 的环境后，直接运行 `start.bat`。

## 模型（必做）

Anime2Sketch 需要 `models\netG.pth`（体积较大，不随本包分发）。

- 项目说明：[Anime2Sketch](https://github.com/Mukosame/Anime2Sketch)
- 直接下载（Google Drive）：[netG.pth](https://drive.google.com/file/d/1cf90_fPW-elGOKu5mTXT5N1dum-XY_46/view)
- 或从 Anime2Sketch Release / 网盘获取后，**重命名为 `netG.pth`** 放入 `models\`

LineartAnime 可在首次使用时由 `huggingface_hub` 自动下载到 `models\lineart_anime.pth`（需联网）。

## 启动入口

| 方式 | 说明 |
|------|------|
| `start.bat` | 推荐：启动正式 Qt 界面（`heytea_qt.py`） |
| `env\python.exe heytea_modern.py` | 备用 CustomTkinter 界面 |

建议系统 **DPI 缩放 100%**；过高缩放可能导致绘画区域无法完全覆盖画布。

## 常见问题

- **提示找不到 Python / env**：引导包请先运行 `setup_env.bat`；一键包请确认 `env\python.exe` 存在且未被杀软隔离。
- **提示找不到 netG.pth**：按上方说明放入 `models\netG.pth` 后重试。
- **杀毒软件拦截**：PyAutoGUI / 键鼠模拟可能被误报，请将解压目录加入白名单。
