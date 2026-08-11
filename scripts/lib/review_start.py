import argparse
import asyncio
import os
import sys
from pathlib import Path


def _resolve_repo_root() -> Path:
    if os.environ.get("LITREVIEW_ROOT"):
        return Path(os.environ["LITREVIEW_ROOT"]).expanduser().resolve()
    return Path(__file__).resolve().parent.parent.parent


REPO_ROOT = _resolve_repo_root()
sys.path.insert(0, str(REPO_ROOT))

try:
    from src.web.config_generator import generate_config_yaml
except ImportError as exc:
    print(f"Error: unable to import src.web.config_generator from {REPO_ROOT}: {exc}")
    print("Hint: set LITREVIEW_ROOT to your repo path or run this script from the cloned repo.")
    raise SystemExit(1) from exc


async def run_start(question: str, profile: str, output: str) -> int:
    print(f"Generating review config for question: {question!r}")
    output_path = Path(output)
    if not output_path.is_absolute():
        output_path = REPO_ROOT / output_path
    try:
        yaml_content = await generate_config_yaml(
            research_question=question,
            generation_profile=profile,
        )
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(yaml_content, encoding="utf-8")
    except Exception as exc:
        print(f"Error generating config: {exc}")
        return 1
    print(f"Generated config written to: {output_path}")
    return 0


async def _main() -> int:
    parser = argparse.ArgumentParser(description="Generate review.yaml for a systematic literature review.")
    parser.add_argument("--question", required=True, help="Plain-English research question.")
    parser.add_argument(
        "--profile",
        default="standard",
        choices=["standard", "health_sdg"],
        help="Generation profile for config synthesis.",
    )
    parser.add_argument(
        "--output",
        default="config/review.yaml",
        help="Output path for generated YAML (absolute or relative to repo root).",
    )
    args = parser.parse_args()
    return await run_start(question=args.question, profile=args.profile, output=args.output)


if __name__ == "__main__":
    raise SystemExit(asyncio.run(_main()))
