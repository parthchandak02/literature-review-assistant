#!/usr/bin/env python3
"""Check endpoint parity between spec.md and src/web/app.py.

This script enforces a bidirectional contract lock:
- Every documented endpoint in spec section 10.1 must exist in FastAPI code.
- Every FastAPI endpoint in code must be documented in spec section 10.1.
"""

from __future__ import annotations

import argparse
import ast
import re
from dataclasses import dataclass
from pathlib import Path

from rich.console import Console

console = Console()

ALLOWED_DECORATORS = {"get", "post", "put", "patch", "delete", "options", "head", "api_route"}
HEADING_PATTERN = re.compile(r"^###\s+10\.1\s+REST Endpoints\s*$")
ANY_H3_PATTERN = re.compile(r"^###\s+")
TABLE_HEADER_PATTERN = re.compile(r"^\|\s*Method\s*\|\s*Path\s*\|\s*Description\s*\|\s*$")
SEPARATOR_PATTERN = re.compile(r"^\|\s*-+\s*\|\s*-+\s*\|\s*-+\s*\|\s*$")
PATH_CONVERTER_PATTERN = re.compile(r"\{([A-Za-z0-9_]+):[^{}]+\}")
CATCH_ALL_PATH_PATTERN = re.compile(r"\{[^{}:]+:path\}")
MULTI_SLASH_PATTERN = re.compile(r"/{2,}")


@dataclass(frozen=True, order=True)
class Endpoint:
    method: str
    path: str


@dataclass(frozen=True)
class EndpointDiff:
    missing_in_docs: set[Endpoint]
    stale_in_docs: set[Endpoint]

    @property
    def ok(self) -> bool:
        return not self.missing_in_docs and not self.stale_in_docs


def normalize_endpoint(method: str, path: str) -> Endpoint:
    normalized_method = method.strip().upper()
    normalized_path = path.strip()
    if not normalized_path.startswith("/"):
        normalized_path = f"/{normalized_path}"
    normalized_path = PATH_CONVERTER_PATTERN.sub(r"{\1}", normalized_path)
    normalized_path = MULTI_SLASH_PATTERN.sub("/", normalized_path)
    if len(normalized_path) > 1 and normalized_path.endswith("/"):
        normalized_path = normalized_path.rstrip("/")
    return Endpoint(method=normalized_method, path=normalized_path)


def _find_10_1_section_bounds(lines: list[str]) -> tuple[int, int]:
    matches = [idx for idx, line in enumerate(lines) if HEADING_PATTERN.match(line.strip())]
    if len(matches) != 1:
        raise ValueError(
            f"spec.md: expected exactly one heading '### 10.1 REST Endpoints', found {len(matches)}"
        )
    start = matches[0] + 1
    end = len(lines)
    for idx in range(start, len(lines)):
        if ANY_H3_PATTERN.match(lines[idx].strip()):
            end = idx
            break
    return start, end


def parse_spec_endpoints(spec_text: str) -> set[Endpoint]:
    lines = spec_text.splitlines()
    section_start, section_end = _find_10_1_section_bounds(lines)
    section_lines = lines[section_start:section_end]

    table_start = -1
    for idx in range(len(section_lines)):
        if TABLE_HEADER_PATTERN.match(section_lines[idx].strip()):
            table_start = idx
            break
    if table_start < 0:
        raise ValueError("spec.md: section 10.1 found, but endpoint table header was not found")
    if table_start + 1 >= len(section_lines) or not SEPARATOR_PATTERN.match(section_lines[table_start + 1].strip()):
        raise ValueError("spec.md: section 10.1 endpoint table separator row is missing or malformed")

    endpoints: set[Endpoint] = set()
    row_number = 0
    for idx in range(table_start + 2, len(section_lines)):
        raw = section_lines[idx].strip()
        if not raw:
            break
        if not raw.startswith("|"):
            break
        row_number += 1
        parts = raw.strip("|").split("|", 2)
        if len(parts) != 3:
            raise ValueError(f"spec.md: malformed endpoint row #{row_number}: {raw}")
        method = parts[0].strip()
        path = parts[1].strip()
        if not method or not path:
            raise ValueError(f"spec.md: endpoint row missing method/path at row #{row_number}: {raw}")
        endpoint = normalize_endpoint(method, path)
        if endpoint in endpoints:
            raise ValueError(f"spec.md: duplicate endpoint in section 10.1: {endpoint.method} {endpoint.path}")
        endpoints.add(endpoint)
    if not endpoints:
        raise ValueError("spec.md: section 10.1 endpoint table contains no endpoint rows")
    return endpoints


