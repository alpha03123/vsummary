from __future__ import annotations

import importlib.util
import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


def _load_script_module():
    module_path = ROOT / "scripts" / "run_new_arch_long_tests.py"
    spec = importlib.util.spec_from_file_location("run_new_arch_long_tests", module_path)
    assert spec is not None
    assert spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class RunNewArchLongTestsScriptTests(unittest.TestCase):
    def test_run_case_saves_debug_trace_payload(self) -> None:
        module = _load_script_module()
        case = module.LongTestCase(
            case_id="lt-test",
            title="测试",
            session_id="series|series-a|series-home|lt-test",
            turns=(module.LongTestTurn(message="问题"),),
            focus="focus",
        )
        fake_result = SimpleNamespace(
            thinking_summaries=["摘要"],
            tool_rows=["- get_video_summary [ok]"],
            final_answer="答案",
            raw_events=[{"type": "answer_completed", "payload": {"message": "答案"}, "elapsed_ms": 12}],
            debug_trace={"graph_result": {"answer": "答案"}},
        )

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_root = Path(temp_dir)
            with (
                patch.object(module, "ROOT", temp_root),
                patch.object(module, "run_agent_case", return_value=fake_result),
            ):
                module._run_case(
                    container=object(),
                    case=case,
                    show_raw_events=False,
                    max_turns=None,
                    save_trace=True,
                    debug_trace=True,
                )

            payload = json.loads((temp_root / "temp" / "long-test-traces" / "lt-test.json").read_text(encoding="utf-8"))
            self.assertEqual(payload["turns"][0]["debug_trace"]["graph_result"]["answer"], "答案")
            self.assertEqual(payload["turns"][0]["duration_ms"], 12)


if __name__ == "__main__":
    unittest.main()
