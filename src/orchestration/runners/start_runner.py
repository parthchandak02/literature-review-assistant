"""Runner helpers for StartNode and ResumeStartNode."""

from __future__ import annotations

from pathlib import Path

from src.config.loader import load_configs
from src.db.database import get_db
from src.db.repositories import WorkflowRepository
from src.db.workflow_registry import DRAFT_REGISTRY_STATUSES, allocate_workflow_id, find_by_workflow_id
from src.db.workflow_registry import register as register_workflow
from src.orchestration.helpers.runtime import hash_config as helper_hash_config
from src.orchestration.state import ReviewState
from src.utils import structured_log
from src.utils.logging_paths import create_run_paths, default_run_artifacts


def _rc(state: ReviewState):
    return getattr(state, "run_context", None)


def _now_utc() -> str:
    from datetime import UTC, datetime

    return datetime.now(UTC).strftime("%Y%m%d-%H%M%S")


async def run_start_node(state: ReviewState) -> None:
    """Populate initial workflow state and run paths."""
    rc = _rc(state)
    if rc:
        rc.emit_phase_start("start", "Loading configs...")
    review, settings = load_configs(state.review_path, state.settings_path)
    state.review = review
    state.settings = settings
    state.run_id = _now_utc()

    reserved_id = (state.workflow_id or "").strip()
    reg_entry = await find_by_workflow_id(state.run_root, reserved_id) if reserved_id else None
    if reg_entry is not None and reg_entry.status in DRAFT_REGISTRY_STATUSES:
        state.workflow_id = reserved_id
        state.db_path = reg_entry.db_path
        run_dir = Path(reg_entry.db_path).parent
        state.log_dir = str(run_dir)
        state.output_dir = str(run_dir)
        structured_log.configure_run_logging(state.log_dir)
        structured_log.bind_run(state.workflow_id, state.run_id, log_dir=state.log_dir)
        state.artifacts.update(default_run_artifacts(run_dir))

        config_src = Path(state.review_path) if Path(state.review_path).exists() else Path("config/review.yaml")
        header = f"# workflow_id: {state.workflow_id}\n# run_dir: {run_dir}\n# created_at: {state.run_id}\n#\n"
        if config_src.exists():
            yaml_text = config_src.read_text(encoding="utf-8")
            (run_dir / "config_snapshot.yaml").write_text(header + yaml_text, encoding="utf-8")
            (run_dir / "review.yaml").write_text(yaml_text, encoding="utf-8")
            config_hash = helper_hash_config(str(config_src))
        else:
            (run_dir / "config_snapshot.yaml").write_text(header, encoding="utf-8")
            config_hash = ""

        async with get_db(state.db_path) as db:
            repository = WorkflowRepository(db)
            await repository.create_workflow(state.workflow_id, state.review.research_question, config_hash)

        await register_workflow(
            run_root=state.run_root,
            workflow_id=state.workflow_id,
            topic=state.review.research_question,
            config_hash=config_hash,
            db_path=state.db_path,
            status="running",
        )

        if rc is not None:
            if hasattr(rc, "notify_workflow_id"):
                rc.notify_workflow_id(state.workflow_id, state.run_root)
            rc.emit_phase_done("start", {"workflow_id": state.workflow_id})
            if hasattr(rc, "set_db_path"):
                rc.set_db_path(state.db_path)
        return

    state.workflow_id = await allocate_workflow_id(state.run_root)

    run_paths = create_run_paths(
        run_root=state.run_root,
        workflow_description=review.research_question,
        workflow_id=state.workflow_id,
    )
    state.log_dir = str(run_paths.run_dir)
    state.output_dir = str(run_paths.run_dir)
    state.db_path = str(run_paths.runtime_db)
    structured_log.configure_run_logging(state.log_dir)
    structured_log.bind_run(state.workflow_id, state.run_id, log_dir=state.log_dir)
    state.artifacts.update(default_run_artifacts(run_paths.run_dir))

    config_src = Path(state.review_path) if Path(state.review_path).exists() else Path("config/review.yaml")
    snapshot_dest = run_paths.run_dir / "config_snapshot.yaml"
    header = f"# workflow_id: {state.workflow_id}\n# run_dir: {run_paths.run_dir}\n# created_at: {state.run_id}\n#\n"
    if config_src.exists():
        snapshot_dest.write_text(
            header + config_src.read_text(encoding="utf-8"),
            encoding="utf-8",
        )
    else:
        snapshot_dest.write_text(header, encoding="utf-8")

    review_yaml_dest = run_paths.run_dir / "review.yaml"
    if config_src.exists():
        review_yaml_dest.write_text(config_src.read_text(encoding="utf-8"), encoding="utf-8")

    config_hash = helper_hash_config(state.review_path)
    async with get_db(state.db_path) as db:
        repository = WorkflowRepository(db)
        await repository.create_workflow(state.workflow_id, state.review.research_question, config_hash)

    await register_workflow(
        run_root=state.run_root,
        workflow_id=state.workflow_id,
        topic=state.review.research_question,
        config_hash=config_hash,
        db_path=state.db_path,
        status="running",
    )

    if rc is not None:
        if hasattr(rc, "notify_workflow_id"):
            rc.notify_workflow_id(state.workflow_id, state.run_root)
        rc.emit_phase_done("start", {"workflow_id": state.workflow_id})
        if hasattr(rc, "set_db_path"):
            rc.set_db_path(state.db_path)


async def resolve_resume_next_phase(state: ReviewState) -> str:
    """Resolve next phase key for resume routing."""
    rc = _rc(state)
    if rc:
        rc.emit_phase_start("resume", f"Resuming from {state.next_phase}...")
    structured_log.configure_run_logging(state.log_dir)
    structured_log.bind_run(state.workflow_id, state.run_id or "resume", log_dir=state.log_dir)
    try:
        reg_entry = await find_by_workflow_id(state.run_root, state.workflow_id)
        if reg_entry and str(getattr(reg_entry, "status", "")) == "awaiting_review":
            return "human_review_checkpoint"
        if reg_entry and str(getattr(reg_entry, "status", "")) == "awaiting_prospero":
            return "phase_1_prospero_gate"
    except Exception:
        pass
    return state.next_phase or "phase_1_prospero_gate"
