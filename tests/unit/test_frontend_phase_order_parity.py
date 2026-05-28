from __future__ import annotations

import re
from pathlib import Path

from src.orchestration.resume import PHASE_ORDER as BACKEND_PHASE_ORDER


def _load_frontend_resume_phase_order() -> list[str]:
    repo_root = Path(__file__).resolve().parents[2]
    constants_path = repo_root / "frontend" / "src" / "lib" / "constants.ts"
    text = constants_path.read_text(encoding="utf-8")

    match = re.search(
        r"export const RESUME_PHASE_ORDER = \[(.*?)\] as const",
        text,
        flags=re.DOTALL,
    )
    assert match, "RESUME_PHASE_ORDER block not found in frontend constants.ts"
    body = match.group(1)
    return re.findall(r'"([^"]+)"', body)


def test_frontend_resume_phase_order_matches_backend_user_visible_flow() -> None:
    frontend_order = _load_frontend_resume_phase_order()
    backend_user_visible_order = [phase for phase in BACKEND_PHASE_ORDER if phase != "phase_7_audit"]
    assert frontend_order == backend_user_visible_order
