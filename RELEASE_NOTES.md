# Release Notes Template

## 变更摘要
- UI 架构拆分为布局层、组件层、状态层
- 预览处理链路异步化并增加参数签名去重
- 预设加载增加兼容归一化与异常回退
- CI 增加构建前冒烟校验并支持 tag 自动发布

## 已知问题
- 首次加载 Anime2Sketch 模型仍会有明显等待时间
- 骨架提取在缺少 OpenCV ximgproc 时会自动回退到“所有轮廓”

## 升级注意事项
- 正式入口为 `heytea_modern.py`，`main.py` 仅为兼容入口
- 发布版本号由 `VERSION` 文件维护，发布标签建议使用 `vX.Y.Z`
