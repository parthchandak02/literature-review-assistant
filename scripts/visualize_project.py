#!/usr/bin/env python3
"""
Project Visualization Script

Generates multiple visualizations of the project structure:
1. Module dependency graph (using pydeps or graphviz)
2. Workflow diagram (Mermaid)
3. Project structure tree
4. Import dependency graph

Usage:
    python scripts/visualize_project.py [--format png|svg|html] [--output-dir OUTPUT_DIR]
"""

import os
import sys
import subprocess
import json
from pathlib import Path
from typing import Dict, List, Optional, Set, Tuple
import argparse

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

try:
    from rich.console import Console
    from rich.tree import Tree
    from rich import print as rprint
    HAS_RICH = True
    console = Console()
except ImportError:
    HAS_RICH = False
    # Fallback console
    class SimpleConsole:
        def print(self, msg):
            print(msg)
    console = SimpleConsole()


def check_tool_available(tool_name: str) -> bool:
    """Check if a command-line tool is available."""
    try:
        subprocess.run(
            [tool_name, "--version"],
            capture_output=True,
            check=True,
            timeout=5
        )
        return True
    except (subprocess.CalledProcessError, FileNotFoundError, subprocess.TimeoutExpired):
        return False


def install_pydeps():
    """Install pydeps if not available."""
    console.print("[yellow]pydeps not found. Installing...[/yellow]")
    try:
        subprocess.run(
            [sys.executable, "-m", "pip", "install", "pydeps"],
            check=True,
            cwd=project_root
        )
        console.print("[green]pydeps installed successfully[/green]")
        return True
    except subprocess.CalledProcessError:
        console.print("[red]Failed to install pydeps[/red]")
        return False


def generate_pydeps_graph(output_dir: Path, format: str = "png") -> Optional[Path]:
    """Generate dependency graph using pydeps."""
    if not check_tool_available("pydeps"):
        if not install_pydeps():
            return None
    
    console.print("[cyan]Generating dependency graph with pydeps...[/cyan]")
    
    output_file = output_dir / f"dependency_graph_pydeps.{format}"
    
    try:
        # Generate graph for main entry point
        cmd = [
            "pydeps",
            "main.py",
            "--max-bacon=2",  # Limit depth
            "--cluster",  # Cluster related modules
            "--show-deps",  # Show dependencies
            "--noshow",  # Don't open automatically
            "-o", str(output_file),  # Output file
            "-T", format,  # Format (png, svg, pdf)
        ]
        
        result = subprocess.run(
            cmd,
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=60
        )
        
        if result.returncode == 0 and output_file.exists():
            console.print(f"[green]Generated: {output_file}[/green]")
            return output_file
        else:
            console.print(f"[yellow]pydeps output: {result.stderr}[/yellow]")
            return None
            
    except subprocess.TimeoutExpired:
        console.print("[red]pydeps timed out[/red]")
        return None
    except Exception as e:
        console.print(f"[red]Error running pydeps: {e}[/red]")
        return None


def generate_graphviz_from_dot(dot_file: Path, output_dir: Path, format: str = "png") -> Optional[Path]:
    """Generate visualization from existing DOT file using graphviz."""
    if not check_tool_available("dot"):
        console.print("[yellow]graphviz (dot) not found. Install with: brew install graphviz (macOS) or apt-get install graphviz (Linux)[/yellow]")
        return None
    
    if not dot_file.exists():
        console.print(f"[yellow]DOT file not found: {dot_file}[/yellow]")
        return None
    
    console.print(f"[cyan]Generating graph from {dot_file}...[/cyan]")
    
    output_file = output_dir / f"dependency_graph.{format}"
    
    try:
        result = subprocess.run(
            ["dot", f"-T{format}", str(dot_file), "-o", str(output_file)],
            cwd=project_root,
            capture_output=True,
            text=True,
            timeout=30
        )
        
        if result.returncode == 0 and output_file.exists():
            console.print(f"[green]Generated: {output_file}[/green]")
            return output_file
        else:
            console.print(f"[red]Error: {result.stderr}[/red]")
            return None
            
    except Exception as e:
        console.print(f"[red]Error running graphviz: {e}[/red]")
        return None


