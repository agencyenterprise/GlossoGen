#!/usr/bin/env python3
"""Custom linting script for the Jinja prompt templates.

Checks the Jinja templates a scenario renders its prompts from. Nothing else reads
them until a run does, and by then the run directory has been claimed and the agents
have connected.

``TemplateRenderer`` uses ``StrictUndefined``, so an undefined variable already
fails at render. What is left to check is everything that fails before a variable is
reached, plus the templates nothing renders at all:

- a template that does not parse, which today surfaces after the run directory
  has been claimed and the agents have connected
- an ``{% include %}`` naming a partial that is not in the root the renderer
  searches, which is the same failure one level down
- a template no code and no other template names, which is a prompt somebody
  edits believing it is live
- a name in the code that no template answers to, which costs a launch

Undeclared variables are deliberately not checked. Scenarios assemble their
template variables in helpers, so the set a template is rendered with is not
decidable from the call site, and a rule that guessed would report the templates
that are fine. ``StrictUndefined`` covers that case where it can be answered
exactly.

Template names resolve against the directory a renderer was pointed at rather
than against the file doing the including, because that is how
``FileSystemLoader`` resolves them: a template in ``prompts/probe/`` including
``_shared.jinja`` gets ``prompts/_shared.jinja``. Roots are derived from the tree
rather than listed here, so a new scenario needs no edit.
"""

import argparse
import ast
import re
import sys
from pathlib import Path
from typing import NamedTuple

from jinja2 import Environment, StrictUndefined, TemplateSyntaxError

TEMPLATE_SUFFIX = ".jinja"

# The scaffold's templates are written in another dialect: `new-scenario` renders
# them with `<<>>` delimiters precisely so the `{{ }}` they contain survives into
# the prompt files it writes. Parsing them as platform prompts would be parsing
# them as the wrong language.
ALTERNATE_DIALECT_ROOTS = ("scaffold_templates",)

# Directories read for the names that reference a template, which decides what
# counts as an orphan. `tests` is in here because the fake scenarios under it ship
# prompts of their own, and a template a test renders is reached by something.
REFERENCE_ROOTS = ("src", "scripts", "linter", "tests")

# Directories whose lookups have to resolve on disk. `tests` is deliberately not
# among them: a test that writes a template into `tmp_path` and renders it is
# looking up a name that legitimately does not ship. Shipped code doing the same
# thing is the mistake this rule is for.
LOOKUP_ROOTS = ("src", "scripts", "linter")

# Calls that look a template up by name. Used by the rule that a name in the code
# resolves, where a false positive would block CI: a literal ending in `.jinja` is
# not always a lookup, and the scaffold's destination paths are the counter-example
# living in this repository.
_LOOKUP_FUNCTIONS = frozenset(
    {"render", "get_template", "get_or_select_template", "select_template", "from_string", "parse"}
)
_LOOKUP_KEYWORDS = frozenset({"template_name", "name"})

_TEMPLATE_NAME = re.compile(r"""['"]([A-Za-z0-9_./-]+\.jinja)['"]""")
_INCLUDE = re.compile(
    r"""{%-?\s*(?:include|import|extends|from)\s*['"]([^'"]+)['"]""",
)

# A literal this long holding a newline is prose rather than a message. Tuned
# against the tree it runs on: the longest legitimate multi-line literal in a
# scenario is a tool description, and prompts start well above this.
PROSE_LITERAL_CHARS = 400


class Finding(NamedTuple):
    """One problem, and where to look for it."""

    path: Path
    line: int
    message: str


class TemplateRoot(NamedTuple):
    """A directory a renderer searches, and the templates found under it."""

    directory: Path
    templates: tuple[Path, ...]

    def names(self) -> set[str]:
        """Return every name a template under this root answers to."""
        return {path.relative_to(self.directory).as_posix() for path in self.templates}


def main() -> None:
    """Check every template under the target directory and report what is wrong."""
    parser = argparse.ArgumentParser(description="Lint the Jinja prompt templates")
    parser.add_argument("--target-dir", type=str, required=True, help="Directory to check")
    parser.add_argument(
        "--exclude",
        action="append",
        default=[],
        help="Directory name to skip; repeatable",
    )
    args = parser.parse_args()

    target = Path(args.target_dir).resolve()
    excluded = set(args.exclude)

    roots = find_template_roots(target=target, excluded=excluded)
    if not roots:
        print("No prompt templates found")
        sys.exit(0)

    referenced = collect_referenced_names(target=target, excluded=excluded)
    findings = [
        *check_templates_parse(roots=roots),
        *check_includes_resolve(roots=roots),
        *check_every_template_is_referenced(roots=roots, referenced=referenced),
        *check_every_reference_resolves(roots=roots, target=target, excluded=excluded),
    ]
    advisory = check_no_prose_in_python(target=target, excluded=excluded)

    report(findings=findings, advisory=advisory)
    if findings:
        sys.exit(1)
    sys.exit(0)


