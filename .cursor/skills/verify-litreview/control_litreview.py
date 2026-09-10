#!/usr/bin/env python3
"""Agent-friendly verification CLI for literature-review-assistant (pstack-style lever)."""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[3]
SCOPING_FIXTURE = REPO_ROOT / "tests/fixtures/scoping/review_scoping_smoke.yaml"


def _emit(payload: dict[str, Any], as_json: bool) -> None:
    if as_json:
        print(json.dumps(payload, indent=2))
    else:
        for key, value in payload.items():
            print(f"{key}: {value}")


def _run(cmd: list[str], cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, cwd=cwd or REPO_ROOT, capture_output=True, text=True, check=False)


def cmd_doctor(args: argparse.Namespace, as_json: bool) -> int:
    checks: dict[str, Any] = {}
    pm2 = _run(["pm2", "jlist"])
    checks["pm2_ok"] = pm2.returncode == 0
    if pm2.returncode == 0:
        try:
            processes = json.loads(pm2.stdout or "[]")
            checks["pm2_processes"] = [
                {"name": p.get("name"), "status": p.get("pm2_env", {}).get("status")}
                for p in processes
                if str(p.get("name", "")).startswith("litreview-")
            ]
        except json.JSONDecodeError:
            checks["pm2_processes"] = []
    health = _run(["curl", "-sf", f"{args.base_url}/api/health"])
    checks["api_health_ok"] = health.returncode == 0
    ruff = _run(["uv", "run", "ruff", "check", "src/models", "src/web/config_generator.py", "-q"])
    checks["ruff_ok"] = ruff.returncode == 0
    tsc = _run(["./node_modules/.bin/tsc", "-b", "--noEmit"], cwd=REPO_ROOT / "frontend")
    checks["frontend_typecheck_ok"] = tsc.returncode == 0
    ok = all([checks["pm2_ok"], checks["api_health_ok"], checks["ruff_ok"], checks["frontend_typecheck_ok"]])
    payload = {"command": "doctor", "ok": ok, "checks": checks}
    _emit(payload, as_json)
    if not ok and not as_json and not checks["api_health_ok"]:
        print("Hint: run ./scripts/ops_pm2.sh restart --backend-only", file=sys.stderr)
    return 0 if ok else 1


def cmd_profile_resolve(args: argparse.Namespace) -> int:
    config_path = Path(args.config)
    if not config_path.is_absolute():
        config_path = REPO_ROOT / config_path
    proc = _run(["uv", "run", "python", "scripts/check.py", "config-methodology", str(config_path)])
    if proc.returncode != 0:
        print(proc.stderr or proc.stdout, file=sys.stderr)
        return proc.returncode
    print(proc.stdout.strip())
    return 0


def cmd_phase1_gate(args: argparse.Namespace, as_json: bool) -> int:
    steps: list[dict[str, Any]] = []
    pytest = _run(["uv", "run", "pytest", "tests/unit/test_methodology_profile.py", "tests/unit/test_pcc_config.py", "tests/unit/test_config_generator_scoping.py", "-q"])
    steps.append({"name": "phase1_unit_tests", "ok": pytest.returncode == 0})
    methodology = _run(["uv", "run", "python", "scripts/check.py", "config-methodology", str(SCOPING_FIXTURE)])
    steps.append({"name": "scoping_fixture", "ok": methodology.returncode == 0})
    vitest = _run(["./node_modules/.bin/vitest", "run", "ReviewTypeDecisionStage"], cwd=REPO_ROOT / "frontend")
    steps.append({"name": "wizard_tests", "ok": vitest.returncode == 0})
    tsc = _run(["./node_modules/.bin/tsc", "-b", "--noEmit"], cwd=REPO_ROOT / "frontend")
    steps.append({"name": "frontend_typecheck", "ok": tsc.returncode == 0})
    ok = all(step["ok"] for step in steps)
    _emit({"command": "phase1-gate", "ok": ok, "steps": steps}, as_json)
    return 0 if ok else 1


def cmd_sr_regression(args: argparse.Namespace, as_json: bool) -> int:
    if args.quick:
        pytest = _run(["uv", "run", "pytest", "tests/unit/test_methodology_profile.py", "tests/unit/test_config_generator.py", "-q", "--tb=no"])
        ok = pytest.returncode == 0
        _emit({"command": "sr-regression", "mode": "quick", "ok": ok}, as_json)
        return 0 if ok else 1
    proc = _run(["make", "check-local"])
    ok = proc.returncode == 0
    _emit({"command": "sr-regression", "mode": "full", "ok": ok, "tail": (proc.stdout or proc.stderr or "")[-800:]}, as_json)
    return 0 if ok else 1


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="control_litreview")
    sub = parser.add_subparsers(dest="command", required=True)
    doctor = sub.add_parser("doctor")
    doctor.add_argument("--base-url", default="http://127.0.0.1:8001")
    profile = sub.add_parser("profile-resolve")
    profile.add_argument("--config", default=str(SCOPING_FIXTURE.relative_to(REPO_ROOT)))
    sub.add_parser("phase1-gate")
    sr = sub.add_parser("sr-regression")
    sr.add_argument("--quick", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    raw = list(argv or sys.argv[1:])
    as_json = "--json" in raw
    if as_json:
        raw = [a for a in raw if a != "--json"]
    args = _build_parser().parse_args(raw)
    if args.command == "doctor":
        return cmd_doctor(args, as_json)
    if args.command == "profile-resolve":
        return cmd_profile_resolve(args)
    if args.command == "phase1-gate":
        return cmd_phase1_gate(args, as_json)
    if args.command == "sr-regression":
        return cmd_sr_regression(args, as_json)
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
