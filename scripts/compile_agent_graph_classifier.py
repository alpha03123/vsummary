from __future__ import annotations

import argparse
from pathlib import Path
import sys
import os

import dspy

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from backend.agent_graph.dspy_compile import compile_classifier_program, evaluate_classifier_program
from backend.agent_graph.dspy_dataset import build_classifier_devset, build_classifier_trainset, slice_examples
from backend.agent_graph.dspy_lm import ProxyStreamingLM
from backend.video_summary.infrastructure.settings import load_env_settings, normalize_openai_base_url


def main() -> int:
    os.environ.setdefault("PYTHONUTF8", "1")
    parser = argparse.ArgumentParser(description="Compile DSPy classifier program for the agent graph.")
    parser.add_argument("--output-dir", default=str(ROOT / "data" / "agent_graph" / "dspy" / "classifier"))
    parser.add_argument("--train-limit", type=int, default=20)
    parser.add_argument("--dev-limit", type=int, default=9)
    parser.add_argument("--eval-threads", type=int, default=4)
    args = parser.parse_args()

    env = load_env_settings(ROOT)
    if not env.api_key.strip():
        raise RuntimeError("缺少 API Key，无法执行 DSPy compile。")

    dspy.configure(
        lm=ProxyStreamingLM(
            model=f"openai/{env.model.strip()}",
            api_base=normalize_openai_base_url(env.base_url),
            api_key=env.api_key.strip(),
        )
    )

    plan_dir = ROOT / "docs" / "plan"
    trainset = slice_examples(build_classifier_trainset(plan_dir), args.train_limit)
    devset = slice_examples(build_classifier_devset(plan_dir), args.dev_limit)
    compiled = compile_classifier_program(trainset=trainset)
    evaluation = evaluate_classifier_program(
        program=compiled,
        devset=devset,
        num_threads=args.eval_threads,
    )

    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    compiled.save(str(output_dir / "program.json"))

    print(f"trainset={len(trainset)}")
    print(f"devset={len(devset)}")
    print(f"evaluation={evaluation}")
    print(f"saved={output_dir / 'program.json'}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
