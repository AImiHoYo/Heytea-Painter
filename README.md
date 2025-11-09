# Heytea-Painter
Automatically add drawing elements by extracting edges.
# 使用方法：
运行
`
start.bat
`
点击"加载图片"，选择线条提取方法。
一共有三种边缘检测方式：Pencil Sketch、Canny、Anime2Sketch
三种绘画方式：短行程、只能拖动、仿真人

推荐使用"Anime2Sketch"+"仿真人"的搭配方式

然后就是自己随便捣鼓下参数，确保红色的线条覆盖到线稿，尽量不要让线条出现毛躁，否则会影响绘画效果
一般调整方法是：
1.调整二值化阈值
2.微调最小化轮廓面
3.微调模型敏感度
4.调整线条简化度
5.预览线条粗细调至2（小程序的画笔没有笔压且很粗）
6.抖动修正强度选0或1（太高会很圆润）
7.换线停顿一定要设置到5，否则会自动清屏
