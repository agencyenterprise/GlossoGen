"""Build-time hooks for the documentation site.

Two problems, both caused by the documentation being written to be read in the
repository first.

**Pages outside `docs/`.** The README is the natural index, and `Architecture.md`,
`CONTRIBUTING.md`, `SECURITY.md` and `CHANGELOG.md` are documentation by any
reading, but mkdocs only collects what is under `docs_dir`. Rather than move them,
which would break every link to them on GitHub and in every clone, they are added
to the build from where they are.

**Links that leave the docs tree.** Dozens of links point at source
(`../src/...`), at tests, or at a root file. On GitHub they resolve. In a built
site they are 404s, because the source is not part of the site. They are rewritten
to permalinks on the default branch at build time, so the markdown keeps working
where it is written and the site gets links that work too.

The alternative was editing every one of them into an absolute URL. That reads
worse in the repository, which is where engineers actually read these files, and
rots silently the first time someone moves a file.
"""

import logging
import re
from pathlib import Path

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.plugins import event_priority
from mkdocs.structure.files import File, Files
from mkdocs.structure.pages import Page

logger = logging.getLogger("mkdocs.hooks")

REPO_BLOB = "https://github.com/agencyenterprise/GlossoGen/blob/main"
REPO_TREE = "https://github.com/agencyenterprise/GlossoGen/tree/main"

# Repository-root pages that belong in the site, and the name each takes inside it.
# The README becomes the index: it is already written as the entry point.
#
# `Architecture.md` is deliberately absent. It is an internal engineering write-up
# rather than documentation for someone using the platform, so it stays in the
# repository and links to it from the site become permalinks like any other file
# under `src/`.
ROOT_PAGES = {
    "README.md": "index.md",
    "CONTRIBUTING.md": "contributing.md",
    "SECURITY.md": "security.md",
    "CHANGELOG.md": "changelog.md",
    "notebooks/README.md": "notebooks.md",
    # The notebooks themselves: mkdocs-jupyter converts any .ipynb in the file
    # list, and executes it, so the site shows the outputs the repo strips.
    "notebooks/01_read_a_run.ipynb": "01_read_a_run.ipynb",
    "notebooks/02_score_a_run.ipynb": "02_score_a_run.ipynb",
    "notebooks/03_compare_runs.ipynb": "03_compare_runs.ipynb",
}

# Pages that live under `docs/` and are still not published. Excluded here rather
# than only left out of the nav, because mkdocs builds every file in `docs_dir`
# whether the nav mentions it or not: dropping the nav entry alone would publish
# the page and merely make it unlinked. Links to one become permalinks, so a reader
# on the site is sent to the copy in the repository.
REPO_ONLY_DOCS = (
    "documentation-style.md",
    "learnings.md",
    "communication-metrics.md",
    "compaction-and-clean-history-cost.md",
    "judge-decodability-exploit.md",
)

# Directories copied in whole because pages reference their contents.
ROOT_ASSET_DIRS = ("images",)

# Link text may itself hold brackets, which is ordinary here: a Next.js route
# segment is written `app/g/[groupSlug]/`. One level of nesting is allowed so those
# links are seen at all; without it the whole link is skipped and reaches the site
# unrewritten.
_TEXT = r"((?:[^\[\]]|\[[^\[\]]*\])*)"
_TARGET = r"([^)\s]+)"
_TITLE = r"(\s+\"[^\"]*\")?"

_LINK = re.compile(rf"(?<!!)\[{_TEXT}\]\({_TARGET}{_TITLE}\)")
_IMAGE = re.compile(rf"!\[{_TEXT}\]\({_TARGET}{_TITLE}\)")


