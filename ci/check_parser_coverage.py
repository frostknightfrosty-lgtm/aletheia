#!/usr/bin/env python3
"""Fail-fast parser coverage pre-flight for the tagged adapter inventory.

Rules:
- Every adapter must have >=1 parser_test marker, OR
- descriptor.parser_test_exempt must be true with a non-empty reason.
- A marked test must call a method named ``parse`` in its function body.
- Unknown adapter names and duplicate file/function markers are errors.

This deliberately checks the test source as well as the runtime inventory so a
bookkeeping-only coverage declaration cannot satisfy the gate.
"""

from __future__ import annotations

import ast
import sys
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
TESTS = ROOT / "tests"
sys.path.insert(0, str(ROOT / "app"))

from aletheia.adapters.registry import phase7_adapters  # noqa: E402


@dataclass(frozen=True)
class ParserTestRef:
    adapter: str
    path: Path
    function: str


def _marker_name(decorator: ast.expr) -> str | None:
    if not isinstance(decorator, ast.Call):
        return None
    func = decorator.func
    if not isinstance(func, ast.Name) or func.id != "parser_test":
        return None
    if len(decorator.args) != 1 or not isinstance(decorator.args[0], ast.Constant):
        raise ValueError("parser_test decorator must have exactly one string literal argument")
    value = decorator.args[0].value
    if not isinstance(value, str) or not value.strip():
        raise ValueError("parser_test adapter name must be a non-empty string literal")
    return value


def _calls_parse(node: ast.AST) -> bool:
    return any(
        isinstance(child, ast.Call)
        and isinstance(child.func, ast.Attribute)
        and child.func.attr == "parse"
        for child in ast.walk(node)
    )


def collect_parser_tests() -> list[ParserTestRef]:
    refs: list[ParserTestRef] = []
    for path in sorted(TESTS.glob("test_*.py")):
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            for decorator in node.decorator_list:
                adapter = _marker_name(decorator)
                if adapter is None:
                    continue
                if not _calls_parse(node):
                    raise SystemExit(
                        f"PARSER PREFLIGHT FAIL: {path.relative_to(ROOT)}::{node.name} "
                        f"is marked parser_test({adapter!r}) but does not call .parse()"
                    )
                refs.append(ParserTestRef(adapter, path, node.name))
    return refs


def verify_parser_coverage() -> tuple[list[str], list[str]]:
    inventory = phase7_adapters()
    refs = collect_parser_tests()
    errors: list[str] = []
    seen: dict[str, list[ParserTestRef]] = {}
    for ref in refs:
        seen.setdefault(ref.adapter, []).append(ref)
        if ref.adapter not in inventory:
            errors.append(
                f"unknown parser-test adapter {ref.adapter!r} at "
                f"{ref.path.relative_to(ROOT)}::{ref.function}"
            )

    for name, adapter in sorted(inventory.items()):
        descriptor = adapter.descriptor
        matches = seen.get(name, [])
        exempt = bool(getattr(descriptor, "parser_test_exempt", False))
        reason = getattr(descriptor, "parser_test_exempt_reason", None)
        if matches:
            continue
        if exempt and isinstance(reason, str) and reason.strip():
            continue
        errors.append(
            f"missing parser coverage for {name!r}: add parser_test({name!r}) "
            "or set parser_test_exempt=true with parser_test_exempt_reason"
        )

    duplicate_errors = [
        f"duplicate parser coverage for {name!r}: "
        + ", ".join(f"{r.path.relative_to(ROOT)}::{r.function}" for r in entries)
        for name, entries in sorted(seen.items())
        if len(entries) > 1
    ]
    errors.extend(duplicate_errors)
    covered = sorted(seen)
    return covered, errors


def main() -> int:
    covered, errors = verify_parser_coverage()
    inventory_count = len(phase7_adapters())
    if errors:
        print("PARSER PREFLIGHT: FAIL")
        for error in errors:
            print(f"- {error}")
        print(f"Inventory adapters: {inventory_count}; marked parser tests: {len(covered)}")
        return 1
    print(f"PARSER PREFLIGHT: PASS — {inventory_count}/{inventory_count} adapters have parser coverage")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
