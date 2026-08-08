# 模型下载链路规格

## 目标

修复本地模型（ASR 与 RAG）下载"经常失败、失败即清零"的问题，把下载能力统一收敛到 `huggingface_hub` 已有的续传、退避重试与镜像机制上，不再自行实现 HTTP 传输层。

本规格以当前 `src` 为实现基线。所有关于 `huggingface_hub` 与 `fastembed` 内部行为的判断均已在本机实测确认，版本见"依赖基线"，行号引自本机 site-packages 源码。

## 当前链路与问题

项目存在两条互不相关的下载链路。

| | ASR（faster-whisper / whisper.cpp） | RAG（fastembed embedding / reranker） |
| --- | --- | --- |
| 实现位置 | `asr/huggingface_model_downloader.py` | `rag/rag_models.py` |
| 下载方式 | 自研：`HfApi.model_info` 列文件 + `requests` 逐个流式写盘 | 构造 `TextEmbedding` / `TextCrossEncoder`，下载是构造函数副作用 |
| 续传 | 无 | 有（fastembed 内部走 `snapshot_download`） |
| 退避重试 | 无 | 有（同上） |
| 字节级进度 | 有 | 无，只有 `5.0` 与 `95.0` 两个点 |
| 取消 | 有，10MB 粒度 | 无，端到端缺失 |
| 落盘布局 | `data/models/{faster-whisper,whisper-cpp}/<model_id>/` 扁平 | `data/models/fastembed/`，布局由 fastembed 决定 |

### ASR 侧缺陷

- **失败即清零。** `download()` 的 `except Exception: _remove_path(temp_dir); raise` 会删掉整个临时目录。1.6G 的 `model.bin` 下到后段断一次，全部作废，重试从 0 开始。这是"总是下载不成功"的主要来源。
- **无续传。** 每个文件 `open("wb")` 从 0 写起，不发 `Range`。
- **无重试。** 单发 `session.get`，`hf_raise_for_status` 一抛即冒到顶层触发上述清理。镜像站 502/超时是常态。
- **读超时 10 秒。** `timeout=constants.HF_HUB_DOWNLOAD_TIMEOUT` 默认 10s，对 `stream=True` 是两个 chunk 之间的间隔上限，慢镜像上必然触发。
- **`max_workers` 是死字段。** dataclass 声明了，`_snapshot_download` 是串行 `for` 循环，全仓库无读取点。
- **不复用 HF 缓存。** 与 `HF_HOME` 互不相通。

### RAG 侧缺陷

- **镜像实际未生效。** fastembed 的源顺序是 `local_files_only=True` 本地探测 → HF `snapshot_download` → GCS tarball → `sleep 3.0` 重试。GCS 分支是硬编码的 `storage.googleapis.com`，与 `HF_ENDPOINT` 无关。本机磁盘上是 `fast-bge-small-zh-v1.5/`（`fast-` 前缀是 `retrieve_model_gcs` 在 `deprecated_tar_struct=True` 时的命名），证明 HF 分支失败后静默降级到了 GCS。
- **reranker 无兜底。** `BAAI/bge-reranker-base` 的 `sources.url` 为 `None`，HF 分支一失败即彻底无路。
- **取消端到端缺失。** `settings.py` 只有 `list_rag_models` / `download_rag_model` / `stream_rag_model_download_progress`，无 cancel 路由；`_download_from_huggingface` 从不调用 `reporter.is_cancel_requested()`；`Thread(daemon=True)` 在进程退出时被硬杀，留下半成品。
- **反猜目录命名。** `_candidate_model_dirs()` 需同时兼容 `models--owner--name/` 与 `fast-xxx/`，并读取 `sources._deprecated_tar_struct` 这类内部字段。
- **锁清理是补丁。** `_remove_model_lock_entries()` 专门删 `.locks` 残留，其存在本身说明曾被中断下载的死锁影响。

### 配置缺陷（独立于代码）

本机 `.env` 第 5 行为 `HF_ENDPOINT=`（空），而 `.env.example` 的默认值是 `https://hf-mirror.com`。