def generate_workflow_mermaid(output_dir: Path) -> Path:
    """Generate Mermaid workflow diagram."""
    console.print("[cyan]Generating workflow diagram (Mermaid)...[/cyan]")
    
    workflow_mermaid = """graph TD
    Start([Start: main.py]) --> Init[WorkflowManager<br/>Initialization]
    Init --> Phase1[Phase 1: Build Search Strategy<br/>SearchStrategyBuilder]
    Phase1 --> Phase2[Phase 2: Search Databases<br/>MultiDatabaseSearcher]
    Phase2 --> Phase3[Phase 3: Deduplication<br/>Deduplicator]
    Phase3 --> Phase4[Phase 4: Title/Abstract Screening<br/>TitleAbstractScreener]
    Phase4 --> Phase5[Phase 5: Full-text Screening<br/>FullTextScreener]
    Phase5 --> Phase6[Phase 6: Paper Enrichment<br/>PaperEnricher]
    Phase6 --> Phase7[Phase 7: Data Extraction<br/>DataExtractorAgent]
    Phase7 --> Phase8[Phase 8: Quality Assessment<br/>RiskOfBiasAssessor]
    Phase7 --> Phase9[Phase 9: PRISMA Diagram<br/>PRISMAGenerator]
    Phase7 --> Phase10[Phase 10: Visualizations<br/>ChartGenerator]
    Phase7 --> Phase11[Phase 11: Article Writing<br/>Writing Agents]
    Phase11 --> Phase12[Phase 12: Final Report<br/>Report Compilation]
    Phase8 --> Phase12
    Phase9 --> Phase12
    Phase10 --> Phase12
    Phase12 --> End([End: Output Files])
    
    style Start fill:#e1f5fe
    style End fill:#e8f5e9
    style Phase1 fill:#fff3e0
    style Phase2 fill:#fff3e0
    style Phase3 fill:#f3e5f5
    style Phase4 fill:#f3e5f5
    style Phase5 fill:#f3e5f5
    style Phase6 fill:#e8f5e9
    style Phase7 fill:#e8f5e9
    style Phase8 fill:#ffebee
    style Phase9 fill:#ffebee
    style Phase10 fill:#ffebee
    style Phase11 fill:#e1f5fe
    style Phase12 fill:#e1f5fe
"""
    
    output_file = output_dir / "workflow_diagram.mmd"
    output_file.write_text(workflow_mermaid)
    console.print(f"[green]Generated: {output_file}[/green]")
    console.print("[yellow]View at: https://mermaid.live/ or use a Mermaid viewer[/yellow]")
    
    return output_file


def generate_module_structure_tree(output_dir: Path) -> Path:
    """Generate a visual tree structure of the project."""
    console.print("[cyan]Generating module structure tree...[/cyan]")
    
    def build_tree_text(path: Path, prefix: str = "", max_depth: int = 3, current_depth: int = 0) -> List[str]:
        """Recursively build tree structure as text."""
        lines = []
        if current_depth >= max_depth:
            return lines
        
        try:
            items = sorted(path.iterdir(), key=lambda x: (x.is_file(), x.name))
            for i, item in enumerate(items):
                # Skip hidden files and common ignore patterns
                if item.name.startswith('.') or item.name in ['__pycache__', 'node_modules', '.git', '.venv', 'venv']:
                    continue
                
                is_last = i == len(items) - 1
                current_prefix = "└── " if is_last else "├── "
                next_prefix = prefix + ("    " if is_last else "│   ")
                
                if item.is_dir():
                    lines.append(f"{prefix}{current_prefix}{item.name}/")
                    lines.extend(build_tree_text(item, next_prefix, max_depth, current_depth + 1))
                elif item.suffix in ['.py', '.yaml', '.md', '.txt', '.toml']:
                    lines.append(f"{prefix}{current_prefix}{item.name}")
        except PermissionError:
            pass
        return lines
    
    tree_lines = ["Project Structure", "=" * 50]
    tree_lines.extend(build_tree_text(project_root, max_depth=3))
    
    output_file = output_dir / "project_structure.txt"
    tree_text = "\n".join(tree_lines)
    output_file.write_text(tree_text)
    
    console.print(f"[green]Generated: {output_file}[/green]")
    print(tree_text)
    
    return output_file


