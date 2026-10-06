# VSummary Workspace UI

Reusable product-neutral workspace components for VSummary shells.

Install the preview package from GitHub Packages:

```ini
# .npmrc
@alpha03123:registry=https://npm.pkg.github.com
```

```sh
npm install @alpha03123/vsummary-workspace-ui@next
```

The package deliberately has no Local API client or local-only route dependency.

## Host extension contract

`WorkspaceApp` accepts a host with `api`, scoped `storage`, `panels` and optional render callbacks.
`renderBrand(controller, page)` replaces the toolbar brand, including its mark and title.
`renderToolbar(controller, page)` adds toolbar controls.
`renderSidebarHeader(controller, page)` and `renderSidebarFooter(controller, page)` render outside
the sidebar's scrolling content, so they remain available across library and series views.

`createActions({state, dispatch, contentActions, coreApi, actions})` returns controller overrides.
**Host actions always take precedence over package defaults.** Unspecified actions retain their defaults.
`actions` contains the original controller actions, so overrides can delegate without calling themselves:

```jsx
createActions({actions}) {
  return {
    onSelectSeries(seriesId) {
      if (!session) return requestLogin();
      return actions.onSelectSeries(seriesId);
    },
  };
}
```

This is a UI extension contract. Authentication and workspace authorization belong to the host backend.

## Reusable surfaces

`WorkspaceDialog` preserves its accessible name and focus trap when `header` replaces the default header.
Dialogs render through a portal to `document.body`, outside clipped or transformed host containers.
Its `title` remains the accessible dialog name. `header={null}` hides the visual header.
`align="center"` centers the default header; `align="start"` is the default.
`className`, `headerClassName`, `iconClassName` and `backdropClassName` merge with the corresponding
default Tailwind classes, with caller classes taking precedence. For an unframed mark, use
`iconClassName="border-0 bg-transparent"`. For an unblurred backdrop, use
`backdropClassName="backdrop-blur-none"`.

A close button appears when `onClose` is provided. `showClose={false}` hides it and `closeLabel`
sets its accessible name. While `pending`, the close button, Escape, backdrop dismissal and submit
are blocked. `useFocusTrap(containerRef, active)` is exported for custom host dialogs; the host
handles Escape and dismissal.

`WorkspaceStateBlock` accepts `className` with the same merge semantics. For embedded loading
states, use `className="mt-0 min-h-0"` instead of inheriting the full-page spacing.

`WorkspaceUsagePage` is a presentation component shared by Local and Cloud. Without `children`,
it lazily loads the token analytics view using `usage`, `range`, `loading`, `error` and `onChangeRange`.
It fetches no data. Hosts can supply their own quota/check-in content as `children` and customize
`title`, `eyebrow`, `icon`, `className`, `bodyClassName`, `closeLabel` and `onClose`. Analytics charts
are not loaded when custom content is supplied.

`WorkspaceUsageAnalytics` is also exported with its own lazy-loading boundary. Hosts can compose
check-in controls and statistics inside the same `WorkspaceUsagePage`:

```jsx
<WorkspaceUsagePage title="额度与用量" onClose={close}>
  <CheckInControls />
  <WorkspaceUsageAnalytics usage={usage} range={range} loading={loading}
    error={error} onChangeRange={setRange} />
</WorkspaceUsagePage>
```

`createWorkspaceApi(transport).loadProviderUsage(range)` fetches the shared authenticated Core route
`GET /api/provider-settings/usage?range=7d` and returns the analytics view model. The backend chooses
the authenticated workspace and actor; the browser does not supply an actor filter.

## 0.5.0-alpha.6

Adds dialog customization and close controls, brand/sidebar header slots, state-block class merging,
documented action overrides with default delegation, shared usage presentation and the public focus hook.

## 0.5.0-alpha.7

Portals dialogs outside host containers so sidebar account dialogs remain visible and clickable.

## 0.5.0-alpha.8

Exports composable lazy usage analytics and the shared usage client, allowing check-ins and token
statistics in one host panel without copying the analytics implementation.

## 账号偏好与任务 SDK

`createWorkspaceApi()` 导出 `loadUserPreferences`、`updateUserPreferences`、`loadJobs`、`loadJobStatistics`、`loadJob` 和 `cancelChatRequest`。聊天状态接收 `queue` SSE 事件并提供 `chatQueue`，宿主可展示排队与取消入口。积分、签到和运营后台由 Cloud 定义，共享包不内置价格。

## 0.5.0-alpha.10：设置组件契约

`WorkspaceSettingRow` 接受 `layout="responsive"`（默认，小屏竖排、2xl 起横排）或
`layout="stacked"`（所有视口宽度下竖排，控件占满内容宽度并左对齐）。
`contentClassName` 继续作用于控件容器；无需宿主复制设置行或覆盖包 CSS。

`WorkspaceToggleSwitch` 的 `onChange(nextChecked)` 现在传入下一状态的布尔值，
可直接保存到表单。原先依赖点击事件的宿主必须改为接收布尔值。

```jsx
<WorkspaceSettingRow layout="stacked" title="多模态概括" description="允许模型读取视频画面。">
  <WorkspaceToggleSwitch checked={form.multimodal}
    onChange={value => setForm({...form, multimodal: value})} ariaLabel="多模态概括" />
</WorkspaceSettingRow>
```

## 0.5.0-alpha.11：宿主媒体能力与术语

宿主可设置 `features.mediaPreview=false`：隐藏视频预览工具，已保存的预览面板改为文本概况，
时间戳跳转定位文本，不创建播放器。`features.sourceRegeneration=false` 隐藏字幕模式入口，
已处理内容不再提供依赖原媒体的重新处理按钮。Local 默认保持全部媒体能力。

系列相关文案统一为“系列”，移除共享空态中的本机目录导入提示。
数据库整理的历史完成提示不再于进入或刷新工作区时显示，执行进度与失败提示保留。

## 0.5.0-alpha.12：系列空态

空系列页在“还没有系列”下说明“请点击添加系列以增添第一个系列”，直接引导用户使用下方按钮。
宿主可用 `toolbarButtons.assistant`、`toolbarButtons.usage`、`toolbarButtons.settings` 的
`{label, icon}` 修改包内工具栏按钮的悬停文案、可访问名称和图标；未指定时沿用 Local 原值。

## 0.5.0-alpha.13：聊天作用域

AI 聊天仅在已选择系列或视频时显示。回到全部系列主页时，工具栏入口和聊天抽屉都会关闭。

## 0.5.0-alpha.14：系列任务状态

系列处理仅在持久父任务与全部子任务都终态后显示完成、失败或取消。点击取消后界面保持“正在取消”，
直到后端确认最终状态。

## 0.5.0-alpha.15：系列任务一致性

系列处理中存在其他活跃视频任务时，启动请求会直接返回冲突，不会创建部分批任务。Cloud 在创建
系列父任务前一次性预留每个待处理视频的积分；余额不足时不会创建父任务或子任务。

## 0.5.0-alpha.16：遗留批任务恢复

如果早期版本把父批任务提前标为终态、但子任务仍未结束，worker 会恢复父任务为等待状态并继续
跟踪子任务。取消这类遗留批任务会进入正常的取消流程。