`apply_runtime_env_overrides()`（`config/settings.py:944`）对空值执行 `os.environ.pop(key, None)`，随后 `_refresh_loaded_huggingface_hub_endpoint()` 把 `constants.ENDPOINT` 重置为 `https://huggingface.co`。即项目在主动删除镜像配置、强制直连。这是 RAG 降级到 GCS 的直接原因，也会放大 ASR 的失败率。

## 依赖基线

| 依赖 | requirements 约束 | 本机实测版本 |
| --- | --- | --- |
| `huggingface-hub` | `>=0.24,<1` | 0.36.2 |
| `fastembed` / `fastembed-gpu` | `>=0.7,<1` | 见 requirements.cpu/gpu |
| `faster-whisper` | `>=1.1,<2` | — |

## 已确认的上游行为

以下均为实测结论，是本规格设计的前提。

**续传与重试是内置的。** `file_download.py:1713` 用 `incomplete_path.open("ab")` 追加写入，`:410` 用 `_adjust_range_header()` 按已有字节设置 `Range`。初始请求走 `utils/_http.py:213` 的 `http_backoff`，默认 `max_retries=5`、退避 1s→8s，覆盖 `Timeout` / `ConnectionError` / `ChunkedEncodingError` 与 500/502/503/504。

**`local_dir` 路径同样走续传。** `file_download.py:1222` 取 `get_local_download_paths()` 后，仍把 `paths.incomplete_path(etag)` 交给 `_download_to_tmp_and_move()`。因此不需要共享 HF 缓存根即可获得续传。

**`local_dir` 落盘布局（实测）。** 目标文件平铺在 `local_dir/`，续传元数据在 `local_dir/.cache/huggingface/download/<filename>.metadata`，并带一个 `.cache/huggingface/.gitignore`。二次调用返回同一路径，不重复下载。

**`snapshot_download` 的 `tqdm_class` 不能用于字节级进度。** `_snapshot_download.py:116` 原文注释：`Note that the tqdm_class is not passed to each individual download.`；`:332` 只把它交给 `thread_map`，即仅驱动"已完成 N/M 个文件"的外层条。

**`hf_hub_download` 没有 `tqdm_class` 参数**（实测签名为 `False`）。字节级进度只经由 `utils/tqdm.py:291` 的 `_tqdm_bar`，而该参数属于 `http_get` / `xet_get`，`hf_hub_download` 不透传。

**`http_get` 可提供全部三项能力。** 实测签名含 `resume_size`、`_nb_retries=5`、`_tqdm_bar`。传入 `_tqdm_bar` 时 `_get_progress_bar_context` 走 `nullcontext(_tqdm_bar)`，直接复用外部对象。

**进度对象仅需 `.update()`。** `file_download.py:482 / 490 / 502 / 631` 是唯一调用点，无 `.close()` / `.refresh()` / `.set_description()`。

**取消粒度为 10MB。** `constants.DOWNLOAD_CHUNK_SIZE = 10485760`。`progress.update(len(chunk))` 在 `temp_file.write(chunk)` 之前（`:502`），因此在 `update()` 内抛异常时该 chunk 不落盘。与现有自研代码粒度一致，无退化。

**`hf_transfer` 与续传互斥。** `:1701` 在启用 `hf_transfer` 时删除 `.incomplete` 重下，`:396` 有明确 warning 说明它忽略自定义 `Range`。本项目场景（弱网大文件）不启用。

**fastembed 的 `cache_dir` 就是标准 HF 缓存根。** `common/model_management.py:214` 按 `Path(cache_dir) / f"models--{repo.replace('/','--')}"` 计算快照目录，并把 `cache_dir` 原样传给 `snapshot_download`。

**fastembed 的本地校验不会硬失败。** `model_management.py:217-234` 中 `_verify_files_from_metadata` 失败仅 `logger.warning`，源码注释：`do not raise, still make an attempt to load the model`；`METADATA_FILE` 不存在时直接跳过校验。因此外部预先填充的缓存可被接受。

