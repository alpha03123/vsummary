# Changelog

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
