# 任务：Heytea-Painter 今晚迭代 v1.1.0（必须保持可运行）

你是 AutoClaw 工程 Agent。工作目录优先：`/Users/a1234/Projects/Heytea-Painter`（GitHub：https://github.com/AImiHoYo/Heytea-Painter）。若项目「heytea」已绑定该源，就在该工作区直接改。

## 目标（产品）
打造更好用、识图更准、绘画更准的喜茶线稿绘制工具；界面简洁、小白友好；向多平台适配推进；代码质量可读可测。今晚只交付 **一个小版本 v1.1.0**，必须仍能启动、预览、走完标定流程（缺模型时可降级提示，不能崩）。

## 模型使用（请在 AutoClaw 内按任务切换）
1. 用 **Auto** 先读仓库结构、`README`、`modules/*`、`scripts/smoke_check.py`、`VERSION`，输出实现计划（≤15 行）。
2. 用 **GLM-5.3** 实现代码改动。
3. 若涉及界面观感/预览对比，用 **GLM-5.3-Flash** 看截图辅助。
4. 最后用 **Auto** 跑验收清单并写 `RELEASE_NOTES.md` / bump `VERSION`。

## 架构约束（重要）
- **今晚不要** 迁移到 Tauri/React。保留 CustomTkinter 主壳。
- 借鉴现代架构的**思想**写入代码边界即可：
  - `modules/platform_input.py`：跨平台鼠标/键盘抽象（Windows 保留 pydirectinput；macOS 用 Quartz/CGEvent 或 pynput；Linux 用 pynput）
  - `modules/path_planner.py`（或扩展 contour_optimizer）：行程排序、减少无效换线、默认安全换线停顿
  - UI：默认「简单模式」+「高级参数」折叠；推荐预设一键应用（Anime2Sketch + 仿真人 + 预览粗细 2 + 换线停顿 ≥5000）
- 参考笔记已放在同目录 `ARCHITECTURE_NOTES.md`（若没有，按上文理解执行）。

## 必须完成的交付物
1. `VERSION` → `1.1.0`
2. 更新 `RELEASE_NOTES.md`（中文，写清变更/已知问题）
3. 代码改动通过现有/扩展冒烟：`python scripts/smoke_check.py`（若路径不同以仓库为准）
4. macOS：`start.sh` / `start.command` 能启动到主窗口（即便绘制后端是 stub/可探测）
5. Windows 行为不回归（条件导入，禁止在非 Windows 直接 `ctypes.windll` 炸掉）
6. Git：在本地提交清晰 commit（message 含 `v1.1.0`）；若有权限再 push；不要强推
7. 结束时输出：改动文件列表、如何启动、验收结果、下一步 v1.1.1 建议（3 条）

## 验收清单
- [ ] 无模型时 Anime2Sketch 有可读错误提示，其它模式仍可用
- [ ] 简单模式默认参数安全（换线停顿不会是 0）
- [ ] 非 Windows 启动不因 windll/pydirectinput 崩溃
- [ ] smoke_check 通过
- [ ] UI 文案对小白友好（中文为主）

现在开始：先读代码再改，小步提交，做完停在可运行状态。