**两个 RAG 模型的源与产物不同。**

| 模型 | `sources.hf` | `sources.url` | `model_file` |
| --- | --- | --- | --- |
| `BAAI/bge-small-zh-v1.5` | `Qdrant/bge-small-zh-v1.5` | GCS tarball，`_deprecated_tar_struct=True` | `model_optimized.onnx` |
| `BAAI/bge-reranker-base` | `BAAI/bge-reranker-base` | `None` | `onnx/model.onnx` |

`model_optimized.onnx` 是 tarball 优化产物，HF 仓库中不存在该文件，故 GCS 分支的产物无法用 `hf_hub_download` 复现。

## 范围

| 优先级 | 工作包 | 用户价值 |
| --- | --- | --- |
| P0 | ASR 下载器改为 `http_get`，失败保留续传状态 | 大模型下载不再"失败清零"，弱网可完成 |
| P1 | `.env` 镜像默认值与空值语义修正 | 镜像真正生效，不再静默直连 |
| P2 | RAG 改为我方预热 HF 缓存，fastembed 只负责加载 | 镜像对 RAG 生效，reranker 有可靠路径，获得进度与取消 |

不在本期范围：替换 fastembed 本身；统一 ASR 与 RAG 到同一缓存根；启用 `hf_transfer`；下载并发化（见"审查决策"第 3 条）。

## P0: ASR 下载器改造

### 保留的现有骨架

`download()` 的四段结构不变：临时目录 → 下载 → 校验 → `Path.replace` 原子替换。`HuggingFaceDownloadSpec` 的对外字段除 `max_workers` 外不变。`resolve_model_dir` / `resolve_model_source` / `resolve_model_path` 全部不动，磁盘布局保持 `data/models/faster-whisper/<model_id>/` 扁平结构。

因此**本机现有 2.0G 模型（`large-v3-turbo` 1.6G、`small` 464M）不需要重新下载，也不需要迁移**。

### 替换的部分

`_snapshot_download()` 内的手写 HTTP 传输改为逐文件调用 `huggingface_hub.file_download.http_get`：

- URL 由 `hf_hub_url(repo_id, filename, endpoint=...)` 生成，headers 由 `build_hf_headers()` 生成。
- 每个文件在临时目录内维护自己的 `.incomplete` 文件；调用前读取其现有大小作为 `resume_size`，以 `open("ab")` 追加。
- 传入自定义进度对象作为 `_tqdm_bar`：其 `update(n)` 先累加全局已下载字节并上报 `reporter`，再检查取消标志，命中则抛 `HuggingFaceDownloadCancelled`。
- 单文件完成后校验大小（`model_info(files_metadata=True)` 提供 `expected_size`），通过后移动到临时目录内的正式相对路径。
- `expected_size` 为 `None` 时跳过大小校验，进度总量按未知处理（`_calculate_download_progress` 已支持 `total_bytes is None`）。

`http_get` 属于 `huggingface_hub.file_download` 的模块级函数，但 `_tqdm_bar` / `_nb_retries` 是下划线前缀参数。实现须用 `inspect.signature` 做能力探测：缺少 `_tqdm_bar` 时降级为 `hf_hub_download(local_dir=...)`（仍有续传与重试，仅失去字节级进度与 10MB 粒度取消），并记录一条告警。降级路径必须在原子替换前清理 `local_dir/.cache/huggingface/` sidecar，避免其进入正式目录。

### 失败与取消语义变更

**这是本期最重要的行为变更。**

| 场景 | 现在 | 改后 |
| --- | --- | --- |
| 下载中途失败 | 删除临时目录，下次从 0 | 保留临时目录与 `.incomplete`，下次续传 |
| 用户取消 | 删除临时目录，下次从 0 | 同上，保留 |
| 校验缺文件 | 删除临时目录 | 保留（下次重新列表并续传） |
| 校验通过 | 原子替换 | 先剪除本次计划外的残留文件，再删 sidecar，再原子替换 |

