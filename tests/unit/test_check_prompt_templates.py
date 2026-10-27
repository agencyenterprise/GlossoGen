"""What the prompt-template linter reports, and what it deliberately does not.

A linter that passes because it looked at nothing is worse than no linter, and
this one has enough structure to fail that way silently: it derives the directory
a renderer searches, keeps two template dialects apart, and reads two different
sets of source files for its two reference rules. Each of those is checked here on
a tree built for the purpose.
"""

from pathlib import Path

from linter.check_prompt_templates import (
    check_environments_are_strict,
    check_every_reference_resolves,
    check_every_template_is_referenced,
    check_includes_resolve,
    check_no_prose_in_python,
    check_rendered_variables_match,
    check_templates_parse,
    collect_referenced_names,
    find_template_roots,
    root_of,
)


def write(path: Path, body: str) -> Path:
    """Write a file and every directory above it."""
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(body, encoding="utf-8")
    return path


def tree(root: Path) -> Path:
    """Build a minimal repository: one scenario, one prompt, one reference.

    The reference passes the variable the prompt reads, so a tree built for
    another rule's test carries no finding of its own.
    """
    prompts = root / "src" / "glossogen" / "scenarios" / "reactor_purge" / "prompts"
    write(prompts / "system.jinja", "You are {{ role }}.\n")
    write(prompts / "_shared.jinja", "shared\n")
    write(
        root / "src" / "glossogen" / "scenarios" / "reactor_purge" / "scenario.py",
        'renderer.render(template_name="system.jinja", template_variables={"role": r})\n',
    )
    return root


def roots_of(root: Path) -> list[Path]:
    """Return the template roots found under a tree."""
    return [found.directory for found in find_template_roots(target=root, excluded=set())]


def test_the_root_is_the_directory_the_renderer_searches(tmp_path: Path) -> None:
    """A template in a subdirectory still resolves names against the root above it.

    `prompts/probe/x.jinja` is loaded by a renderer pointed at `prompts`, so its
    includes are looked for there. Getting this wrong would make every partial in
    a scenario with a `probe/` directory look unresolvable.
    """
    prompts = tmp_path / "prompts"
    write(prompts / "top.jinja", "top\n")
    nested = write(prompts / "probe" / "deep.jinja", "deep\n")

    assert root_of(template=nested) == prompts


def test_a_root_with_no_templates_above_it_is_its_own_root(tmp_path: Path) -> None:
    """The walk up stops at the first directory holding no templates of its own."""
    prompts = tmp_path / "pkg" / "prompts"
    template = write(prompts / "only.jinja", "only\n")

    assert root_of(template=template) == prompts


def test_a_clean_tree_reports_nothing(tmp_path: Path) -> None:
    """The baseline every other test here breaks one thing against."""
    root = tree(tmp_path)
    found = find_template_roots(target=root, excluded=set())
    referenced = collect_referenced_names(target=root, excluded=set())

    assert not check_templates_parse(roots=found)
    assert not check_includes_resolve(roots=found)
    assert not check_every_reference_resolves(roots=found, target=root, excluded=set())
    # `_shared.jinja` is unreferenced in this tree, so only `system.jinja` is
    # expected to be clean; the orphan rule has its own test below.
    orphans = check_every_template_is_referenced(roots=found, referenced=referenced)
    assert [one.path.name for one in orphans] == ["_shared.jinja"]


def test_a_template_that_does_not_parse_is_reported(tmp_path: Path) -> None:
    """Otherwise this surfaces once the run directory is claimed."""
    root = tree(tmp_path)
    write(
        root / "src" / "glossogen" / "scenarios" / "reactor_purge" / "prompts" / "system.jinja",
        "{% if unclosed %}\n",
    )

    findings = check_templates_parse(roots=find_template_roots(target=root, excluded=set()))

    assert [one.path.name for one in findings] == ["system.jinja"]
    assert "does not parse" in findings[0].message