def report(findings: list[Finding], advisory: list[Finding]) -> None:
    """Print findings grouped by file, advisory ones after and separately."""
    for label, group in (("", findings), ("advisory: ", advisory)):
        by_path: dict[Path, list[Finding]] = {}
        for finding in group:
            by_path.setdefault(finding.path, []).append(finding)
        for path in sorted(by_path):
            print(f"\n{label}{path}:")
            for finding in sorted(by_path[path], key=lambda one: one.line):
                if finding.line:
                    print(f"  Line {finding.line}: {finding.message}")
                else:
                    print(f"  {finding.message}")

    if findings:
        print(f"\n Found {len(findings)} prompt template error(s)")
        return
    counted = f", {len(advisory)} advisory" if advisory else ""
    print(f"No prompt template errors found{counted}")


def is_excluded(path: Path, excluded: set[str]) -> bool:
    """Whether any part of a path names an excluded directory."""
    return bool(excluded & set(path.parts))


def find_template_roots(target: Path, excluded: set[str]) -> list[TemplateRoot]:
    """Group every template under ``target`` by the directory a renderer searches.

    The root is the highest ancestor still holding templates of its own, which is
    what a renderer is pointed at: ``prompts`` rather than ``prompts/probe``, and
    ``scaffold_templates`` rather than the ``prompts`` inside it.
    """
    templates = [
        path
        for path in sorted(target.rglob(f"*{TEMPLATE_SUFFIX}"))
        if not is_excluded(path=path, excluded=excluded)
    ]
    grouped: dict[Path, list[Path]] = {}
    for path in templates:
        grouped.setdefault(root_of(template=path), []).append(path)
    return [
        TemplateRoot(directory=directory, templates=tuple(found))
        for directory, found in sorted(grouped.items())
    ]


def root_of(template: Path) -> Path:
    """Return the directory a renderer would be pointed at for this template."""
    root = template.parent
    while holds_templates_directly(directory=root.parent):
        root = root.parent
    return root


def holds_templates_directly(directory: Path) -> bool:
    """Whether a directory has templates of its own, ignoring subdirectories."""
    if not directory.is_dir():
        return False
    return any(child.suffix == TEMPLATE_SUFFIX for child in directory.iterdir())


def environment_for(root: TemplateRoot) -> Environment:
    """Return an environment matching how this root's templates are rendered.

    Filters are not registered. Jinja resolves them when a template runs rather
    than when it parses, so a template using one still parses here.
    """
    if root.directory.name in ALTERNATE_DIALECT_ROOTS:
        return Environment(
            variable_start_string="<<",
            variable_end_string=">>",
            block_start_string="<%",
            block_end_string="%>",
            undefined=StrictUndefined,
            autoescape=False,
        )
    return Environment(undefined=StrictUndefined, autoescape=False)


def check_templates_parse(roots: list[TemplateRoot]) -> list[Finding]:
    """Every template parses under the environment that renders it."""
    findings: list[Finding] = []
    for root in roots:
        environment = environment_for(root=root)
        for path in root.templates:
            try:
                environment.parse(path.read_text(encoding="utf-8"))
            except TemplateSyntaxError as error:
                findings.append(
                    Finding(
                        path=path,
                        line=error.lineno or 0,
                        message=f"does not parse: {error.message}",
                    )
                )
    return findings


def check_includes_resolve(roots: list[TemplateRoot]) -> list[Finding]:
    """Every included name is a template in the same root."""
    findings: list[Finding] = []
    for root in roots:
        available = root.names()
        for path in root.templates:
            for line_number, name in included_names(path=path):
                if name in available:
                    continue
                findings.append(
                    Finding(
                        path=path,
                        line=line_number,
                        message=(
                            f"includes {name!r}, which is not in {root.directory.name}/. "
                            "Names resolve against the directory the renderer searches, "
                            "not the including template's own directory"
                        ),
                    )
                )
    return findings


def included_names(path: Path) -> list[tuple[int, str]]:
    """Return every name this template includes, with the line it appears on."""
    found: list[tuple[int, str]] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        found.extend((line_number, name) for name in _INCLUDE.findall(line))
    return found


def python_files_under(target: Path, roots: tuple[str, ...], excluded: set[str]) -> list[Path]:
    """Return every Python file under the named directories of ``target``."""
    found: list[Path] = []
    for directory in roots:
        source = target / directory
        if not source.is_dir():
            continue
        found.extend(
            path
            for path in sorted(source.rglob("*.py"))
            if not is_excluded(path=path, excluded=excluded)
        )
    return found


def collect_referenced_names(target: Path, excluded: set[str]) -> set[str]:
    """Return every template name the code mentions, by any means.

    Every literal rather than only the lookups, because this feeds the orphan rule
    and a name missed there marks a live template as dead. A name matched here that
    is not really a lookup costs nothing: it can only fail to mark something.
    """
    referenced: set[str] = set()
    for path in python_files_under(target=target, roots=REFERENCE_ROOTS, excluded=excluded):
        referenced |= set(_TEMPLATE_NAME.findall(path.read_text(encoding="utf-8")))
    return referenced