临时目录按模型隔离（`.{model_id}.download`），`is_downloaded()` 只看正式目录，因此保留临时目录不影响状态判断。需要提供一个显式的"清理下载缓存"入口，让用户可主动丢弃残留（见"审查决策"第 1 条）。

"剪除计划外残留"是必要的：若 `allow_patterns` 或上游仓库文件清单发生变化，上次遗留的文件不能被 `Path.replace` 带进正式目录。

### 移除的代码

- `HuggingFaceDownloadSpec.max_workers` 字段及其文档（死字段，无读取点）。
- 自研的大小校验与 `iter_content` 循环。

## P1: 镜像配置修正

- `.env.example` 保持 `HF_ENDPOINT=https://hf-mirror.com`。
- 修正空值语义：`apply_runtime_env_overrides()` 当前对空值执行 `pop`，等于主动删除进程环境中已有的镜像配置。改为"`.env` 中显式写空 → 视为未配置，不再 `pop` 掉进程环境中的既有值"，避免项目覆盖用户在 shell 或系统层面设置的镜像。
- 设置页若允许清空该字段，须明确区分"清空（回退默认）"与"显式直连"两种意图；不允许静默写入空值后又反过来删除环境变量。
- 保留 `_refresh_loaded_huggingface_hub_endpoint()`：ASR 侧改造后不再依赖它（`http_get` 的 URL 由 `hf_hub_url(endpoint=...)` 显式生成），但 fastembed 内部按 `constants.ENDPOINT` 取值，P2 完成前仍需它。
- 不启用 `HF_HUB_ENABLE_HF_TRANSFER`：与续传互斥，且本项目瓶颈是稳定性而非峰值速度。

## P2: RAG 缓存预热

### 原理

利用 fastembed 源顺序的第一步（`local_files_only=True` 本地探测）：由我方先用 `hf_hub_download(cache_dir=data/models/fastembed)` 把文件下成标准 HF 缓存布局，之后构造 `TextEmbedding` / `TextCrossEncoder` 时该探测直接命中，fastembed 不发网络请求，**永不降级到 GCS**。

要下载的文件清单从 `list_supported_models()` 的 `model_file` 与 `additional_files` 推导，与 fastembed 自身计算的 `extra_patterns` 保持一致。

### 收益

- 镜像对 RAG 真正生效（当前实测为失效）。
- `bge-reranker-base` 不再依赖无兜底的 HF 直连。
- 获得与 ASR 一致的续传与退避重试，以及进度上报与取消能力。
- ~~`_candidate_model_dirs()` 可退化为只认 `models--owner--name/` 一种布局~~ →
  **实施时否决**：退化会让现有 `fast-bge-small-zh-v1.5/`（91M）不再被识别为已下载，
  凭空触发一次重下。保留双布局兼容的成本只是一个 `sources.url` 分支，收益是零迁移。
- ~~`_remove_model_lock_entries()` 与 `.locks` 清理补丁可移除~~ →
  **实施时否决**：`.locks` 残留仍会挡住下一次下载，与布局无关，清理逻辑保留。

### 代价与约束

- ~~现有 `fast-bge-small-zh-v1.5/`（91M）无法复用，需重下一次~~ →
  **已避免**：保留 tarball 布局兼容后该目录仍被判定为已下载，无需重下。
  新下载走 HF 布局，两种布局共存。
- **进度与取消的粒度低于 ASR 侧**：`warm_cache()` 按“文件之间”上报与响应取消，
  不做字节级。预热的是几十到几百 MB 的中小文件，文件粒度够用；换字节级要把
  `_CancellableProgress` 接进 `hf_hub_download`，而后者不暴露 `_tqdm_bar` 钩子
  （已验证：只有 `snapshot_download` 有 `tqdm_class`，且不透传给单文件下载）。
