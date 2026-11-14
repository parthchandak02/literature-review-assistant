"""Lock import paths that used to emit deprecation warnings at test startup."""

from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def _python(code: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["PYTHONPATH"] = str(ROOT) + os.pathsep + env.get("PYTHONPATH", "")
    return subprocess.run(
        [sys.executable, "-W", "always", "-c", code],
        cwd=ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )


def test_workflow_graph_import_has_no_deprecation_warning() -> None:
    result = _python(
        "import warnings\n"
        "warnings.simplefilter('always')\n"
        "with warnings.catch_warnings(record=True) as caught:\n"
        "    warnings.simplefilter('always')\n"
        "    from src.orchestration.workflow import RUN_GRAPH\n"
        "    assert RUN_GRAPH is not None\n"
        "bad = [\n"
        "    str(item.message)\n"
        "    for item in caught\n"
        "    if 'deprecated' in str(item.message).lower() and 'Graph' in str(item.message)\n"
        "]\n"
        "print('\\n'.join(bad))\n"
        "raise SystemExit(1 if bad else 0)\n"
    )
    assert result.returncode == 0, result.stdout + result.stderr


def test_google_genai_types_import_has_no_union_alias_warning() -> None:
    result = _python(
        "import warnings\n"
        "warnings.simplefilter('always')\n"
        "with warnings.catch_warnings(record=True) as caught:\n"
        "    warnings.simplefilter('always')\n"
        "    import google.genai.types\n"
        "    assert google.genai.types is not None\n"
        "bad = [str(item.message) for item in caught if '_UnionGenericAlias' in str(item.message)]\n"
        "print('\\n'.join(bad))\n"
        "raise SystemExit(1 if bad else 0)\n"
    )
    assert result.returncode == 0, result.stdout + result.stderr