def test_an_include_outside_the_root_is_reported(tmp_path: Path) -> None:
    """Names resolve against the root, so a partial elsewhere does not count."""
    root = tree(tmp_path)
    write(
        root / "src" / "glossogen" / "scenarios" / "reactor_purge" / "prompts" / "system.jinja",
        '{% include "_missing.jinja" %}\n',
    )

    findings = check_includes_resolve(roots=find_template_roots(target=root, excluded=set()))

    assert len(findings) == 1
    assert "_missing.jinja" in findings[0].message


def test_an_include_from_a_subdirectory_resolves_against_the_root(tmp_path: Path) -> None:
    """The case the root derivation exists for, stated as a passing test."""
    root = tree(tmp_path)
    write(
        root
        / "src"
        / "glossogen"
        / "scenarios"
        / "reactor_purge"
        / "prompts"
        / "probe"
        / "p.jinja",
        '{% include "_shared.jinja" %}\n',
    )

    findings = check_includes_resolve(roots=find_template_roots(target=root, excluded=set()))

    assert not findings


def test_a_template_nothing_reaches_is_reported(tmp_path: Path) -> None:
    """A prompt no run renders is one somebody edits believing it is live."""
    root = tree(tmp_path)
    write(
        root / "src" / "glossogen" / "scenarios" / "reactor_purge" / "prompts" / "stray.jinja",
        "stray\n",
    )
    found = find_template_roots(target=root, excluded=set())

    findings = check_every_template_is_referenced(
        roots=found, referenced=collect_referenced_names(target=root, excluded=set())
    )

    assert "stray.jinja" in {one.path.name for one in findings}


def test_an_included_partial_is_not_an_orphan(tmp_path: Path) -> None:
    """Being included counts as being reached, so partials need no literal."""
    root = tree(tmp_path)
    write(
        root / "src" / "glossogen" / "scenarios" / "reactor_purge" / "prompts" / "system.jinja",
        '{% include "_shared.jinja" %}\n',
    )
    found = find_template_roots(target=root, excluded=set())

    findings = check_every_template_is_referenced(
        roots=found, referenced=collect_referenced_names(target=root, excluded=set())
    )

    assert not findings


def test_a_lookup_that_resolves_to_nothing_is_reported(tmp_path: Path) -> None:
    """The typo that costs a launch."""
    root = tree(tmp_path)
    write(
        root / "src" / "glossogen" / "scenarios" / "reactor_purge" / "scenario.py",
        'renderer.render(template_name="sytsem.jinja", template_variables={})\n',
    )

    findings = check_every_reference_resolves(
        roots=find_template_roots(target=root, excluded=set()), target=root, excluded=set()
    )

    assert len(findings) == 1
    assert "sytsem.jinja" in findings[0].message


def test_a_literal_that_is_not_a_lookup_is_not_reported(tmp_path: Path) -> None:
    """The scaffold's destination paths are literals that must not resolve.

    `_destinations` maps a template to the file it writes, and that filename ends
    in `.jinja` while naming nothing that exists. Reading lookups rather than every
    literal is what keeps this from failing the build.
    """
    root = tree(tmp_path)
    write(
        root / "src" / "glossogen" / "scenario_authoring" / "scenario_scaffold.py",
        'DESTINATIONS = {"scenario.py.jinja": "prompts/briefer_system.jinja"}\n',
    )

    findings = check_every_reference_resolves(
        roots=find_template_roots(target=root, excluded=set()), target=root, excluded=set()
    )

    assert not findings


def test_a_lookup_in_a_test_is_not_required_to_resolve(tmp_path: Path) -> None:
    """A test writing a template into tmp_path renders a name that never ships."""
    root = tree(tmp_path)
    write(
        root / "tests" / "unit" / "test_renderer.py",
        'renderer.render(template_name="written_at_runtime.jinja", template_variables={})\n',
    )

    findings = check_every_reference_resolves(
        roots=find_template_roots(target=root, excluded=set()), target=root, excluded=set()
    )

    assert not findings


def test_a_reference_from_a_test_still_saves_a_template_from_being_an_orphan(
    tmp_path: Path,
) -> None:
    """The fake scenarios under tests/ ship prompts, and a test renders them."""
    root = tree(tmp_path)
    write(
        root / "tests" / "fakes" / "external_scenario" / "uses.py",
        'renderer.render(template_name="_shared.jinja", template_variables={})\n',
    )
    found = find_template_roots(target=root, excluded=set())

    findings = check_every_template_is_referenced(
        roots=found, referenced=collect_referenced_names(target=root, excluded=set())
    )

    assert "_shared.jinja" not in {one.path.name for one in findings}


