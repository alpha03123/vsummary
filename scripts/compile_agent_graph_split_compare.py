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

from backend.agent_graph.dspy.dspy_lm import ProxyStreamingLM
from backend.agent_graph.dspy.split_compare_compile import SplitCompareMetric, compile_split_compare_program
from backend.agent_graph.split_compare_dataset import build_split_compare_devset, build_split_compare_trainset
from backend.video_summary.infrastructure.settings import load_env_settings, normalize_openai_base_url


def main() -> int:
    os.environ.setdefault("PYTHONUTF8", "1")
    parser = argparse.ArgumentParser(description="Compile DSPy split_compare program.")
    parser.add_argument("--output-dir", default=str(ROOT / "data" / "agent_graph" / "dspy" / "split_compare"))
    parser.add_argument("--train-limit", type=int, default=20)
    parser.add_argument("--dev-limit", type=int, default=10)
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

    trainset = build_split_compare_trainset(ROOT / "docs" / "plan")[: args.train_limit]
    devset = build_split_compare_devset(ROOT / "docs" / "plan")[: args.dev_limit]
    compiled = compile_split_compare_program(trainset=trainset)
    evaluator = dspy.Evaluate(
        devset=devset,
        metric=SplitCompareMetric(),
        num_threads=args.eval_threads,
        display_progress=False,
        display_table=False,
    )
    evaluation = evaluator(compiled)

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
