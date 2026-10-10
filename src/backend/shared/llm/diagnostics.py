"""LLM lifecycle diagnostics without prompts, credentials or model output."""

import json
import logging

from backend.core.metering import current_operation_id

LOGGER = logging.getLogger(__name__)


def log_llm_event(event, **fields):
    LOGGER.info(json.dumps({"event": event, "operation_id": current_operation_id(), **fields}, ensure_ascii=False))