# Before the plugins' own on_files (priority 0): mkdocs-jupyter converts the
# notebooks it finds in the file list, so the list has to hold them by then.
@event_priority(50)
def on_files(files: Files, config: MkDocsConfig) -> Files:
    """Add the repository-root pages and assets, and drop the repo-only ones."""
    root = Path(config.docs_dir).parent
    for repo_only in REPO_ONLY_DOCS:
        found = files.get_file_from_path(repo_only)
        if found is None:
            logger.warning("%s is listed as repo-only but is not in docs/", repo_only)
            continue
        files.remove(found)

    for source, destination in ROOT_PAGES.items():
        path = root / source
        if not path.is_file():
            logger.warning("Root page %s is missing; leaving it out of the site", source)
            continue
        files.append(
            File(
                path=destination,
                src_dir=str(path.parent),
                dest_dir=config.site_dir,
                use_directory_urls=config.use_directory_urls,
            )
        )
        # `File` derives its source name from `path`, so point it at the real file.
        files.get_file_from_path(destination).abs_src_path = str(path)

    for directory in ROOT_ASSET_DIRS:
        for asset in sorted((root / directory).rglob("*")):
            if not asset.is_file():
                continue
            files.append(
                File(
                    path=asset.relative_to(root).as_posix(),
                    src_dir=str(root),
                    dest_dir=config.site_dir,
                    use_directory_urls=config.use_directory_urls,
                )
            )
    return files


def on_page_markdown(markdown: str, page: Page, config: MkDocsConfig, files: Files) -> str:
    """Rewrite links that would not resolve in the built site.

    Resolution is done against where the page's source actually lives, which for
    the root pages is not ``docs/``. That is what makes ``docs/installation.md`` in
    the README and ``installation.md`` in a docs page both land in the right place.
    """
    _ = files
    root = Path(config.docs_dir).parent
    source_dir = Path(page.file.abs_src_path).parent

    def rewrite(match: re.Match[str], bang: str) -> str:
        text, target, title = match.group(1), match.group(2), match.group(3) or ""
        resolved = _resolve(target=target, source_dir=source_dir, root=root, config=config)
        if resolved is None:
            return match.group(0)
        return f"{bang}[{text}]({resolved}{title})"

    markdown = _LINK.sub(lambda match: rewrite(match, ""), markdown)
    return _IMAGE.sub(lambda match: rewrite(match, "!"), markdown)


def _resolve(target: str, source_dir: Path, root: Path, config: MkDocsConfig) -> str | None:
    """Return what a link should point at in the site, or None to leave it alone.

    Everything the site carries sits at its top level: the pages under ``docs/``
    keep their names, and each root page is added under a name of its own. So an
    in-site link is the target's name relative to ``docs/``, which is both what a
    page inside ``docs/`` already writes and what a root page's ``docs/x.md``
    should become.

    Relative rather than absolute on purpose. mkdocs resolves and validates a
    relative link and leaves an absolute one alone, so writing ``/installation``
    here would pass ``--strict`` whether or not the page existed.
    """
    if _is_external(target=target):
        return None

    path, separator, anchor = target.partition("#")
    if path == "":
        return None

    absolute = (source_dir / path).resolve()
    fragment = f"{separator}{anchor}" if separator else ""

    site_name = _site_page_for(absolute=absolute, root=root)
    if site_name is not None:
        return f"{site_name}{fragment}"

    docs_dir = Path(config.docs_dir).resolve()
    if _is_within(absolute=absolute, parent=docs_dir):
        rewritten = absolute.relative_to(docs_dir).as_posix()
        # A page kept out of the site is not in the site to link to, so send the
        # reader to the copy in the repository instead of at a page that 404s.
        if rewritten in REPO_ONLY_DOCS:
            return f"{REPO_BLOB}/{absolute.relative_to(root).as_posix()}{fragment}"
        if rewritten == path:
            return None
        return f"{rewritten}{fragment}"

    for directory in ROOT_ASSET_DIRS:
        if _is_within(absolute=absolute, parent=(root / directory).resolve()):
            return f"{absolute.relative_to(root).as_posix()}{fragment}"

    if not absolute.exists():
        logger.warning("Link %r on a page in %s points at nothing", target, source_dir)
        return None

    relative = absolute.relative_to(root).as_posix()
    base = REPO_TREE if absolute.is_dir() else REPO_BLOB
    return f"{base}/{relative}{fragment}"


def _site_page_for(absolute: Path, root: Path) -> str | None:
    """Return the in-site name of a repository-root page, if it is one."""
    for source, destination in ROOT_PAGES.items():
        if absolute == (root / source).resolve():
            return destination
    return None


def _is_within(absolute: Path, parent: Path) -> bool:
    """Whether a resolved path is inside a directory."""
    return parent == absolute or parent in absolute.parents


def _is_external(target: str) -> bool:
    """Whether a link target already points somewhere absolute."""
    return target.startswith(("http://", "https://", "mailto:", "#", "/"))
