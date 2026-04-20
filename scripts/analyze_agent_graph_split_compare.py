from __future__ import annotations

import argparse
from pathlib import Path
import sys

import dspy

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.dspy.dspy_lm import ProxyStreamingLM
from backend.agent_graph.dspy.split_compare_compile import SplitCompareMetric, SplitCompareModule
from backend.agent_graph.split_compare_dataset import build_split_compare_devset
from backend.video_summary.infrastructure.settings import load_env_settings, normalize_openai_base_url


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze zero-shot split_compare quality.")
    parser.add_argument("--limit", type=int, default=5)
    args = parser.parse_args()

    env = load_env_settings(ROOT)
    if not env.api_key.strip():
        raise RuntimeError("缺少 API Key，无法执行 DSPy analysis。")

    dspy.configure(
        lm=ProxyStreamingLM(
            model=f"openai/{env.model.strip()}",
            api_base=normalize_openai_base_url(env.base_url),
            api_key=env.api_key.strip(),
        )
    )

    module = SplitCompareModule()
    devset = build_split_compare_devset(ROOT / "docs" / "plan")[: args.limit]
    metric = SplitCompareMetric()

    for example in devset:
        prediction = module(**example.inputs())
        score = metric(example, prediction)
        print("---")
        print(f"id={example.id}")
        print(f"user_message={example.user_message}")
        print(f"expected_queries={example.queries}")
        print(f"predicted_queries={getattr(prediction, 'queries', None)}")
        print(f"score={score}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