def check_every_template_is_referenced(
    roots: list[TemplateRoot], referenced: set[str]
) -> list[Finding]:
    """Every template is named by the code, or included by another template."""
    included: set[str] = set()
    for root in roots:
        for path in root.templates:
            included |= {name for _, name in included_names(path=path)}

    findings: list[Finding] = []
    for root in roots:
        for path in root.templates:
            name = path.relative_to(root.directory).as_posix()
            if name in included or name in referenced or path.name in referenced:
                continue
            findings.append(
                Finding(
                    path=path,
                    line=0,
                    message=(
                        "nothing renders or includes this template. A prompt no run "
                        "reaches is one somebody edits believing it is live"
                    ),
                )
            )
    return findings


def check_every_reference_resolves(
    roots: list[TemplateRoot], target: Path, excluded: set[str]
) -> list[Finding]:
    """Every name looked up as a template answers to one.

    Reads lookups rather than every literal ending in ``.jinja``. The two differ,
    and this repository holds the reason: the scaffold's ``_destinations`` maps a
    template name to the *file it writes*, and that destination is a literal
    ending in ``.jinja`` which is not supposed to resolve to anything.

    Checked against every root rather than the one belonging to the naming module,
    because a basename is shared deliberately: ten scenarios ship a
    ``description.jinja``, and which renderer sees which is decided by the
    ``prompts_dirs`` it was built with rather than by the literal.
    """
    available: set[str] = set()
    for root in roots:
        names = root.names()
        available |= names
        available |= {Path(name).name for name in names}

    findings: list[Finding] = []
    for path in python_files_under(target=target, roots=LOOKUP_ROOTS, excluded=excluded):
        for line_number, name in looked_up_names(path=path):
            if name in available:
                continue
            findings.append(
                Finding(
                    path=path,
                    line=line_number,
                    message=f"looks up template {name!r}, which does not exist",
                )
            )
    return findings


def looked_up_names(path: Path) -> list[tuple[int, str]]:
    """Return every template name this file looks up, with its line."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        # Reported by the Python linters; nothing to add here.
        return []

    found: list[tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue
        for name, line in _lookup_arguments(call=node):
            if name.endswith(TEMPLATE_SUFFIX):
                found.append((line, name))
    return found


def _lookup_arguments(call: ast.Call) -> list[tuple[str, int]]:
    """Return the string arguments of ``call`` that name a template."""
    called = call.func
    is_lookup = isinstance(called, ast.Attribute) and called.attr in _LOOKUP_FUNCTIONS
    is_lookup = is_lookup or (isinstance(called, ast.Name) and called.id in _LOOKUP_FUNCTIONS)

    found: list[tuple[str, int]] = []
    if is_lookup:
        found.extend(
            (argument.value, argument.lineno)
            for argument in call.args
            if isinstance(argument, ast.Constant) and isinstance(argument.value, str)
        )
    for keyword in call.keywords:
        if keyword.arg not in _LOOKUP_KEYWORDS:
            continue
        if isinstance(keyword.value, ast.Constant) and isinstance(keyword.value.value, str):
            found.append((keyword.value.value, keyword.value.lineno))
    return found


def check_no_prose_in_python(target: Path, excluded: set[str]) -> list[Finding]:
    """Prompt-sized string literals in scenario code, reported and not enforced.

    Prompts belong in ``prompts/*.jinja`` so they can be read, diffed and rendered
    strictly. This finds the ones that drifted back into Python, and is advisory
    because the line between a long tool description and a prompt is a judgement
    the linter should not make on anybody's behalf.
    """
    scenarios = target / "src" / "glossogen" / "scenarios"
    if not scenarios.is_dir():
        return []

    findings: list[Finding] = []
    for path in sorted(scenarios.rglob("*.py")):
        if is_excluded(path=path, excluded=excluded):
            continue
        findings.extend(prose_literals(path=path))
    return findings


def prose_literals(path: Path) -> list[Finding]:
    """Return the multi-line, prompt-sized literals in one file, docstrings aside."""
    try:
        tree = ast.parse(path.read_text(encoding="utf-8"))
    except SyntaxError:
        # Reported by the Python linters; nothing to add here.
        return []

    docstrings = {
        id(node.body[0].value)
        for node in ast.walk(tree)
        if isinstance(node, (ast.Module, ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
        and node.body
        and isinstance(node.body[0], ast.Expr)
        and isinstance(node.body[0].value, ast.Constant)
        and isinstance(node.body[0].value.value, str)
    }

    findings: list[Finding] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.Constant) or not isinstance(node.value, str):
            continue
        if id(node) in docstrings:
            continue
        if len(node.value) < PROSE_LITERAL_CHARS or "\n" not in node.value:
            continue
        findings.append(
            Finding(
                path=path,
                line=node.lineno,
                message=(
                    f"{len(node.value)}-character multi-line literal. Prompts belong in "
                    "prompts/*.jinja, where they render strictly and can be diffed"
                ),
            )
        )
    return findings


if __name__ == "__main__":
    main()