def test_the_scaffold_dialect_is_parsed_as_itself(tmp_path: Path) -> None:
    """`<<>>` templates hold `{{ }}` on purpose, and are not platform prompts.

    Parsing them with default delimiters would read the placeholders they are
    meant to emit as placeholders of their own.
    """
    scaffold = tmp_path / "src" / "glossogen" / "scenario_authoring" / "scaffold_templates"
    write(scaffold / "scenario.py.jinja", "<% if class_prefix %><<class_prefix>><% endif %>\n")
    write(scaffold / "prompts" / "system.jinja.jinja", "{% raw_looking %}{{ not_closed \n")

    findings = check_templates_parse(roots=find_template_roots(target=tmp_path, excluded=set()))

    assert not findings
    assert roots_of(tmp_path) == [scaffold]


def test_prompt_sized_literals_in_scenario_python_are_advisory(tmp_path: Path) -> None:
    """Reported, and left to a person to judge."""
    root = tree(tmp_path)
    body = "line of prompt text\n" * 40
    write(
        root / "src" / "glossogen" / "scenarios" / "reactor_purge" / "world.py",
        f'PROMPT = """{body}"""\n',
    )

    findings = check_no_prose_in_python(target=root, excluded=set())

    assert [one.path.name for one in findings] == ["world.py"]


def test_a_module_docstring_is_not_reported_as_a_prompt(tmp_path: Path) -> None:
    """Every module here opens with one, and they are long."""
    root = tree(tmp_path)
    body = "Explaining this module at length.\n" * 40
    write(
        root / "src" / "glossogen" / "scenarios" / "reactor_purge" / "world.py",
        f'"""{body}"""\n',
    )

    assert not check_no_prose_in_python(target=root, excluded=set())


def test_excluded_directories_are_not_read(tmp_path: Path) -> None:
    """`modal` ships a vLLM chat template that glossogen never renders.

    Excluding it is what keeps that from being reported as an orphan prompt, so
    both halves are asserted: found when it is not excluded, gone when it is.
    """
    root = tree(tmp_path)
    write(root / "modal" / "tool_chat_template.jinja", "{{ tools }}\n")

    included = [one.directory for one in find_template_roots(target=root, excluded=set())]
    excluded = [one.directory for one in find_template_roots(target=root, excluded={"modal"})]

    assert root / "modal" in included
    assert root / "modal" not in excluded


def test_a_permissive_environment_is_reported_and_a_strict_one_is_not(tmp_path: Path) -> None:
    """The default undefined is what let an empty turn number ship in every PDF.

    Both halves are asserted, because a rule that reported nothing would pass the
    tree it is meant to guard just as quietly.
    """
    root = tree(tmp_path)
    permissive = write(
        root / "src" / "glossogen" / "server" / "loose_renderer.py",
        "from jinja2 import Environment\n\nenv = Environment(autoescape=True)\n",
    )
    write(
        root / "src" / "glossogen" / "server" / "strict_renderer.py",
        "from jinja2 import Environment, StrictUndefined\n\n"
        "env = Environment(undefined=StrictUndefined)\n",
    )

    findings = check_environments_are_strict(target=root, excluded=set())

    assert [one.path for one in findings] == [permissive]
    assert "StrictUndefined" in findings[0].message


def test_a_module_qualified_environment_is_reported(tmp_path: Path) -> None:
    """`jinja2.Environment(...)` is the same call written another way."""
    root = tree(tmp_path)
    write(
        root / "src" / "glossogen" / "server" / "qualified_renderer.py",
        "import jinja2\n\nenv = jinja2.Environment(autoescape=True)\n",
    )

    assert len(check_environments_are_strict(target=root, excluded=set())) == 1


def variable_findings(root: Path) -> list[str]:
    """Run the variable rule over a tree and return its messages."""
    roots = find_template_roots(target=root, excluded=set())
    check = check_rendered_variables_match(roots=roots, target=root, excluded=set())
    return [one.message for one in check.findings]


