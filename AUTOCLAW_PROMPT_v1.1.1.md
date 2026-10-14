# 续作：Heytea-Painter v1.1.1（在 v1.1.0 之上，必须保持可运行）

工作区：/Users/a1234/Projects/Heytea-Painter
先读：VERSION、RELEASE_NOTES.md、ARCHITECTURE_NOTES.md、最近两次 commit、modules/path_planner.py、settings_store、主 UI。

## 模型分工
- Auto：读代码 → 写 ≤12 行计划 → 最终验收总结
- GLM-5.3：实现代码
- GLM-5.3-Flash：若有 UI 截图再看观感（可选）

## 目标（小版本，全部做完再停）
1. 简单/高级模式：真正折叠/隐藏专家参数（CustomTkinter + 若有 Qt/heytea_modern）
2. 识图：LineartAnime / Anime2Sketch 预览与实绘一致性小改进；缺模型时中文友好提示
3. 绘制：path_planner 增加「按包围盒分块再最近邻」；仿真人换线停顿 UI 提示文案
4. 冒烟全绿：`conda run -n heytea-painter python tests/test_cross_platform.py`（或现有 smoke）
5. VERSION → 1.1.1，更新 RELEASE_NOTES.md（中文），本地 git commit（message 含 v1.1.1）
6. 不要 Tauri 迁移；不要破坏 macOS `./start.sh`；不要 force-push

做完输出：改动文件、commit hash、测试结果、启动方式、下一步 3 条建议。现在开始。
