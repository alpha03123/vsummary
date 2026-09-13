# 浏览器插件安装与使用教程

VSummary 的 Chrome 插件可以把视频工作区放到 Bilibili 播放页旁边。播放视频时，你可以在侧边栏中查看 AI 概况、章节、思维导图、知识卡片和笔记，也可以直接围绕当前视频提问。

## 使用前准备

- Chrome 116 或更高版本。
- 已下载或安装 VSummary。
- 使用插件期间，需要保持 VSummary 正常运行。

插件文件夹的位置：

- Windows 整合包：`<VSummary 解压目录>\extensions\bilibili-sidepanel`
- 源码版：`<项目目录>\extensions\bilibili-sidepanel`


## 第一步：启动 VSummary

Windows 整合包用户双击根目录中的 `start.bat`。源码版用户按照项目的[安装文档](installation.md)启动服务。

等待浏览器自动打开 VSummary，或者手动访问：

```text
http://127.0.0.1:4173
```

确认这个页面能够正常打开后，再安装或使用插件。关闭启动窗口或停止 VSummary 后，侧边栏将无法连接。

## 第二步：安装插件

1. 在 Chrome 地址栏输入 `chrome://extensions` 并回车。
2. 打开页面右上角的“开发者模式”。
3. 点击页面左上角的“加载已解压的扩展程序”。
4. 选择 `extensions\bilibili-sidepanel` 文件夹。
5. 确认扩展列表中出现“VSummary B站总结”。

为了方便使用，可以点击 Chrome 工具栏中的扩展程序按钮，再把“VSummary B站总结”固定到工具栏。

如果安装插件时已经打开了 Bilibili 视频页，请刷新一次视频页面，让插件完成加载。

## 第三步：在 Bilibili 视频页使用

1. 保持 VSummary 在后台运行。
2. 打开一个地址中包含 `/video/BV` 的 Bilibili 视频播放页。
3. 点击浏览器工具栏中的“VSummary B站总结”图标。
4. 浏览器侧边栏会自动打开，并显示当前视频的工作区。

首次打开的视频会自动加入 VSummary 的“B站导入”系列。进入 AI 概况等功能时，按照页面提示开始处理视频；处理完成后即可查看转写、总结和其他知识内容。

插件会跟随当前窗口中的活动标签页：

- 切换到另一个 Bilibili 视频时，侧边栏会切换到新视频。
- 切换多 P 视频的分 P 时，侧边栏会切换到对应分 P。
- 离开 Bilibili 视频页时，侧边栏会显示未检测到视频的提示。
- 点击章节、转写片段或引用的时间位置时，Bilibili 播放器会跳到对应进度。

## 更新插件

VSummary 更新后，如果 `extensions\bilibili-sidepanel` 中的插件文件发生了变化：

1. 打开 `chrome://extensions`。
2. 找到“VSummary B站总结”。
3. 点击卡片中的“重新加载”按钮。
4. 刷新已经打开的 Bilibili 视频页面。

通常不需要先删除再重新安装插件。

## 常见问题

### 侧边栏提示“未检测到 B站视频”

确认当前活动标签页是普通的 Bilibili 视频播放页，并且地址中包含 `/video/BV`。番剧播放页、首页和搜索页暂不支持。安装或更新插件后，还需要刷新已经打开的视频页面。

### 侧边栏打不开或一直显示连接失败

先访问 `http://127.0.0.1:4173`，确认 VSummary 正在运行。如果页面打不开，请重新启动 VSummary，等待主页面能够访问后再打开侧边栏。

### 点击时间位置后，播放器没有跳转

等待 Bilibili 播放器加载完成后重试。如果问题仍然存在，请刷新视频页面；安装或重新加载插件前已经打开的页面尤其需要刷新。

### Chrome 提示插件损坏或无法加载

确认选择的是 `bilibili-sidepanel` 文件夹本身，并且其中存在 `manifest.json`。不要移动、删除或单独复制这个文件夹中的某几个文件。

### 如何卸载插件

打开 `chrome://extensions`，找到“VSummary B站总结”，点击“移除”即可。卸载插件不会删除 VSummary 中已经导入或处理的视频。
