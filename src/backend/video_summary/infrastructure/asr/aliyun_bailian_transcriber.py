"""阿里云百炼 / DashScope Paraformer ASR 转写器。"""

from __future__ import annotations

import json
import logging
from http import HTTPStatus
from pathlib import Path
from typing import Callable

import httpx

from backend.video_summary.domain.models import Transcript, TranscriptSegment

logger = logging.getLogger(__name__)


class AliyunBailianTranscriber:
    """通过 DashScope SDK 临时上传本地音频，并调用 Paraformer 非实时转写。"""

    def __init__(
        self,
        *,
        model: str,
        base_url: str,
        api_key: str,
        language: str = "zh",
    ) -> None:
        normalized_model = model.strip()
        normalized_api_key = api_key.strip()
        if not normalized_model:
            raise RuntimeError("阿里云百炼 ASR 模型名称不能为空。")
        if not normalized_api_key:
            raise RuntimeError("请先在设置中填写阿里云百炼 ASR API Key。")

        self._model = normalized_model
        self._base_address = _normalize_dashscope_base_address(base_url)
        self._api_key = normalized_api_key
        self._language = language.strip() or "zh"
        self.cache_identity = "|".join(
            [
                type(self).__module__,
                type(self).__qualname__,
                self._model,
                self._base_address,
                self._language,
            ]
        )

    def transcribe(
        self,
        audio_path: Path,
        output_stem: Path,
        on_progress: Callable[[float], None] | None = None,
    ) -> Transcript:
        """上传本地音频到 DashScope 临时 OSS，并返回带时间戳的转写结果。"""
        if not audio_path.exists():
            raise RuntimeError(f"待转写音频不存在：{audio_path}")

        output_stem.parent.mkdir(parents=True, exist_ok=True)
        oss_url = self._upload_audio(audio_path)
        _report(on_progress, 0.08)
        task = self._submit_transcription(oss_url)
        _report(on_progress, 0.12)
        result = self._wait_transcription(task)
        _report(on_progress, 0.90)
        transcript_payload = self._load_transcription_payload(result)
        transcript = _parse_transcript_payload(transcript_payload, language=self._language)
        _report(on_progress, 1.0)
        return transcript

    def _upload_audio(self, audio_path: Path) -> str:
        try:
            from dashscope.utils.oss_utils import OssUtils
        except ImportError as error:
            raise RuntimeError("dashscope is not installed.") from error

        try:
            upload_result = OssUtils.upload(
                model=self._model,
                file_path=str(audio_path),
                api_key=self._api_key,
                base_address=self._base_address,
            )
        except Exception as error:
            raise RuntimeError(f"上传音频到 DashScope 临时存储失败：{error}") from error

        oss_url = _extract_oss_url(upload_result)
        if not isinstance(oss_url, str) or not oss_url.strip():
            raise RuntimeError("上传音频到 DashScope 临时存储失败：未返回有效文件地址。")
        return oss_url.strip()

    def _submit_transcription(self, oss_url: str):
        try:
            from dashscope.audio.asr import Transcription
        except ImportError as error:
            raise RuntimeError("dashscope is not installed.") from error

        try:
            response = Transcription.async_call(
                model=self._model,
                file_urls=[oss_url],
                api_key=self._api_key,
                base_address=self._base_address,
                headers={"X-DashScope-OssResourceResolve": "enable"},
            )
        except Exception as error:
            raise RuntimeError(f"提交阿里云百炼转写任务失败：{error}") from error
        _ensure_success_response(response, "提交阿里云百炼转写任务失败")
        return response

    def _wait_transcription(self, task):
        from dashscope.audio.asr import Transcription

        try:
            response = Transcription.wait(
                task,
                api_key=self._api_key,
                base_address=self._base_address,
            )
        except Exception as error:
            raise RuntimeError(f"等待阿里云百炼转写任务失败：{error}") from error
        _ensure_success_response(response, "阿里云百炼转写任务失败")

        output = _response_output(response)
        task_status = str(output.get("task_status", "")).upper()
        if task_status and task_status != "SUCCEEDED":
            logger.error(_format_task_failure(task_status, output))
            if _is_no_valid_fragment(output):
                return response
            raise RuntimeError(_to_user_task_failure_message(task_status, output))
        return response

    def _load_transcription_payload(self, response) -> dict[str, object]:
        output = _response_output(response)
        transcription_url = _find_transcription_url(output)
        if transcription_url is None:
            return output

        try:
            with httpx.Client(timeout=60.0) as client:
                http_response = client.get(transcription_url)
                http_response.raise_for_status()
                payload = http_response.json()
        except Exception as error:
            raise RuntimeError(f"下载阿里云百炼转写结果失败：{error}") from error
        if not isinstance(payload, dict):
            raise RuntimeError("阿里云百炼转写结果格式无效。")
        return payload


def _normalize_dashscope_base_address(base_url: str) -> str:
    normalized = base_url.strip().rstrip("/")
    if not normalized:
        normalized = "https://dashscope.aliyuncs.com"
    if normalized.endswith("/api/v1"):
        return normalized
    if normalized.endswith("/api"):
        return f"{normalized}/v1"
    return f"{normalized}/api/v1"


