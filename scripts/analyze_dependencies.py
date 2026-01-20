#!/usr/bin/env python3
"""
Dependency Analysis Script

Analyzes Python project dependencies and generates visualization diagrams.
Uses pydeps for dependency graph generation.
"""

import subprocess
import sys
from pathlib import Path
import json
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_pydeps_installed():
    """Check if pydeps is installed."""
    try:
        import pydeps
        return True
    except ImportError:
        return False


def install_pydeps():
    """Install pydeps if not available."""
    logger.info("Installing pydeps...")
    try:
        subprocess.check_call([sys.executable, "-m", "pip", "install", "pydeps", "graphviz"])
        logger.info("pydeps installed successfully")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"Failed to install pydeps: {e}")
        return False


def generate_dependency_graph(output_dir: Path, format: str = "png"):
    """
    Generate dependency graph for the project.
    
    Args:
        output_dir: Directory to save output files
        format: Output format (png, svg, dot)
    """
    project_root = Path(__file__).parent.parent
    src_dir = project_root / "src"
    output_file = output_dir / f"dependency_graph.{format}"
    
    logger.info(f"Generating dependency graph for {src_dir}...")
    
    try:
        # Generate dependency graph
        cmd = [
            sys.executable, "-m", "pydeps",
            str(src_dir),
            "--noshow",
            f"-T{format}",
            f"-o{output_file}",
            "--max-bacon=2",  # Limit depth to avoid clutter
            "--cluster",  # Cluster related modules
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(project_root))
        
        if result.returncode == 0:
            logger.info(f"Dependency graph saved to {output_file}")
            return str(output_file)
        else:
            logger.error(f"pydeps failed: {result.stderr}")
            return None
            
    except Exception as e:
        logger.error(f"Error generating dependency graph: {e}")
        return None


def analyze_imports(project_root: Path):
    """
    Analyze imports and create a simple dependency map.
    
    Args:
        project_root: Project root directory
    """
    import ast
    from collections import defaultdict
    
    src_dir = project_root / "src"
    dependencies = defaultdict(set)
    modules = {}
    
    # Find all Python files
    for py_file in src_dir.rglob("*.py"):
        if py_file.name == "__init__.py":
            continue
            
        rel_path = py_file.relative_to(src_dir)
        module_name = str(rel_path.with_suffix("")).replace("/", ".")
        
        try:
            with open(py_file, "r", encoding="utf-8") as f:
                tree = ast.parse(f.read(), filename=str(py_file))
                
            # Extract imports
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    for alias in node.names:
                        dep_name = alias.name.split(".")[0]
                        if dep_name.startswith("src.") or not dep_name.startswith("_"):
                            dependencies[module_name].add(dep_name)
                elif isinstance(node, ast.ImportFrom):
                    if node.module:
                        dep_name = node.module.split(".")[0]
                        if dep_name.startswith("src.") or not dep_name.startswith("_"):
                            dependencies[module_name].add(dep_name)
                            
            modules[module_name] = str(rel_path)
            
        except Exception as e:
            logger.warning(f"Failed to parse {py_file}: {e}")
    
    return dict(dependencies), modules


def generate_mermaid_diagram(dependencies: dict, modules: dict, output_file: Path):
    """
    Generate Mermaid diagram from dependency analysis.
    
    Args:
        dependencies: Dictionary mapping modules to their dependencies
        modules: Dictionary mapping module names to file paths
        output_file: Output file path
    """
    logger.info("Generating Mermaid diagram...")
    
    lines = ["graph TD"]
    
    # Create nodes
    for module in sorted(modules.keys()):
        node_id = module.replace(".", "_").replace("-", "_")
        display_name = module.split(".")[-1]
        lines.append(f'    {node_id}["{display_name}"]')
    
    # Create edges
    for module, deps in sorted(dependencies.items()):
        module_id = module.replace(".", "_").replace("-", "_")
        for dep in sorted(deps):
            if dep in modules:  # Only show internal dependencies
                dep_id = dep.replace(".", "_").replace("-", "_")
                lines.append(f"    {dep_id} --> {module_id}")
    
    diagram = "\n".join(lines)
    
    with open(output_file, "w") as f:
        f.write(diagram)
    
    logger.info(f"Mermaid diagram saved to {output_file}")
    return str(output_file)


def main():
    """Main function."""
    project_root = Path(__file__).parent.parent
    output_dir = project_root / "docs" / "dependency_analysis"
    output_dir.mkdir(parents=True, exist_ok=True)
    
    logger.info("Starting dependency analysis...")
    
    # Check if pydeps is installed
    if not check_pydeps_installed():
        logger.warning("pydeps not found. Attempting to install...")
        if not install_pydeps():
            logger.error("Could not install pydeps. Please install manually: pip install pydeps graphviz")
            return
    
    # Generate dependency graph with pydeps
    graph_file = generate_dependency_graph(output_dir, format="png")
    if graph_file:
        logger.info(f"✓ Dependency graph: {graph_file}")
    
    # Also generate SVG for better quality
    svg_file = generate_dependency_graph(output_dir, format="svg")
    if svg_file:
        logger.info(f"✓ Dependency graph (SVG): {svg_file}")
    
    # Generate simple import analysis
    logger.info("Analyzing imports...")
    dependencies, modules = analyze_imports(project_root)
    
    # Save dependency map as JSON
    json_file = output_dir / "dependency_map.json"
    with open(json_file, "w") as f:
        json.dump({
            "dependencies": {k: list(v) for k, v in dependencies.items()},
            "modules": modules
        }, f, indent=2)
    logger.info(f"✓ Dependency map: {json_file}")
    
    # Generate Mermaid diagram
    mermaid_file = output_dir / "dependency_diagram.mmd"
    generate_mermaid_diagram(dependencies, modules, mermaid_file)
    logger.info(f"✓ Mermaid diagram: {mermaid_file}")
    
    logger.info("Dependency analysis complete!")
    logger.info(f"Output files saved to: {output_dir}")


if __name__ == "__main__":
    main()
