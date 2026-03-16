#!/usr/bin/env python3
"""
Custom linting script to detect TYPE_CHECKING and future annotations usage.

This script scans Python files for:
- `from __future__ import annotations`
- `from typing import TYPE_CHECKING` or `import typing` followed by `typing.TYPE_CHECKING`
- `if TYPE_CHECKING:` blocks
"""

import argparse
import ast
import sys
from pathlib import Path


class TypeCheckingVisitor(ast.NodeVisitor):
    """AST visitor to find TYPE_CHECKING and future annotations usage."""

    def __init__(self) -> None:
        self.errors: list[dict[str, str | int]] = []

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit from...import statements."""
        if node.module == "__future__":
            for alias in node.names:
                if alias.name == "annotations":
                    self.errors.append(
                        {
                            "line": node.lineno,
                            "col": node.col_offset,
                            "message": (
                                f"Line {node.lineno}: "
                                "'from __future__ import annotations' is forbidden"
                            ),
                        }
                    )

        if node.module == "typing":
            for alias in node.names:
                if alias.name == "TYPE_CHECKING":
                    self.errors.append(
                        {
                            "line": node.lineno,
                            "col": node.col_offset,
                            "message": (
                                f"Line {node.lineno}: "
                                "'from typing import TYPE_CHECKING' is forbidden"
                            ),
                        }
                    )

        self.generic_visit(node)

    def visit_If(self, node: ast.If) -> None:
        """Visit if statements to catch 'if TYPE_CHECKING:' blocks."""
        if isinstance(node.test, ast.Name) and node.test.id == "TYPE_CHECKING":
            self.errors.append(
                {
                    "line": node.lineno,
                    "col": node.col_offset,
                    "message": f"Line {node.lineno}: 'if TYPE_CHECKING:' block is forbidden",
                }
            )

        if (
            isinstance(node.test, ast.Attribute)
            and isinstance(node.test.value, ast.Name)
            and node.test.value.id == "typing"
            and node.test.attr == "TYPE_CHECKING"
        ):
            self.errors.append(
                {
                    "line": node.lineno,
                    "col": node.col_offset,
                    "message": (
                        f"Line {node.lineno}: " "'if typing.TYPE_CHECKING:' block is forbidden"
                    ),
                }
            )

        self.generic_visit(node)


def check_file(file_path: Path) -> list[dict[str, str | int]]:
    """Check a single Python file for TYPE_CHECKING and future annotations."""
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
        checker = TypeCheckingVisitor()
        checker.visit(tree)
        return checker.errors
    except SyntaxError as e:
        return [
            {
                "line": e.lineno or 0,
                "col": e.offset or 0,
                "message": f"Syntax error: {e.msg}",
            }
        ]
    except (OSError, UnicodeDecodeError) as e:
        return [{"line": 0, "col": 0, "message": f"Error parsing file: {e}"}]


def normalize_exclude_patterns(patterns: list[str]) -> list[str]:
    """Split comma-separated patterns and trim whitespace."""
    normalized: list[str] = []
    for pattern in patterns:
        for part in pattern.split(sep=","):
            trimmed = part.strip()
            if trimmed:
                normalized.append(trimmed)
    return normalized


def is_excluded(file_path: Path, patterns: list[str]) -> bool:
    """Return True when the file path matches any exclude pattern."""
    path_str = file_path.as_posix()
    for pattern in patterns:
        if pattern and pattern in path_str:
            return True
    return False


def main() -> None:
    """Main function to check all Python files."""
    parser = argparse.ArgumentParser(
        description="Check Python files for TYPE_CHECKING and future annotations"
    )
    parser.add_argument(
        "--target-dir",
        type=str,
        default=".",
        help="Target directory to check (default: current directory)",
    )
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Directory or file patterns to exclude (can be used multiple times)",
    )
    parser.add_argument("files", nargs="*", help="Specific files to check")

    args = parser.parse_args()

    if args.files:
        files_to_check = [Path(arg) for arg in args.files]
    else:
        target_path = Path(args.target_dir)
        files_to_check = list(target_path.rglob("*.py"))

    exclude_patterns = [".venv", "__pycache__", ".git", "node_modules"]
    exclude_patterns.extend(normalize_exclude_patterns(patterns=args.exclude))

    total_errors = 0

    for file_path in files_to_check:
        if is_excluded(file_path=file_path, patterns=exclude_patterns):
            continue

        errors = check_file(file_path=file_path)

        if errors:
            print(f"\n{file_path}:")
            for error in errors:
                print(f"  {error['message']}")
                total_errors += 1

    if total_errors > 0:
        print(f"\nFound {total_errors} TYPE_CHECKING / future annotations error(s)")
        sys.exit(1)
    else:
        print("No TYPE_CHECKING or future annotations usage found")
        sys.exit(0)


if __name__ == "__main__":
    main()
