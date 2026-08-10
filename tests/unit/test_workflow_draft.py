import pytest

from src.web.workflow_draft import reserve_workflow_draft, save_workflow_config_draft


@pytest.mark.asyncio
async def test_reserve_and_save_config_draft(tmp_path) -> None:
    run_root = str(tmp_path / "runs")
    reserved = await reserve_workflow_draft(run_root=run_root, topic="Chair volleyball in care homes")
    workflow_id = reserved["workflow_id"]
    assert workflow_id.startswith("wf-")

    yaml = "research_question: Chair volleyball in care homes\n"
    await save_workflow_config_draft(
        run_root=run_root,
        workflow_id=workflow_id,
        review_yaml=yaml,
    )

    from src.db.workflow_registry import find_by_workflow_id

    entry = await find_by_workflow_id(run_root, workflow_id)
    assert entry is not None
    assert entry.status == "config_ready"
    assert (tmp_path / "runs").exists()
