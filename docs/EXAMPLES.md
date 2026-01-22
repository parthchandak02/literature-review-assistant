# Examples

Code examples and use cases for the Literature Review Assistant.

## Table of Contents

- [Citation Resolution](#citation-resolution)
- [Multi-Journal Submission](#multi-journal-submission)
- [Custom Templates](#custom-templates)
- [Git Workflow](#git-workflow)
- [Complete Workflow with Manuscript Pipeline](#complete-workflow-with-manuscript-pipeline)

## Citation Resolution

Resolve citations during workflow:

```bash
# Resolve single citation
python main.py --resolve-citation doi:10.1038/nbt.3780

# Use in manuscript (auto-resolved if enabled)
# Write: "Previous work [@doi:10.1038/nbt.3780] showed..."
# System resolves to: "Previous work [1] showed..."
```

## Multi-Journal Submission

Generate packages for multiple journals:

```python
from src.export.submission_package import SubmissionPackageBuilder
from pathlib import Path

builder = SubmissionPackageBuilder(Path("data/outputs"))
packages = builder.build_for_multiple_journals(
    workflow_outputs,
    journals=["ieee", "nature", "plos"],
    manuscript_markdown=Path("data/outputs/final_report.md"),
)

for journal, package_dir in packages.items():
    print(f"{journal}: {package_dir}")
```

## Custom Templates

Create and use custom journal template:

```python
from src.export.template_manager import TemplateManager

manager = TemplateManager()
template_content = """
\\documentclass{article}
\\usepackage{...}
\\begin{document}
$body$
\\end{document}
"""
manager.create_custom_template("myjournal", template_content)
```

## Git Workflow

Version control for manuscript:

```python
from src.version_control.git_manager import GitManuscriptManager
from pathlib import Path

# Initialize repository
git_manager = GitManuscriptManager(Path("data/outputs/manuscript"))
git_manager.initialize_repo()

# Make changes to manuscript files...

# Commit changes
git_manager.commit_changes("Updated introduction section")

# Create revision branch
git_manager.create_branch("revision-round-1")
git_manager.commit_changes("Addressed reviewer comments")
```

## Complete Workflow with Manuscript Pipeline

```bash
# Run full workflow with Manubot export and submission package
python main.py --manubot-export --build-package --journal ieee

# Or enable in config/workflow.yaml and run normally
python main.py
```
