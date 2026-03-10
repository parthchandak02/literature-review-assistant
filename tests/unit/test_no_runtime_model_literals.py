from __future__ import annotations

from pathlib import Path


def test_no_runtime_model_literals_in_src() -> None:
    """Enforce YAML as single source of model IDs.

    Runtime model IDs must not be hardcoded in src/ Python files.
    """
    src_root = Path(__file__).resolve().parents[2] / "src"
    forbidden_tokens = (
        "google-gla:gemini-",
        "google-vertex:gemini-",
        "anthropic:claude-",
        "openai:gpt-",
    )

    violations: list[str] = []
    for py_file in src_root.rglob("*.py"):
        text = py_file.read_text(encoding="utf-8")
        for line_no, line in enumerate(text.splitlines(), start=1):
            if any(token in line for token in forbidden_tokens):
                rel = py_file.relative_to(src_root.parent)
                violations.append(f"{rel}:{line_no}: {line.strip()}")

    assert not violations, (
        "Runtime provider model literals found in src/. "
        "Define model IDs only in config/settings.yaml.\n" + "\n".join(violations)
    )