def analyze_imports() -> Dict[str, List[str]]:
    """Analyze Python imports across the project."""
    console.print("[cyan]Analyzing imports...[/cyan]")
    
    imports_map: Dict[str, List[str]] = {}
    src_dir = project_root / "src"
    
    for py_file in src_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
        
        try:
            content = py_file.read_text()
            module_imports = []
            
            for line in content.split('\n'):
                line = line.strip()
                if line.startswith('import ') or line.startswith('from '):
                    # Extract import name
                    if line.startswith('import '):
                        imp = line[7:].split()[0].split('.')[0]
                    else:  # from ... import
                        parts = line[5:].split('import')[0].strip().split('.')
                        imp = parts[0] if parts else ''
                    
                    if imp and imp not in ['os', 'sys', 'json', 'typing', 'pathlib', 'datetime']:
                        if imp.startswith('src.'):
                            module_imports.append(imp[4:])  # Remove 'src.' prefix
                        elif imp in ['src']:
                            continue
                        else:
                            module_imports.append(imp)
            
            if module_imports:
                rel_path = str(py_file.relative_to(project_root))
                imports_map[rel_path] = list(set(module_imports))
                
        except Exception as e:
            console.print(f"[yellow]Error analyzing {py_file}: {e}[/yellow]")
    
    return imports_map


def generate_import_graph(imports_map: Dict[str, List[str]], output_dir: Path) -> Path:
    """Generate a simplified import dependency graph."""
    console.print("[cyan]Generating import dependency graph...[/cyan]")
    
    # Create a simplified graph showing main module dependencies
    graph_lines = ["digraph G {", "  rankdir=LR;", "  node [shape=box];"]
    
    # Group by top-level module
    modules: Dict[str, Set[str]] = {}
    for file_path, imports in imports_map.items():
        if file_path.startswith('src/'):
            parts = file_path.split('/')
            if len(parts) > 1:
                module = parts[1]  # e.g., 'orchestration', 'search'
                if module not in modules:
                    modules[module] = set()
                modules[module].update(imports)
    
    # Add nodes
    for module in sorted(modules.keys()):
        graph_lines.append(f'  "{module}" [label="{module}"];')
    
    # Add edges (simplified - only show cross-module dependencies)
    for module, imports in modules.items():
        for imp in imports:
            # Check if import is another module in src/
            for other_module in modules.keys():
                if other_module != module and imp.startswith(other_module):
                    graph_lines.append(f'  "{other_module}" -> "{module}";')
                    break
    
    graph_lines.append("}")
    
    output_file = output_dir / "import_dependencies.dot"
    output_file.write_text('\n'.join(graph_lines))
    console.print(f"[green]Generated: {output_file}[/green]")
    
    # Also generate visualization if graphviz is available
    if check_tool_available("dot"):
        png_file = output_dir / "import_dependencies.png"
        try:
            subprocess.run(
                ["dot", "-Tpng", str(output_file), "-o", str(png_file)],
                check=True,
                timeout=30
            )
            console.print(f"[green]Generated: {png_file}[/green]")
        except Exception:
            pass
    
    return output_file


