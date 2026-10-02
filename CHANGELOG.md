# Changelog

## v0.5.4

### Feature

- AI 概括支持选择概括风格
- 逐字稿章节截图现在会附带可直接访问的图片地址，启用“逐字稿配图”后会在每章显示对应画面。

### Fix

- 修复 Bilibili 侧栏播放器桥接初始化与逐字稿定位同步问题。
- 修复外链视频身份恢复、字幕来源保存和可复用生成阶段缓存，避免重新处理时丢失可用素材。
- 修复章节时间范围与重叠校验，防止异常时间轴继续发布。
- 改善持久化生成任务的准备阶段、耗时与进度显示，并默认折叠对话推理内容。
- 修复缓存失效的问题
- 修复导图/卡片卡0%的问题
## v0.5.3

### Feature
- AI 整理逐字稿新增按章节生成的响应式目录
- 视频预览面板新增原始媒体导出入口。
- AI 对话的会话管理收纳到面板顶栏最右侧，可展开切换或新建对话。

### Fix

- 修复人工笔记编辑后保存失败；更新笔记时会保留原始创建时间。删除人工笔记前现在会要求确认。
- 修复播放视频时 citation 悬浮预览被重渲染打断的问题。
- 修复全局 AI 对话 citation 在系列概况中跳到同名错误章节的问题；现在会切换到引用所属视频、展开对应原文并高亮精确转写片段。
- 关闭视频预览面板时自动暂停播放。
- 修复视频与全局思维导图生成进度在准备阶段显示 `0%`、耗时或预估时间缺失的问题；准备阶段改为用户可读状态，并支持实时计时与估算。
- 将播放器入口文案由“查看当前转写”调整为“查看当前逐字稿”。

## v0.5.2.2

### Fix

- 更新器和打包脚本支持四段正式版本号，以及 `alpha`、`beta`、`rc`、`hotfix` 后缀的项目版本规则；打包时会拒绝不符合规则的版本号。

## v0.5.2.1

### Fix

- 修复 AI 概括引用了未提供的转写时间时导致整篇概括生成失败的问题；现在会将校验错误反馈给模型重试一次，仍不通过时移除无效角标并保留已生成的概括正文与可验证引用。

## v0.5.2

### Feature

- 工作台支持可拆分、嵌套的弹性面板布局。
- 浏览器 Bilibili 插件视频默认导入专用的 `B站导入` 系列；该系列从 All Shelves 移至首页 Plugin Directory

### Fix

- 修复 SQL 存储的视频预览未按 fast-start 格式准备，导致浏览器预览体验不稳定的问题。
- 修复转写片段拖拽不可靠、拖拽后滚动链路异常的问题。
- 修复空 Playground 的打开、首次外链视频导入与并发创建问题。
- 修复 macOS 从源码启动时前端构建产物未更新的问题。

## v0.5.1.1

### Fixed

- Fixed legacy knowledge-card and note imports when multiple videos reuse local IDs such as `kc-1` or `note-1`.
- Preserved knowledge-card relationships during legacy import by remapping them to the new database IDs.
- Made legacy structured-artifact imports resumable when an interruption occurs between persisting data and recording import progress.
- Allowed the managed local MySQL instance to move to a new loopback port when its previously recorded port is no longer available.
