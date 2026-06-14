# mp4\_to\_bas

mp4 转 bilibili BAS 弹幕

这是一个可以把 mp4 视频转为 bilibili 的 BAS 弹幕的脚本（生成 10 帧/s 的视频脚本）。

## 使用方法

1. 双击运行 `install_deps.bat` 安装依赖库
2. 运行 `video_to_bas.py`，复制 mp4 文件绝对路径粘贴进去
3. 生成 txt 文件，与原视频在同一文件夹下
4. 使用`split_bas.py`切割（单文件约300000字节），以绕过b站的对于代码bas弹幕的封禁

## 关于直接发送bas弹幕显示接口错误

> U993：小伙伴目前BAS弹幕因为有部分安全性的原因己经移除该功能啦\~之前的留存弹幕还是正常显示，但是目前无法进行发送，还请您理解下\~

但是，经过测试，单页面300000字以内的bas代码可以发送（不论path/text）

详情：【精准空降到 00:10】 <https://www.bilibili.com/video/BV1c4x7ezEVa/?share_source=copy_web&vd_source=5eefa811b68327201c83017ccd98253f&t=10>

<br />

## Tips

- [x] 生成时间较长，每处理 10 帧反馈一次进度

## 目前的局限性

- 无法调整生成脚本帧率
- 目前无法保证视频一定居中
- 全程 DeepSeek 完成，人工调试修改

