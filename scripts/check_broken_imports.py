#!/usr/bin/env python3
"""
Check for broken imports and circular dependencies.

Analyzes all Python files in the project to find:
- Broken imports (modules that don't exist)
- Circular dependencies
- Missing modules
"""

import ast
import sys
from pathlib import Path
from collections import defaultdict, deque
from typing import Dict, Set, List, Tuple
import logging

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class ImportAnalyzer:
    """Analyzes imports in Python project."""
    
    def __init__(self, project_root: Path):
        self.project_root = project_root
        self.src_dir = project_root / "src"
        self.modules: Dict[str, Path] = {}
        self.imports: Dict[str, Set[str]] = defaultdict(set)
        self.broken_imports: List[Tuple[str, str, str]] = []  # (module, import_name, error)
        self.circular_deps: List[List[str]] = []
    
    def find_modules(self):
        """Find all Python modules in the project."""
        for py_file in self.src_dir.rglob("*.py"):
            rel_path = py_file.relative_to(self.src_dir)
            # Convert path to module name
            parts = list(rel_path.parts)
            if parts[-1] == "__init__.py":
                parts = parts[:-1]
            else:
                parts[-1] = parts[-1].replace(".py", "")
            
            module_name = ".".join(parts)
            self.modules[module_name] = py_file
        
        logger.info(f"Found {len(self.modules)} modules")
    
    def analyze_imports(self):
        """Analyze imports in all modules."""
        for module_name, file_path in self.modules.items():
            try:
                with open(file_path, "r", encoding="utf-8") as f:
                    tree = ast.parse(f.read(), filename=str(file_path))
                
                # Extract imports
                for node in ast.walk(tree):
                    if isinstance(node, ast.Import):
                        for alias in node.names:
                            self._check_import(module_name, alias.name, file_path)
                    elif isinstance(node, ast.ImportFrom):
                        if node.module:
                            self._check_import(module_name, node.module, file_path)
                            
            except Exception as e:
                logger.warning(f"Failed to parse {file_path}: {e}")
    
    def _check_import(self, module_name: str, import_name: str, file_path: Path):
        """Check if an import is valid."""
        # Skip standard library and third-party imports
        if import_name.startswith("_") or "." not in import_name:
            return
        
        # Check if it's a local import
        if import_name.startswith("src."):
            import_name = import_name[4:]  # Remove "src." prefix
        
        # Check if module exists
        parts = import_name.split(".")
        base_module = parts[0]
        
        if base_module in self.modules or any(m.startswith(base_module + ".") for m in self.modules.keys()):
            self.imports[module_name].add(import_name)
        else:
            # Check if it's a third-party import (common ones)
            third_party = [
                "pydantic", "pandas", "numpy", "matplotlib", "networkx", 
                "sklearn", "fuzzywuzzy", "pycountry", "pyvis", "exa_py",
                "tavily", "anthropic", "openai", "google", "perplexity"
            ]
            if base_module not in third_party:
                # Might be broken, but could also be a dynamic import
                # Only report if it looks like a local import
                if not any(base_module.startswith(tp) for tp in third_party):
                    self.broken_imports.append((module_name, import_name, "Module not found"))
    
    def find_circular_dependencies(self):
        """Find circular dependencies using DFS."""
        visited = set()
        rec_stack = set()
        cycles = []
        
        def dfs(node: str, path: List[str]):
            visited.add(node)
            rec_stack.add(node)
            path.append(node)
            
            for neighbor in self.imports.get(node, []):
                # Only check local imports
                if neighbor not in self.modules:
                    continue
                
                if neighbor not in visited:
                    dfs(neighbor, path.copy())
                elif neighbor in rec_stack:
                    # Found a cycle
                    cycle_start = path.index(neighbor)
                    cycle = path[cycle_start:] + [neighbor]
                    if cycle not in cycles:
                        cycles.append(cycle)
            
            rec_stack.remove(node)
            path.pop()
        
        for module in self.modules.keys():
            if module not in visited:
                dfs(module, [])
        
        self.circular_deps = cycles
        return cycles
    
    def generate_report(self) -> Dict:
        """Generate analysis report."""
        return {
            "total_modules": len(self.modules),
            "total_imports": sum(len(imps) for imps in self.imports.values()),
            "broken_imports": [
                {
                    "module": mod,
                    "import": imp,
                    "error": err
                }
                for mod, imp, err in self.broken_imports
            ],
            "circular_dependencies": self.circular_deps,
            "modules": list(self.modules.keys())
        }


def main():
    """Main function."""
    project_root = Path(__file__).parent.parent
    
    logger.info("Analyzing imports...")
    analyzer = ImportAnalyzer(project_root)
    analyzer.find_modules()
    analyzer.analyze_imports()
    analyzer.find_circular_dependencies()
    
    report = analyzer.generate_report()
    
    # Print results
    print("\n" + "=" * 60)
    print("IMPORT ANALYSIS REPORT")
    print("=" * 60)
    print(f"\nTotal modules: {report['total_modules']}")
    print(f"Total imports: {report['total_imports']}")
    
    if report['broken_imports']:
        print(f"\n⚠️  Found {len(report['broken_imports'])} potentially broken imports:")
        for item in report['broken_imports'][:10]:  # Show first 10
            print(f"  - {item['module']} imports {item['import']}: {item['error']}")
        if len(report['broken_imports']) > 10:
            print(f"  ... and {len(report['broken_imports']) - 10} more")
    else:
        print("\n✓ No broken imports found")
    
    if report['circular_dependencies']:
        print(f"\n⚠️  Found {len(report['circular_dependencies'])} circular dependencies:")
        for cycle in report['circular_dependencies']:
            print(f"  - {' -> '.join(cycle)}")
    else:
        print("\n✓ No circular dependencies found")
    
    print("\n" + "=" * 60)
    
    # Save report
    import json
    output_file = project_root / "docs" / "dependency_analysis" / "import_analysis.json"
    output_file.parent.mkdir(parents=True, exist_ok=True)
    with open(output_file, "w") as f:
        json.dump(report, f, indent=2)
    
    logger.info(f"Report saved to {output_file}")
    
    return len(report['broken_imports']) == 0 and len(report['circular_dependencies']) == 0


if __name__ == "__main__":
    success = main()
    sys.exit(0 if success else 1)
