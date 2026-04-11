from __future__ import annotations

import argparse
from collections import Counter
from pathlib import Path
import sys

import dspy

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.dspy_compile import ClassifierMetric, SeriesQueryClassifierModule
from backend.agent_graph.dspy_dataset import build_classifier_devset
from backend.agent_graph.dspy_lm import ProxyStreamingLM
from backend.video_summary.infrastructure.settings import load_env_settings, normalize_openai_base_url


def main() -> int:
    parser = argparse.ArgumentParser(description="Analyze zero-shot classifier errors on the devset.")
    parser.add_argument("--limit", type=int, default=9)
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

    module = SeriesQueryClassifierModule()
    devset = build_classifier_devset(ROOT / "docs" / "plan")[: args.limit]
    metric = ClassifierMetric()
    field_hits = Counter()

    for example in devset:
        try:
            prediction = module(**example.inputs())
            score = metric(example, prediction)
        except Exception as error:
            prediction = {}
            score = 0.0
            print("---")
            print(f"id={example.id}")
            print(f"user_message={example.user_message}")
            print(f"error={type(error).__name__}: {error}")
            continue
        print("---")
        print(f"id={example.id}")
        print(f"user_message={example.user_message}")
        print(f"expected_goal={example.goal} predicted_goal={getattr(prediction, 'goal', None)}")
        print(f"expected_target_source={example.target_source} predicted_target_source={getattr(prediction, 'target_source', None)}")
        print(f"expected_context_need={example.context_need} predicted_context_need={getattr(prediction, 'context_need', None)}")
        print(f"expected_action_name={example.action_name} predicted_action_name={getattr(prediction, 'action_name', None)}")
        print(f"score={score}")
        for key in ("goal", "target_source", "context_need", "action_name"):
            if getattr(prediction, key, None) == getattr(example, key, None):
                field_hits[key] += 1

    total = len(devset)
    print("===")
    print(f"devset={total}")
    for key in ("goal", "target_source", "context_need", "action_name"):
        print(f"{key}_acc={field_hits[key]}/{total}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