def generate_summary_report(output_dir: Path, generated_files: List[Path]) -> Path:
    """Generate a summary report of all visualizations."""
    console.print("[cyan]Generating summary report...[/cyan]")
    
    report = f"""# Project Visualization Summary

Generated visualizations for: {project_root.name}

## Generated Files

"""
    
    for file in generated_files:
        if file.exists():
            report += f"- `{file.name}` - {file.stat().st_size} bytes\n"
    
    report += f"""
## How to Use

### Dependency Graphs
- **dependency_graph_pydeps.png**: Full Python module dependency graph (if pydeps available)
- **dependency_graph.png**: Dependency graph from existing DOT file (if graphviz available)
- **import_dependencies.png**: Simplified import dependency graph

### Workflow Diagrams
- **workflow_diagram.mmd**: Mermaid workflow diagram
  - View online at: https://mermaid.live/
  - Or use VS Code extension: "Markdown Preview Mermaid Support"

### Project Structure
- **project_structure.txt**: Text-based project structure tree

## Tools Used

- **pydeps**: Python dependency visualization (install: `pip install pydeps`)
- **graphviz**: Graph visualization (install: `brew install graphviz` or `apt-get install graphviz`)
- **Mermaid**: Workflow diagrams (view online or use VS Code extension)

## Project Overview

This is a Literature Review Assistant - an agentic AI system that automates systematic 
literature reviews from search to publication-ready articles.

### Main Entry Point
- `main.py` - CLI entry point that initializes and runs WorkflowManager

### Core Workflow
1. Build Search Strategy
2. Search Databases (PubMed, arXiv, Semantic Scholar, etc.)
3. Deduplication
4. Title/Abstract Screening (LLM-powered)
5. Full-text Screening (LLM-powered)
6. Paper Enrichment
7. Data Extraction (LLM-powered)
8. Quality Assessment
9. PRISMA Diagram Generation
10. Visualizations
11. Article Writing (LLM-powered)
12. Final Report Compilation

### Key Modules
- `src/orchestration/` - Workflow orchestration and management
- `src/search/` - Database connectors and search functionality
- `src/screening/` - LLM-powered screening agents
- `src/extraction/` - Data extraction agents
- `src/writing/` - Article writing agents
- `src/export/` - Export and submission package generation
- `src/citations/` - Citation management and formatting
- `src/prisma/` - PRISMA diagram generation
- `src/visualization/` - Chart and graph generation

## Next Steps

1. View the workflow diagram: Open `workflow_diagram.mmd` in Mermaid Live Editor
2. Explore dependencies: Open PNG files in an image viewer
3. Understand structure: Read `project_structure.txt`
4. Analyze imports: Check `import_dependencies.dot` or PNG

"""
    
    output_file = output_dir / "VISUALIZATION_SUMMARY.md"
    output_file.write_text(report)
    console.print(f"[green]Generated: {output_file}[/green]")
    
    return output_file


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Generate visualizations of project structure and dependencies"
    )
    parser.add_argument(
        "--format",
        choices=["png", "svg", "pdf"],
        default="png",
        help="Output format for graphs (default: png)"
    )
    parser.add_argument(
        "--output-dir",
        type=str,
        default="data/outputs/visualizations",
        help="Output directory for visualizations (default: data/outputs/visualizations)"
    )
    parser.add_argument(
        "--skip-pydeps",
        action="store_true",
        help="Skip pydeps generation (faster)"
    )
    
    args = parser.parse_args()
    
    # Create output directory
    output_dir = project_root / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    
    console.print(f"[bold cyan]Project Visualization Tool[/bold cyan]")
    console.print(f"Project root: {project_root}")
    console.print(f"Output directory: {output_dir}\n")
    
    generated_files: List[Path] = []
    
    # 1. Generate workflow diagram (Mermaid)
    try:
        mermaid_file = generate_workflow_mermaid(output_dir)
        generated_files.append(mermaid_file)
    except Exception as e:
        console.print(f"[red]Error generating workflow diagram: {e}[/red]")
    
    # 2. Generate project structure tree
    try:
        tree_file = generate_module_structure_tree(output_dir)
        generated_files.append(tree_file)
    except Exception as e:
        console.print(f"[red]Error generating structure tree: {e}[/red]")
    
    # 3. Generate import dependency graph
    try:
        imports_map = analyze_imports()
        import_graph_file = generate_import_graph(imports_map, output_dir)
        generated_files.append(import_graph_file)
    except Exception as e:
        console.print(f"[red]Error generating import graph: {e}[/red]")
    
    # 4. Generate pydeps graph (if available and not skipped)
    if not args.skip_pydeps:
        try:
            pydeps_file = generate_pydeps_graph(output_dir, args.format)
            if pydeps_file:
                generated_files.append(pydeps_file)
        except Exception as e:
            console.print(f"[yellow]Skipping pydeps: {e}[/yellow]")
    
    # 5. Generate graphviz from existing DOT file
    existing_dot = project_root / "data/outputs/dependency_graph.dot"
    if existing_dot.exists():
        try:
            graphviz_file = generate_graphviz_from_dot(existing_dot, output_dir, args.format)
            if graphviz_file:
                generated_files.append(graphviz_file)
        except Exception as e:
            console.print(f"[yellow]Skipping graphviz: {e}[/yellow]")
    
    # 6. Generate summary report
    try:
        summary_file = generate_summary_report(output_dir, generated_files)
        generated_files.append(summary_file)
    except Exception as e:
        console.print(f"[red]Error generating summary: {e}[/red]")
    
    console.print("\n[bold green]Visualization complete![/bold green]")
    console.print(f"\nGenerated {len([f for f in generated_files if f.exists()])} files:")
    for file in generated_files:
        if file.exists():
            console.print(f"  - {file.relative_to(project_root)}")
    
    console.print(f"\n[bold]Next steps:[/bold]")
    console.print("1. View workflow_diagram.mmd at https://mermaid.live/")
    console.print("2. Open PNG files in an image viewer")
    console.print("3. Read VISUALIZATION_SUMMARY.md for details")


if __name__ == "__main__":
    main()