- **ASR 与 RAG 的落盘方式必须不同**，不强行统一：ASR 用 `local_dir` 以保持现有扁平布局并避免迁移；RAG 必须用 `cache_dir` 以迁就 fastembed 的探测规则。共享的是下载器与镜像配置，不是目录根。
- **失败/取消时 HF 缓存目录必须保留**：`_cleanup_incomplete_model_cache()` 原先会删掉
  半成品目录，而 HF 布局下这等于删掉 `blobs/*.incomplete`，与 ASR 侧“末段断线丢掉整个
  进度”是同一个缺陷。现按布局区分：HF 布局跳过（由 HF 的 blob 机制保证未写完的 blob
  不会被提交进 `snapshots/`，因此保留不会让 `is_downloaded()` 误判），tarball 布局仍删除。
- `agent_runtime_provider.py:201` 传给 `BGEReranker` 的是 `local_model_dir("reranker").parent`。改为 HF 缓存布局后该 `.parent` 仍应解析到 fastembed 缓存根，须一并核对。
- `fastembed_adapter.py` 的 `_resolve_specific_model_path()` 按 `fast-<basename>` / `<basename>` 查找完整目录，命中时传 `specific_model_path` 绕过 fastembed 的正常解析。HF 缓存布局下它将返回 `None`，从而回落到 fastembed 自身解析并命中预热缓存——这是期望行为，但须显式覆盖测试。
- 需要新增 RAG 下载取消路由；`_run_download` 的 `except Exception` 须区分取消与失败，取消不应上报为 `failed`。
- `Thread(daemon=True)` 在进程退出时仍会被硬杀，但改造后残留的是可续传的 `.incomplete`，不再是不可用的半成品。

## 验收标准

### P0

- 3G 级模型下载在中途断网后重试，从断点继续，不从 0 重新开始。
- 镜像返回 502/503 时自动退避重试，不再单次失败即整体清零。
- 失败或取消后临时目录与 `.incomplete` 仍存在；下次下载复用。
- 校验通过后正式目录不含 `.cache/huggingface/` 等 sidecar，也不含本次文件清单以外的残留文件。
- 本机现有 `large-v3-turbo` 与 `small` 在改造后仍被 `is_downloaded()` 判定为已下载，不触发任何下载。
- 取消请求在 10MB 内生效；被取消时该 chunk 不落盘。
- `max_workers` 从 `HuggingFaceDownloadSpec` 移除后全仓库无引用残留。
- 在 `_tqdm_bar` 不可用的模拟环境下自动降级到 `hf_hub_download`，仍能完成下载与原子替换。

### P1

- `.env` 中 `HF_ENDPOINT` 为空时，进程环境里已有的 `HF_ENDPOINT` 不被删除。
- 配置镜像后，ASR 与 RAG 的实际请求 host 均为镜像域名。

### P2

- 预热完成后构造 `TextEmbedding` / `TextCrossEncoder` 不产生任何网络请求（可用 `HF_HUB_OFFLINE=1` 断言）。
- `bge-reranker-base` 在仅有镜像可达、`huggingface.co` 不可达的环境下可完成下载。
- `is_downloaded()` / `local_model_dir()` 在 HF 缓存布局与既有 tarball 布局下均正确判定
  （不再要求“不依赖 `_deprecated_tar_struct`”——见上文否决理由）。
- 预热用的仓库 ID 必须取自 `sources.hf`，不得用 `RagModelSpec.model_name`：
  `BAAI/bge-small-zh-v1.5` 的 ONNX 权重实际托管在 `Qdrant/bge-small-zh-v1.5`，
  用 `model_name` 会预热到错误仓库或 404。已有回归用例覆盖。
- 预热的 `allow_patterns` 必须逐字对齐 fastembed 的清单（5 个固定 JSON + `model_file`
  + `additional_files`）：多了浪费带宽，少了会让离线加载失败并回退 GCS，等于白预热。
- 失败/取消后 HF 缓存目录及其 `blobs/*.incomplete` 仍存在，且 `.locks` 已清理。
- RAG 下载可取消，取消后状态为 `cancelled` 而非 `failed`。（**未实施**，见下文遗留项）
- `_resolve_specific_model_path()` 返回 `None` 时，embedding 仍能从预热缓存加载成功。

