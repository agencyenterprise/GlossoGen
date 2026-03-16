#!/usr/bin/env python3
"""
Custom linting script to detect imports inside functions.

This script scans Python files for import statements inside function definitions,
which is against our coding standards.
"""

import argparse
import ast
import sys
from pathlib import Path
from typing import Union


class InlineImportChecker(ast.NodeVisitor):
    """AST visitor to find imports inside functions."""

    def __init__(self) -> None:
        self.errors: list[dict[str, Union[str, int]]] = []
        self.in_function = False
        self.function_depth = 0

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        """Visit function definitions."""
        old_in_function = self.in_function
        old_depth = self.function_depth

        self.in_function = True
        self.function_depth += 1

        self.generic_visit(node)

        self.in_function = old_in_function
        self.function_depth = old_depth

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        """Visit async function definitions."""
        old_in_function = self.in_function
        old_depth = self.function_depth

        self.in_function = True
        self.function_depth += 1

        self.generic_visit(node)

        self.in_function = old_in_function
        self.function_depth = old_depth

    def visit_Import(self, node: ast.Import) -> None:
        """Visit import statements."""
        if self.in_function:
            self.errors.append(
                {
                    "line": node.lineno,
                    "col": node.col_offset,
                    "type": "import",
                    "message": f"Import statement inside function at line {node.lineno}",
                }
            )
        self.generic_visit(node)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        """Visit from...import statements."""
        if self.in_function:
            module = node.module or ""
            self.errors.append(
                {
                    "line": node.lineno,
                    "col": node.col_offset,
                    "type": "from_import",
                    "message": (
                        f"From-import statement inside function at line {node.lineno}: "
                        f"'from {module} import ...'"
                    ),
                }
            )
        self.generic_visit(node)


def check_file(file_path: Path) -> list[dict[str, Union[str, int]]]:
    """Check a single Python file for inline imports."""
    try:
        content = file_path.read_text(encoding="utf-8")

        tree = ast.parse(content, filename=str(file_path))
        checker = InlineImportChecker()
        checker.visit(tree)

        # Filter out errors that have a '# no-inline-import' comment
        lines = content.splitlines()
        final_errors = []
        for error in checker.errors:
            # AST gives 1-based line numbers, so we convert to 0-based index
            line_index = int(str(error["line"])) - 1

            # Check if the line content has our ignore comment
            if line_index < len(lines):
                line_content = lines[line_index]
                if "# no-inline-import" in line_content:
                    continue  # Skip this error if the comment is present

            final_errors.append(error)

        return final_errors
    except SyntaxError as e:
        return [
            {
                "line": e.lineno or 0,
                "col": e.offset or 0,
                "type": "syntax_error",
                "message": f"Syntax error: {e.msg}",
            }
        ]
    except (OSError, UnicodeDecodeError) as e:
        return [{"line": 0, "col": 0, "type": "error", "message": f"Error parsing file: {e}"}]


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
    parser = argparse.ArgumentParser(description="Check Python files for inline imports")
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
        # Check specific files passed as arguments
        files_to_check = [Path(arg) for arg in args.files]
    else:
        # Check all Python files in the target directory and subdirectories
        target_path = Path(args.target_dir)
        files_to_check = list(target_path.rglob("*.py"))

    # Build list of patterns to exclude
    exclude_patterns = [".venv", "__pycache__", ".git", "node_modules"]
    exclude_patterns.extend(normalize_exclude_patterns(patterns=args.exclude))

    total_errors = 0

    for file_path in files_to_check:
        if file_path.name == __file__.split("/")[-1]:  # Skip this script itself
            continue

        # Skip excluded directories and patterns
        if is_excluded(file_path=file_path, patterns=exclude_patterns):
            continue

        errors = check_file(file_path)

        if errors:
            print(f"\n{file_path}:")
            for error in errors:
                print(f"  Line {error['line']}: {error['message']}")
                total_errors += 1

    if total_errors > 0:
        print(f"\n Found {total_errors} inline import error(s)")
        sys.exit(1)
    else:
        print("No inline imports found")
        sys.exit(0)


if __name__ == "__main__":
    main()