def _ensure_success_response(response, context: str) -> None:
    status_code = getattr(response, "status_code", None)
    if status_code == HTTPStatus.OK:
        return
    code = getattr(response, "code", "") or ""
    message = getattr(response, "message", "") or str(response)
    details = _format_response_output(getattr(response, "output", None))
    raise RuntimeError(f"{context}：{code} {message}{details}".strip())


def _response_output(response) -> dict[str, object]:
    output = getattr(response, "output", None)
    if output is None:
        raise RuntimeError("阿里云百炼转写响应缺少 output。")
    return dict(output)


def _find_transcription_url(payload: dict[str, object]) -> str | None:
    direct_url = payload.get("transcription_url")
    if isinstance(direct_url, str) and direct_url.strip():
        return direct_url.strip()

    results = payload.get("results")
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, dict):
                continue
            item_url = item.get("transcription_url")
            if isinstance(item_url, str) and item_url.strip():
                return item_url.strip()
    return None


def _format_task_failure(task_status: str, output: dict[str, object]) -> str:
    details: list[str] = [f"阿里云百炼转写任务未成功：{task_status}"]

    task_id = output.get("task_id")
    if task_id:
        details.append(f"task_id={task_id}")

    for field_name in ("code", "message"):
        value = output.get(field_name)
        if value:
            details.append(f"{field_name}={value}")

    results = output.get("results")
    if isinstance(results, list):
        for index, item in enumerate(results, start=1):
            if not isinstance(item, dict):
                continue
            result_details = _format_result_failure(index, item)
            if result_details:
                details.append(result_details)

    if len(details) == 1:
        details.append(_format_response_output(output))
    return "；".join(details)


def _format_result_failure(index: int, item: dict[str, object]) -> str:
    fragments: list[str] = [f"result[{index}]"]
    has_error_detail = False
    for field_name in ("subtask_status", "task_status", "code", "message"):
        value = item.get(field_name)
        if value:
            fragments.append(f"{field_name}={value}")
            has_error_detail = True
    return " ".join(fragments) if has_error_detail else ""


def _format_response_output(output: object) -> str:
    if output is None:
        return ""
    try:
        return f"；output={json.dumps(output, ensure_ascii=False, default=str)[:1200]}"
    except TypeError:
        return f"；output={output}"


def _to_user_task_failure_message(task_status: str, output: dict[str, object]) -> str:
    error_code = _find_first_error_code(output)
    if error_code == "SUCCESS_WITH_NO_VALID_FRAGMENT":
        return "阿里云百炼转写失败：未识别到有效语音片段，请检查音频是否包含清晰人声。"
    return f"阿里云百炼转写失败：任务状态 {task_status}，请检查音频内容、格式或稍后重试。"


def _find_first_error_code(output: dict[str, object]) -> str:
    code = output.get("code")
    if code:
        return str(code)

    results = output.get("results")
    if isinstance(results, list):
        for item in results:
            if not isinstance(item, dict):
                continue
            item_code = item.get("code")
            if item_code:
                return str(item_code)
    return ""


def _extract_oss_url(upload_result) -> str | None:
    """兼容 DashScope SDK 的上传返回值。

    dashscope 1.26.x 的 `OssUtils.upload` 返回 `(oss_url, upload_certificate)`；
    部分旧版本直接返回 `oss_url` 字符串。
    """
    if isinstance(upload_result, str):
        return upload_result
    if isinstance(upload_result, tuple) and upload_result:
        first_item = upload_result[0]
        if isinstance(first_item, str):
            return first_item
    return None


def _parse_transcript_payload(payload: dict[str, object], *, language: str) -> Transcript:
    segments: list[TranscriptSegment] = []
    if _is_no_valid_fragment(payload):
        return Transcript(
            language=language,
            segments=[
                TranscriptSegment(
                    start_seconds=0.0,
                    end_seconds=0.0,
                    text="无明显人声",
                )
            ],
        )

    for sentence in _iter_sentences(payload):
        text = str(sentence.get("text", "")).strip()
        if not text:
            continue
        segments.append(
            TranscriptSegment(
                start_seconds=_milliseconds_to_seconds(sentence.get("begin_time")),
                end_seconds=_milliseconds_to_seconds(sentence.get("end_time")),
                text=text,
            )
        )
    return Transcript(language=language, segments=segments)


def _is_no_valid_fragment(payload: dict[str, object]) -> bool:
    if payload.get("code") == "SUCCESS_WITH_NO_VALID_FRAGMENT":
        return True

    results = payload.get("results")
    if isinstance(results, list):
        for item in results:
            if isinstance(item, dict) and item.get("code") == "SUCCESS_WITH_NO_VALID_FRAGMENT":
                return True
    return False


def _iter_sentences(payload: dict[str, object]):
    transcripts = payload.get("transcripts")
    if isinstance(transcripts, list):
        for transcript in transcripts:
            if not isinstance(transcript, dict):
                continue
            sentences = transcript.get("sentences")
            if isinstance(sentences, list):
                yield from (sentence for sentence in sentences if isinstance(sentence, dict))
        return

    sentences = payload.get("sentences")
    if isinstance(sentences, list):
        yield from (sentence for sentence in sentences if isinstance(sentence, dict))


def _milliseconds_to_seconds(value: object) -> float:
    try:
        return float(value) / 1000.0
    except (TypeError, ValueError):
        return 0.0


def _report(on_progress: Callable[[float], None] | None, ratio: float) -> None:
    if on_progress is not None:
        on_progress(ratio)