def _is_false_constant(node: ast.expr) -> bool:
    return isinstance(node, ast.Constant) and node.value is False


def _decorator_name(decorator: ast.Call) -> str | None:
    if not isinstance(decorator.func, ast.Attribute):
        return None
    if not isinstance(decorator.func.value, ast.Name):
        return None
    if decorator.func.value.id != "app":
        return None
    if decorator.func.attr not in ALLOWED_DECORATORS:
        return None
    return decorator.func.attr


def _extract_literal_path(decorator: ast.Call) -> str | None:
    if not decorator.args:
        return None
    first = decorator.args[0]
    if isinstance(first, ast.Constant) and isinstance(first.value, str):
        return first.value
    return None


def _extract_api_route_methods(decorator: ast.Call) -> list[str]:
    for keyword in decorator.keywords:
        if keyword.arg != "methods":
            continue
        if not isinstance(keyword.value, (ast.List, ast.Tuple)):
            return []
        methods: list[str] = []
        for element in keyword.value.elts:
            if isinstance(element, ast.Constant) and isinstance(element.value, str):
                methods.append(element.value)
        return methods
    return []


def _include_in_schema_is_false(decorator: ast.Call) -> bool:
    for keyword in decorator.keywords:
        if keyword.arg == "include_in_schema" and _is_false_constant(keyword.value):
            return True
    return False


def extract_fastapi_endpoints(app_source: str) -> set[Endpoint]:
    tree = ast.parse(app_source)
    endpoints: set[Endpoint] = set()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.AsyncFunctionDef, ast.FunctionDef)):
            continue
        for dec in node.decorator_list:
            if not isinstance(dec, ast.Call):
                continue
            dec_name = _decorator_name(dec)
            if dec_name is None:
                continue
            if _include_in_schema_is_false(dec):
                continue
            path = _extract_literal_path(dec)
            if path is None:
                continue
            if not path.startswith("/api"):
                continue
            if CATCH_ALL_PATH_PATTERN.search(path):
                continue
            if dec_name == "api_route":
                methods = _extract_api_route_methods(dec)
            else:
                methods = [dec_name]
            for method in methods:
                endpoints.add(normalize_endpoint(method, path))
    return endpoints


def compare_endpoint_sets(spec_endpoints: set[Endpoint], app_endpoints: set[Endpoint]) -> EndpointDiff:
    return EndpointDiff(
        missing_in_docs=app_endpoints - spec_endpoints,
        stale_in_docs=spec_endpoints - app_endpoints,
    )


def _render_endpoint_set(title: str, values: set[Endpoint]) -> None:
    console.print(title)
    for endpoint in sorted(values):
        console.print(f"  - {endpoint.method} {endpoint.path}")


def run_parity_check(spec_path: Path, app_path: Path) -> int:
    try:
        spec_text = spec_path.read_text(encoding="utf-8")
        app_source = app_path.read_text(encoding="utf-8")
        spec_endpoints = parse_spec_endpoints(spec_text)
        app_endpoints = extract_fastapi_endpoints(app_source)
        diff = compare_endpoint_sets(spec_endpoints, app_endpoints)
    except ValueError as exc:
        console.print(f"ERROR: {exc}")
        return 2
    except OSError as exc:
        console.print(f"ERROR: failed reading input files: {exc}")
        return 2

    if not diff.ok:
        console.print("Endpoint parity check failed.")
        if diff.missing_in_docs:
            _render_endpoint_set("Undocumented endpoints present in code:", diff.missing_in_docs)
        if diff.stale_in_docs:
            _render_endpoint_set("Documented endpoints not found in code:", diff.stale_in_docs)
        return 1

    console.print(
        f"Endpoint parity check passed: {len(spec_endpoints)} documented endpoint(s) match FastAPI decorators."
    )
    return 0


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Check endpoint parity between spec.md section 10.1 and src/web/app.py decorators."
    )
    parser.add_argument("--spec-path", default="spec.md", help="Path to spec markdown file")
    parser.add_argument("--app-path", default="src/web/app.py", help="Path to FastAPI app source file")
    return parser.parse_args()


def main() -> None:
    args = parse_args()
    exit_code = run_parity_check(Path(args.spec_path), Path(args.app_path))
    raise SystemExit(exit_code)


if __name__ == "__main__":
    main()