## 测试计划

现有 `tests/backend/unit/asr/test_huggingface_model_downloader.py` 只有一个用例 `test_chunk_download_cancel_cleans_temp_dir`，其 mock 打在 `session.get` 层，且断言"取消后临时目录被删除"。该断言与本期语义变更直接冲突，**必须重写为断言临时目录被保留**。

需要补充的用例：

- 续传：预置部分 `.incomplete`，断言仅请求剩余字节且最终文件完整。
- 失败保留：模拟传输异常，断言临时目录与 `.incomplete` 存在。
- 残留剪除：预置计划外文件，断言原子替换后正式目录不含它。
- sidecar 清理：降级路径下断言正式目录无 `.cache/huggingface/`。
- 能力探测降级：模拟 `http_get` 缺少 `_tqdm_bar`，断言走 `hf_hub_download` 分支。
- 进度单调性：多文件场景下断言上报进度不回退、落在 5–95 区间。
- RAG 预热命中：预热后在 `HF_HUB_OFFLINE=1` 下断言模型可加载。

均为离线单元测试，不得依赖真实网络。

## 实施顺序

1. P1 配置修正（改动最小，且能独立降低失败率，便于先验证镜像是否为主因）。
2. P0 ASR 下载器改造与测试重写。
3. P2 RAG 预热、目录探测简化、取消路由与相关调用点核对。

每步完成后运行对应后端单元测试；P0 与 P2 额外做一次真实弱网下载与中途中断验证。

## 审查决策

实施前需要确认：

1. **残留临时目录的清理入口。** 保留 `.incomplete` 是本期核心收益，但会长期占盘（单个模型可达 GB 级）。建议在设置页模型列表提供显式"清理下载缓存"，不做自动过期删除，以免又回到"失败清零"。
2. **P1 空值语义的兼容影响。** 改为"空值不再 `pop`"后，此前依赖该行为强制直连的用户会变成沿用系统环境变量。需确认无人依赖旧行为。
3. **是否引入下载并发。** `max_workers` 目前是死字段。faster-whisper 与 reranker 均为单个大文件主导（`model.bin` 占比 99%），并发对总耗时几乎无改善，却会显著复杂化进度合并与取消。建议本期保持串行并直接删除该字段，不做"激活"。
4. **P2 是否保留 GCS 兜底。** 预热命中后 fastembed 不会走 GCS。若预热本身失败，是否允许回落到 fastembed 原有链路（含 GCS）作为最后手段，还是直接报错要求用户检查镜像。建议允许回落但在 UI 明确提示"已绕过镜像"。

## 实施状态（2026-08-08）

已完成 P0 / P1 / P2 的代码与测试。以下记录**实施过程中被证伪或修正的规格内容**，以本节为准。

### 与原规格的偏差

| 原规格 | 实际实施 | 原因 |
| --- | --- | --- |
| P2 收益：`_candidate_model_dirs()` 退化为只认 HF 布局 | **保留双布局兼容**，仍读 `_deprecated_tar_struct` | 简化会让现有 `fast-bge-small-zh-v1.5/`（91M）失效并强制重下。保留兼容后它继续可用，不需重下 |
| P2 收益：`_remove_model_lock_entries()` 可移除 | **保留** | 锁目录残留会挡住下一次下载，与布局无关 |
| P2 收益：RAG 获得"字节级进度、10MB 粒度取消" | **文件粒度** | `warm_cache()` 直接用 `hf_hub_download`，不注入 `_tqdm_bar`。预热文件为几十到几百 MB，文件粒度够用；换取实现简单与 blob 续传由 HF 自管 |
| 代价：现有 91M tarball 目录需重下 | **不需要** | 同上，双布局兼容 |
| 实施顺序 P1→P0→P2 | **P1 先做且优先级提到 0** | 实测确认空 `HF_ENDPOINT` 是失败主因，代码缺陷只是放大器 |

### 实测根因（TUN 关闭）

