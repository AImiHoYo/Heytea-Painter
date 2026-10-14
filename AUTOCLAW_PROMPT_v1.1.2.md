# 续作：Heytea-Painter v1.1.2（在 v1.1.1 之上，保持可运行）

工作区：/Users/a1234/Projects/Heytea-Painter
先读：VERSION、RELEASE_NOTES.md、ARCHITECTURE_NOTES.md、最近两次 commit。

目标（小版本）：
1. 识图精度：Anime2Sketch 预览缓存（边图复用）对齐 Qt 路径，减少滑条拖动全量重推理
2. 绘制精度：分块路径可配置 cell_size；绘制前路径统计写入日志
3. UI：简单模式文案引导「一键推荐」；缺模型时弹窗/日志更醒目
4. 冒烟：python tests/test_cross_platform.py 全绿
5. VERSION → 1.1.2，更新 RELEASE_NOTES，本地 commit

模型：GLM-5.3 写代码；Flash 看 UI 截图；Auto 做验收总结。
不要迁移 Tauri。不要破坏 macOS 启动。