def test_a_variable_the_template_reads_and_the_call_omits_is_reported(tmp_path: Path) -> None:
    """This is what `StrictUndefined` would raise on, found without running it."""
    root = tree(tmp_path)
    scenario = root / "src" / "glossogen" / "scenarios" / "reactor_purge"
    write(scenario / "prompts" / "brief.jinja", "{{ role }} has {{ budget }} left.\n")
    write(
        scenario / "render.py",
        'renderer.render(template_name="brief.jinja", template_variables={"role": r})\n',
    )

    messages = variable_findings(root)

    assert len(messages) == 1
    assert "without ['budget']" in messages[0]


def test_a_variable_the_call_passes_and_the_template_ignores_is_reported(tmp_path: Path) -> None:
    root = tree(tmp_path)
    scenario = root / "src" / "glossogen" / "scenarios" / "reactor_purge"
    write(scenario / "prompts" / "brief.jinja", "{{ role }} reporting.\n")
    write(
        scenario / "render.py",
        'renderer.render(template_name="brief.jinja", '
        'template_variables={"role": r, "budget": b})\n',
    )

    messages = variable_findings(root)

    assert len(messages) == 1
    assert "passes ['budget']" in messages[0]


def test_a_variable_only_an_included_partial_reads_is_not_reported(tmp_path: Path) -> None:
    """Includes are followed, or every scenario using a partial would be reported."""
    root = tree(tmp_path)
    scenario = root / "src" / "glossogen" / "scenarios" / "reactor_purge"
    write(scenario / "prompts" / "_budget.jinja", "{{ budget }} left.\n")
    write(scenario / "prompts" / "brief.jinja", "{{ role }}. {% include '_budget.jinja' %}\n")
    write(
        scenario / "render.py",
        'renderer.render(template_name="brief.jinja", '
        'template_variables={"role": r, "budget": b})\n',
    )

    assert variable_findings(root) == []


def test_a_name_held_in_a_module_constant_is_resolved(tmp_path: Path) -> None:
    """Scenarios name their templates in constants, so a rule missing those sees little."""
    root = tree(tmp_path)
    scenario = root / "src" / "glossogen" / "scenarios" / "reactor_purge"
    write(scenario / "prompts" / "brief.jinja", "{{ budget }} left.\n")
    write(scenario / "template_names.py", 'BRIEF_TEMPLATE = "brief.jinja"\n')
    write(
        scenario / "render.py",
        "renderer.render(template_name=BRIEF_TEMPLATE, template_variables={})\n",
    )

    messages = variable_findings(root)

    assert len(messages) == 1
    assert "without ['budget']" in messages[0]


def test_a_call_it_cannot_read_is_counted_rather_than_passed_over(tmp_path: Path) -> None:
    """A rule that skipped silently would report a clean tree it never looked at."""
    root = tree(tmp_path)
    scenario = root / "src" / "glossogen" / "scenarios" / "reactor_purge"
    write(scenario / "prompts" / "brief.jinja", "{{ budget }} left.\n")
    write(
        scenario / "render.py",
        "renderer.render(template_name=chosen, template_variables=variables)\n",
    )

    roots = find_template_roots(target=root, excluded=set())
    check = check_rendered_variables_match(roots=roots, target=root, excluded=set())

    assert check.findings == ()
    assert check.skipped == 1


def test_the_template_is_found_in_the_calling_scenario_not_another(tmp_path: Path) -> None:
    """Ten scenarios ship a `description.jinja`; each renderer searches only its own."""
    root = tree(tmp_path)
    scenarios = root / "src" / "glossogen" / "scenarios"
    write(scenarios / "reactor_purge" / "prompts" / "description.jinja", "{{ here }}\n")
    write(scenarios / "other_scenario" / "prompts" / "description.jinja", "{{ elsewhere }}\n")
    write(
        scenarios / "reactor_purge" / "render.py",
        'renderer.render(template_name="description.jinja", template_variables={"here": h})\n',
    )

    assert variable_findings(root) == []