| 目标 | 可达性 | 下载 3.5MB |
| --- | --- | --- |
| `huggingface.co` | 超时 8.15s | 失败 `WinError 10060` |
| `hf-mirror.com` | 200 / 0.77s | 成功 7.76s（0.44 MB/s） |

失败链条：`.env` 第 5 行 `HF_ENDPOINT=` 为空 → `os.environ.pop("HF_ENDPOINT")` → `constants.ENDPOINT` 复位为 `https://huggingface.co` → TCP 超时 → 旧代码 `except: _remove_path(temp_dir)` 丢弃全部进度。

附带发现的第二个真实缺陷：`start.bat.tpl:8-9` 与 `build_release.ps1:508-509` 会设 `HF_HOME` / `HUGGINGFACE_HUB_CACHE` 到项目内目录，而 `.env` 里这两行留空会把它们 `pop` 掉，缓存回落到用户主目录。

### 关键实现约束（易回归点）

- **预热的 `repo_id` 必须取 `sources.hf`，不能用 `RagModelSpec.model_name`。** `BAAI/bge-small-zh-v1.5` 的 ONNX 权重实际托管在 `Qdrant/bge-small-zh-v1.5`，用 `model_name` 会 404。已由 `test_prewarm_uses_sources_hf_repo_id_not_model_name` 覆盖。
- **`allow_patterns` 必须与 fastembed 逐字一致**（5 个固定 JSON + `model_file` + `additional_files`）。多了浪费带宽，少了会让离线加载失败并回落 GCS，等于白预热。已由 `test_prewarm_allow_patterns_match_fastembed_base_list` 覆盖。
- **失败时不得删除 `models--*/` 目录**：`blobs/*.incomplete` 是续传锚点。tarball 布局（`fast-*/`）无此机制，仍需删除。两者已分别覆盖。
- `vocab.txt` / `ort_config.json` 存在于仓库但不在 fastembed 清单内，预热目录文件数少于 tarball 目录属**正确**行为。

### 已由实施结论解决的审查决策

- **第 3 条（下载并发）**：按建议保持串行，`max_workers` 已删除，全仓库无残留引用。
- **第 4 条（GCS 兜底）**：保留回落，但收窄为"仅当 fastembed 元数据无 `sources.hf` 时"走 `_download_via_fastembed()`。当前两个模型均有 `sources.hf`，因此实际不会触发。

仍待确认：第 1 条（清理缓存入口）与第 2 条（空值语义兼容影响）。

### 尚未实施

- **RAG 对外的取消 API**。取消的两层已就位：`warm_cache()` 在文件边界检查取消标志并抛 `HuggingFaceDownloadCancelled`，`_run_download()` 已把它与失败分开上报为 `cancelled`（且取消路径不做清理，保留续传现场）。缺的只是一个像 ASR 那样的 HTTP 路由去把取消标志置上——目前没有入口能触发它。
- `agent_runtime_provider.py:201` 的 `.parent` 与 `fastembed_adapter.py` 的 `_resolve_specific_model_path()` 在 HF 布局下的显式覆盖测试。
- 真实弱网验证：需下载 `large-v3` 并中途断网，确认从断点续传而非重新开始。此项无法在开发环境复现，须由使用者验证。

### 测试与检查结果

- `tests/backend/unit/asr/test_huggingface_model_downloader.py`：9 passed（0.44s，全离线）。
- `tests/backend/unit/models/test_rag_model_manager.py`：15 passed（7.64s；改造前 10 tests / 35.30s，耗时下降源于预热路径可注入，不再经 fastembed 构造函数触网）。
- `tests/backend/unit/settings/test_workspace_settings_service.py`：19 passed（0.90s）。
- 后端全量：19 failed / 423 passed。这 19 项在干净树上同样失败（`CancelledGenerator.run()` 缺 `manual_transcript` 参数等测试替身签名漂移），与本期无关；已用 `git stash` 在干净树上复核确认。
- `import-linter`：10 contracts kept, 0 broken（需 `PYTHONPATH=src`）。
