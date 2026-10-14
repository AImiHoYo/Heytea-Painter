# Heytea-Painter 架构调研纪要（2026-10-14）

## 现状（仓库 https://github.com/AImiHoYo/Heytea-Painter）
- 栈：Python 3.10 + CustomTkinter + OpenCV + PyTorch(Anime2Sketch) + pydirectinput/pynput（鼠标自动绘制）
- 入口：`heytea_modern.py`（正式），`main.py` 兼容
- 模块：`image_processor` / `contour_optimizer` / `drawing_engine` / `ui_*`
- 版本：`VERSION=1.0.0`，Windows 首发，macOS 启动脚本已有但绘制输入层偏 Windows
- 产品定位：把图片提成线稿，再在喜茶小程序画布上「仿真人」自动描线

## 现代同类架构可借鉴点（不Tonight 全盘重写）
1. **Painting Droid / Brick.Draw / Paintlet**：React+TS UI + Zustand + Canvas/OffscreenCanvas + **Tauri 2** 桌面壳；重计算进 Rust/WASM。适合远期多平台，不适合今晚。
2. **Napkin**：Tauri+React+Konva，**Zustand 分店 + Zundo 撤销**；注释坐标放在图像空间再缩放。可借鉴「状态切片 + 命令式撤销」。
3. **Taurisight / PictoPy**：本地视觉推理（TF.js / YOLO+ONNX）与 UI 解耦。可借鉴「识图管线独立、可换后端」。
4. **Galileo / Tela / Varve**：文档模型 + Command 历史 + 双渲染路径（编辑预览 vs 导出）。对「线稿→笔迹路径」可映射成 **Stroke Graph / Path Planner** 层。
5. AutoClaw 内置 skill：`frontend-page-design`（偏落地页，不适合本产品主 UI）、`find-skills`（可用 `npx skills find` 继续扩）。

## 推荐演进路线（小版本可运行）
- **v1.1.x（今晚）**：在现有 CustomTkinter 上做「可用性+精度」小迭代，**不换壳**。
  - 跨平台输入抽象（Win / macOS / Linux）
  - 小白模式：默认 Anime2Sketch + 仿真人，高级参数折叠
  - 路径规划：更好的行程排序、换线停顿安全默认
  - 冒烟测试保持绿，版本号 bump
- **v1.2.x**：识图精度（自适应阈值、轮廓骨架回退质量、预览与实绘一致性指标）
- **v1.3.x**：绘制精度（DPI/坐标系、压感模拟、断笔策略）
- **v2.0**：评估 Tauri+共享 Python/ONNX 识图服务（多平台壳），仅在 v1.x 稳定后启动

## AutoClaw 模型分工建议
- **GLM-5.3**：主工程实现 / 重构 / 调试（长程）
- **GLM-5.3-Flash**：看截图、UI 走查、读图对比预览
- **Auto**：编排拆任务、写 changelog、跑检查清单
