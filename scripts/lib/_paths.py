from __future__ import annotations

import os
import sys
from pathlib import Path


def resolve_repo_root() -> Path:
    if os.environ.get("LITREVIEW_ROOT"):
        return Path(os.environ["LITREVIEW_ROOT"]).expanduser().resolve()
    return Path(__file__).resolve().parents[2]


def ensure_repo_on_path() -> Path:
    root = resolve_repo_root()
    root_str = str(root)
    if root_str not in sys.path:
        sys.path.insert(0, root_str)
    return root
