"""Remove a deleted workflow's run directories without touching anything outside the runs root."""

from __future__ import annotations

import logging
import pathlib
import shutil
from collections.abc import Iterable
from dataclasses import dataclass, field

_logger = logging.getLogger(__name__)

RUN_DIR_PREFIX = "run_"


@dataclass
class RunDirCleanup:
    removed: list[pathlib.Path] = field(default_factory=list)
    kept: list[pathlib.Path] = field(default_factory=list)


def _strictly_under(path: pathlib.Path, root: pathlib.Path) -> bool:
    return path != root and path.is_relative_to(root)


def owns_workflow_folder(folder: pathlib.Path, workflow_id: str) -> bool:
    """True when ``folder`` is the per-workflow ``wf-NNNN-<slug>`` folder for ``workflow_id``."""
    return folder.name == workflow_id or folder.name.startswith(f"{workflow_id}-")


def _holds_any(path: pathlib.Path, protected: list[pathlib.Path]) -> bool:
    return any(p == path or p.is_relative_to(path) for p in protected)


def remove_workflow_run_dirs(
    run_dir: pathlib.Path,
    root: pathlib.Path,
    workflow_id: str,
    protected_dirs: Iterable[pathlib.Path] = (),
) -> RunDirCleanup:
    """Delete a workflow's run directory, its sibling ``run_*`` dirs, then empty parents.

    Siblings are removed only when the parent folder is this workflow's own ``wf-NNNN-*``
    folder. Symlinks are never followed, directories holding another registry row's run are
    kept, and empty parents are pruned up to (never including) ``root``.
    """
    root = root.resolve()
    run_dir = run_dir.resolve()
    result = RunDirCleanup()
    if not _strictly_under(run_dir, root):
        raise ValueError(f"{run_dir} is not under {root}")
    protected = [p.resolve() for p in protected_dirs]

    parent = run_dir.parent
    targets = [run_dir]
    if _strictly_under(parent, root) and owns_workflow_folder(parent, workflow_id) and parent.is_dir():
        for child in sorted(parent.iterdir()):
            if child == run_dir or child.is_symlink() or not child.is_dir():
                continue
            if child.name.startswith(RUN_DIR_PREFIX):
                targets.append(child)

    for target in targets:
        if not target.exists():
            continue
        if target.is_symlink() or _holds_any(target, protected):
            result.kept.append(target)
            continue
        try:
            shutil.rmtree(target)
            result.removed.append(target)
        except OSError:
            _logger.warning("Failed to remove run directory %s", target, exc_info=True)
            result.kept.append(target)

    current = parent
    while _strictly_under(current, root):
        try:
            current.rmdir()
        except OSError:
            break
        result.removed.append(current)
        current = current.parent
    return result
