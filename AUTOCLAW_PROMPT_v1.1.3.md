# 续作：Heytea-Painter v1.1.3（在 v1.1.2 之上，保持可运行）

工作区：/Users/a1234/Projects/Heytea-Painter
先读：VERSION、RELEASE_NOTES.md、ARCHITECTURE_NOTES.md、最近两次 commit。

目标（小版本）：
1. 识图：LineartAnime 与 Anime2Sketch 预览缓存命中率日志；可选「强制重推理」按钮
2. 绘制：分块策略可视化（预览上淡色网格）可选开关
3. UI：简单模式隐藏提取方法中的 Pencil/Canny（或灰显并提示用一键推荐）
4. 冒烟全绿；VERSION → 1.1.3；本地 commit

不要迁移 Tauri。不要破坏 macOS 启动。
