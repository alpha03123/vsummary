# B 站链接导入链路 WAF 失败

- **状态**：✅ 已修复（2026-06-13）
- **影响**：`POST /api/linked/bilibili/resolve/series`、`POST /api/videos/{sid}/{vid}/download` 在 B 站外部视频导入时失败
- **类别**：第三方平台集成 / 反爬

---

## 现象（按出现顺序）

1. `POST /api/linked/bilibili/resolve/series` 返回 500，`SSL: UNEXPECTED_EOF_WHILE_READING` 或 `HTTP Error 412`
2. 加 `User-Agent` / `Referer` 后，412 转移到 playinfo 端点（`api.bilibili.com/x/player/playurl`）
3. 加 `SESSDATA` 单 cookie 后，wbi 签名（`/x/web-interface/nav`）通过但 playinfo 仍 412
4. 通过微信 / QQ 转发的 B 站链接被 IDN 编码成 `xn--...` 形式，urllib3 解析失败
5. resolve 拿到视频信息后，真正下载时 yt-dlp 子进程对 playinfo 同样 412
6. 直连 view API 时出现 `SSL: UNEXPECTED_EOF_WHILE_READING`（系统代理干扰）

---

## 根因（按层）

| # | 层 | 根因 |
|---|---|---|
| 1 | B 站网页 WAF | yt-dlp 裸调用，缺 `User-Agent` / `Referer` |
| 2 | B 站 playinfo WAF | `SESSDATA` 单 cookie 不够；playinfo 端点要求完整联防（`buvid3/4/fp`、`b_nut`、`bili_jct`、`_uuid`、`DedeUserID`、`bili_ticket` 等） |
| 3 | IDN mangled URL | 微信 / QQ / 输入法转发时把全角或不可见字符塞进 URL；下游某层把整个 `https://host` 当 IDN 域名编码成 punycode |
| 4 | 系统代理 | Windows 上 `HTTPS_PROXY` 对境内站点也生效，代理 ↔ B 站之间 TLS 握手失败 |
| 5 | yt-dlp 子进程继承 | `Popen` 继承父进程的代理环境变量 |
| 6 | yt-dlp cookiejar 覆盖 | `--add-header "Cookie:..."` 注入的 header 在 playinfo 端点被 yt-dlp 的 cookiejar 路径覆盖，必须走 `--cookies <file>` |

---

## 改动的文件

### 1. `src/backend/bilibili/ytdlp_bilibili.py`（主要修改）

| 行号区域 | 变更 |
|---|---|
| 第 1-12 行 | imports：加 `os`、`tempfile` |
| 模块级常量（第 280-290 行） | 新增 `_BILIBILI_USER_AGENT`、`_BILIBILI_REFERER`、`_BILIBILI_COOKIE_ENV`、`_BILIBILI_SESSDATA_ENV` |
| `_load_bilibili_headers()`（第 293-322 行） | 优先读 `BILIBILI_COOKIE`（完整 Cookie 字符串），回退到 `BILIBILI_SESSDATA`（单 cookie）；原版作为注释保留 |
| `_build_yt_dlp_add_header_flags()`（第 325-331 行） | 新增 helper：dict → `--add-header Key:Value` 列表 |
| `_write_bilibili_cookies_file()`（第 334-369 行） | 新增 helper：把 Cookie 字符串写成 Netscape 格式临时文件，返回路径 |
| `BilibiliDownloader.download` cmd 块（第 99-147 行） | 多次迭代 v1（无 header）→ v2（+ UA/Referer）→ v3（+ `--proxy ""`）→ v4（+ `--cookies` 文件），每次旧版作为注释保留 |
| `BilibiliDownloader.download` Popen 块（第 169-219 行） | 加 `env=proc_env`（清掉 `HTTP_PROXY` / `HTTPS_PROXY` / `ALL_PROXY`）；加 `finally` 清理临时 cookies 文件 |
| `BilibiliDownloader.download` 错误块（第 199-207 行） | 把 yt-dlp 最后 50 行 stdout / stderr 拼进 `RuntimeError`，便于排错 |
| `_extract_info()`（第 276-303 行） | 加 `http_headers` 选项传完整 header |
| `_extract_view_info()`（第 306-330 行） | 加 `proxy=None` 显式不走代理；原始调用整段注释保留 |

### 2. `src/backend/video_summary/library/parsers.py`

| 行号 | 变更 |
|---|---|
| 第 4 行 | 加 `from urllib.parse import urlparse` |
| `DefaultBilibiliUrlParser.parse`（第 11-36 行） | 原 5 行逻辑整段注释保留；新增 IDN mangled URL 检测 + 还原：检测 `parsed_url.path.startswith("//")`，从 path 里把原始 `https://host/...` 抠出来 |

### 3. `.env`（本机，已 gitignore）

- 第 14-18 行：新增 `BILIBILI_COOKIE=...`，包含 12 个核心 B 站 cookies（SESSDATA、buvid3/4/fp、b_nut、bili_jct、_uuid、DedeUserID、bili_ticket 等）
- 第 20-21 行：保留 `BILIBILI_SESSDATA` 作为兼容兜底

### 4. `.env.example`（仓库内模板）

- 第 14-21 行：文档化 `BILIBILI_COOKIE`（优先级最高）和 `BILIBILI_SESSDATA`（兼容入口）两个变量及取法

### 5. 运行时包升级（非源码改动）

```bash
runtime/python.exe -m pip install -U yt-dlp
# 2026.3.17 → 2026.6.9
```

新版 yt-dlp 修了一些 B 站 wbi 签名的边角问题。

---

## 验证步骤

```bash
# 1. 重启后端
# 关闭 start.bat 当前窗口，重新双击 start.bat

# 2. 触发下载
POST /api/linked/bilibili/resolve/series
  body: {"url": "https://www.bilibili.com/video/BV1G29JYQE8b?p=6"}
POST /api/videos/bilibili-BV1G29JYQE8b/BV1G29JYQE8b_p6/download

# 3. 预期
# - 200 OK
# - SSE 进度流最终 status="completed"
# - 文件落到 videos/bilibili-BV1G29JYQE8b/BV1G29JYQE8b_p6.{mp4/m4s/...}
```

---

## 复现 / 回归测试建议

`tests/backend/integration/bilibili/` 下应补 2-3 个 case：

- 正常 BV URL 解析（`https://www.bilibili.com/video/BV1xx411c7mD`）
- IDN mangled URL 还原（用本次 `xn--...//www.bilibili.com/...` 那条）
- 单 `SESSDATA` vs 完整 Cookie 两种 headers 形态的组装差异

---

## 经验沉淀

B 站反爬是多层叠加，单一修复不够：

| 层 | 必备 |
|---|---|
| Webpage | `User-Agent` + `Referer` |
| wbi 签名 | 至少 `SESSDATA` |
| playinfo | `SESSDATA` + `buvid3/4` + `b_nut` + `bili_jct` + `_uuid` + `DedeUserID` + `bili_ticket` + `b_lsid`（来自浏览器 DevTools 完整 Cookie 字符串） |
| yt-dlp 集成 | Cookie **必须**走 `--cookies` 文件，不能走 `--add-header` |
| 系统代理 | 境内站点显式 `proxy=None` / `--proxy ""` |
| URL 来源 | 微信 / QQ 转发的 URL 不可信，需要 IDN mangled 检测 |
