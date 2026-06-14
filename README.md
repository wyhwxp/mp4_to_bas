# mp4\_to\_bas

mp4 转 bilibili BAS 弹幕

这是一个可以把 mp4 视频转为 bilibili 的 BAS 弹幕的脚本（生成 10 帧/s 的视频脚本）。

## 使用方法

1. 双击运行 `install_deps.bat` 安装依赖库
2. 运行 `video_to_bas.py`，复制 mp4 文件绝对路径粘贴进去
3. 生成 txt 文件，与原视频在同一文件夹下
4. 使用`split_bas.py`切割（单文件约300000字节），以绕过b站的对于代码bas弹幕的封禁

## Tips

- [x] 生成时间较长，每处理 10 帧反馈一次进度

## 目前的局限性

- 无法调整生成脚本帧率
- 目前无法保证视频一定居中
- 全程 DeepSeek 完成，人工调试修改

