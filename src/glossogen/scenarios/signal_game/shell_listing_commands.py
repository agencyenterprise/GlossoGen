"""``ls`` and ``stat`` for a player's shell, showing what the shared server records.

just-bash's own ``ls -l`` prints every file as owned by ``user`` at ``Jan  1 00:00``,
and its ``stat`` reports a fixed user and the modification time as the change time.
On the shared server the owner, the mode and both times are what one player can see
of the other's activity, so these commands read them from the server.

``ls`` takes ``-l``, ``-a``, ``-A``, ``-d``, ``-1``, ``-t``, ``-r``, ``-h`` and
``-F``, and prints one name per line, as ``ls`` does when its output is not a
terminal. ``stat`` prints GNU's layout, or the format given with ``-c`` /
``--format``.
"""

import math
from datetime import datetime
from typing import NamedTuple

from just_bash.types import CommandContext, ExecResult

from glossogen.scenarios.signal_game.file_modes import octal_mode, render_mode
from glossogen.scenarios.signal_game.server_shell_fs import ServerShellFs
from glossogen.scenarios.signal_game.shared_server import (
    NodeInfo,
    NodeKind,
    parent_of,
    user_id_of,
)

_LS_FLAGS = frozenset("laAd1trhF")
_LS_LONG_FLAGS = {"--all": "a", "--almost-all": "A", "--directory": "d", "--reverse": "r"}
_RECENT_TIME_FORMAT = "%b %d %H:%M"
_STAT_TIME_FORMAT = "%Y-%m-%d %H:%M:%S.%f000 +0000"
_BLOCK_SIZE = 4096


class _ListedNode(NamedTuple):
    """A node as ``ls`` shows it: its metadata and the name to print."""

    info: NodeInfo
    shown_name: str


def _shell_fs(ctx: CommandContext) -> ServerShellFs:
    if not isinstance(ctx.fs, ServerShellFs):
        raise TypeError("signal_game's ls and stat run only on the shared server")
    return ctx.fs


def _failed(stderr: str, exit_code: int) -> ExecResult:
    return ExecResult(stdout="", stderr=stderr, exit_code=exit_code)


def _human_size(size: int) -> str:
    """``size`` as ``ls -h`` prints it: bytes, then K, M, G with one decimal below 10."""
    value = float(size)
    for unit in ("", "K", "M", "G"):
        if value < 1024 or unit == "G":
            if unit == "":
                return str(size)
            if value < 10:
                return f"{math.ceil(value * 10) / 10:.1f}{unit}"
            return f"{math.ceil(value):.0f}{unit}"
        value /= 1024
    return str(size)


def _type_suffix(info: NodeInfo) -> str:
    """What ``ls -F`` appends: ``/`` to a directory, ``*`` to an executable file."""
    if info.kind is NodeKind.DIRECTORY:
        return "/"
    if info.mode & 0o111:
        return "*"
    return ""


class LsCommand:
    """``ls``, over the server's owners, modes and times."""

    name = "ls"

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """List each operand: a file as itself, a directory as its entries."""
        fs = _shell_fs(ctx=ctx)
        flags: set[str] = set()
        operands: list[str] = []
        for argument in args:
            if argument in _LS_LONG_FLAGS:
                flags.add(_LS_LONG_FLAGS[argument])
            elif argument.startswith("-") and argument != "-":
                for flag in argument[1:]:
                    if flag not in _LS_FLAGS:
                        return _failed(
                            stderr=(
                                f"ls: invalid option -- '{flag}'\n"
                                "Try 'ls --help' for more information.\n"
                            ),
                            exit_code=2,
                        )
                    flags.add(flag)
            else:
                operands.append(argument)
        if not operands:
            operands = ["."]
        stderr = ""
        exit_code = 0
        files: list[_ListedNode] = []
        directories: list[tuple[str, list[_ListedNode]]] = []
        for operand in operands:
            path = fs.resolve_path(base=ctx.cwd, path=operand)
            looked = fs.look(path=path)
            if isinstance(looked, str):
                stderr += f"ls: cannot access '{operand}': {looked}\n"
                exit_code = 2
                continue
            if looked.kind is NodeKind.FILE or "d" in flags:
                files.append(_ListedNode(info=looked, shown_name=operand))
                continue
            inside = fs.look_inside(path=path)
            if isinstance(inside, str):
                stderr += f"ls: cannot open directory '{operand}': {inside}\n"
                exit_code = 2
                continue
            directories.append(
                (operand, self._entries(fs=fs, path=path, inside=inside, flags=flags))
            )
        blocks: list[str] = []
        if files:
            blocks.append(
                self._render(nodes=self._sorted(nodes=files, flags=flags), flags=flags, total=False)
            )
        for operand, entries in directories:
            body = self._render(
                nodes=self._sorted(nodes=entries, flags=flags), flags=flags, total=True
            )
            if len(operands) > 1:
                body = f"{operand}:\n{body}"
            blocks.append(body)
        return ExecResult(stdout="\n".join(blocks), stderr=stderr, exit_code=exit_code)

    @staticmethod
    def _entries(
        fs: ServerShellFs, path: str, inside: list[NodeInfo], flags: set[str]
    ) -> list[_ListedNode]:
        """A directory's entries as listed.

        Hidden entries show under ``-a`` or ``-A``, and ``.`` and ``..`` under ``-a``.
        """
        entries = [
            _ListedNode(info=info, shown_name=info.name)
            for info in inside
            if not info.name.startswith(".") or flags & {"a", "A"}
        ]
        if "a" in flags:
            for shown_name, dot_path in ((".", path), ("..", parent_of(path=path))):
                looked = fs.look(path=dot_path)
                if not isinstance(looked, str):
                    entries.append(_ListedNode(info=looked, shown_name=shown_name))
        return entries

    @staticmethod
    def _sorted(nodes: list[_ListedNode], flags: set[str]) -> list[_ListedNode]:
        if "t" in flags:
            ordered = sorted(
                nodes, key=lambda node: (-node.info.modified.timestamp(), node.shown_name)
            )
        else:
            ordered = sorted(nodes, key=lambda node: node.shown_name)
        if "r" in flags:
            ordered.reverse()
        return ordered

    def _render(self, nodes: list[_ListedNode], flags: set[str], total: bool) -> str:
        if "l" not in flags:
            lines = []
            for node in nodes:
                suffix = ""
                if "F" in flags:
                    suffix = _type_suffix(info=node.info)
                lines.append(f"{node.shown_name}{suffix}\n")
            return "".join(lines)
        sizes = [self._size(info=node.info, flags=flags) for node in nodes]
        owner_width = max((len(node.info.owner) for node in nodes), default=1)
        size_width = max((len(size) for size in sizes), default=1)
        lines: list[str] = []
        if total:
            lines.append(f"total {sum(self._blocks(info=node.info) for node in nodes)}\n")
        for node, size in zip(nodes, sizes, strict=True):
            info = node.info
            links = 1
            if info.kind is NodeKind.DIRECTORY:
                links = 2
            suffix = ""
            if "F" in flags:
                suffix = _type_suffix(info=info)
            mode = render_mode(mode=info.mode, is_directory=info.kind is NodeKind.DIRECTORY)
            lines.append(
                f"{mode} {links} {info.owner:<{owner_width}} {info.owner:<{owner_width}} "
                f"{size:>{size_width}} {info.modified.strftime(_RECENT_TIME_FORMAT)} "
                f"{node.shown_name}{suffix}\n"
            )
        return "".join(lines)

    @staticmethod
    def _size(info: NodeInfo, flags: set[str]) -> str:
        if "h" in flags:
            return _human_size(size=info.size)
        return str(info.size)

    @staticmethod
    def _blocks(info: NodeInfo) -> int:
        """1K blocks a node takes, counted in whole 4K blocks."""
        return math.ceil(info.size / _BLOCK_SIZE) * (_BLOCK_SIZE // 1024)


class StatCommand:
    """``stat``, over the server's owners, modes and both times."""

    name = "stat"

    def __init__(self, users: tuple[str, ...]) -> None:
        self._users = users

    async def execute(self, args: list[str], ctx: CommandContext) -> ExecResult:
        """Print each operand's metadata in GNU's layout, or in the format given."""
        fs = _shell_fs(ctx=ctx)
        template: str | None = None
        operands: list[str] = []
        remaining = list(args)
        while remaining:
            argument = remaining.pop(0)
            if argument in ("-c", "--format"):
                if not remaining:
                    return _failed(
                        stderr=f"stat: option requires an argument -- '{argument}'\n", exit_code=1
                    )
                template = remaining.pop(0)
            elif argument.startswith("--format="):
                template = argument.removeprefix("--format=")
            elif argument in ("-L", "--dereference"):
                continue
            elif argument.startswith("-") and argument != "-":
                return _failed(
                    stderr=f"stat: invalid option -- '{argument.lstrip('-')}'\n", exit_code=1
                )
            else:
                operands.append(argument)
        if not operands:
            return _failed(stderr="stat: missing operand\n", exit_code=1)
        stdout = ""
        stderr = ""
        exit_code = 0
        for operand in operands:
            looked = fs.look(path=fs.resolve_path(base=ctx.cwd, path=operand))
            if isinstance(looked, str):
                stderr += f"stat: cannot statx '{operand}': {looked}\n"
                exit_code = 1
                continue
            if template is None:
                stdout += self._default(info=looked, operand=operand)
            else:
                stdout += self._formatted(info=looked, operand=operand, template=template) + "\n"
        return ExecResult(stdout=stdout, stderr=stderr, exit_code=exit_code)

    def _default(self, info: NodeInfo, operand: str) -> str:
        user_id = user_id_of(user=info.owner, users=self._users)
        mode = render_mode(mode=info.mode, is_directory=info.kind is NodeKind.DIRECTORY)
        blocks = math.ceil(info.size / _BLOCK_SIZE) * (_BLOCK_SIZE // 512)
        return (
            f"  File: {operand}\n"
            f"  Size: {info.size:<10}\tBlocks: {blocks:<10} IO Block: {_BLOCK_SIZE}   "
            f"{_kind_label(info=info)}\n"
            f"Access: ({octal_mode(mode=info.mode)}/{mode})  Uid: ({user_id:>5}/{info.owner:>8})   "
            f"Gid: ({user_id:>5}/{info.owner:>8})\n"
            f"Modify: {_stat_time(moment=info.modified)}\n"
            f"Change: {_stat_time(moment=info.changed)}\n"
        )

    def _formatted(self, info: NodeInfo, operand: str, template: str) -> str:
        user_id = str(user_id_of(user=info.owner, users=self._users))
        links = "1"
        if info.kind is NodeKind.DIRECTORY:
            links = "2"
        fields = {
            "n": operand,
            "N": f"'{operand}'",
            "s": str(info.size),
            "F": _kind_label(info=info),
            "a": f"{info.mode & 0o7777:o}",
            "A": render_mode(mode=info.mode, is_directory=info.kind is NodeKind.DIRECTORY),
            "u": user_id,
            "U": info.owner,
            "g": user_id,
            "G": info.owner,
            "y": _stat_time(moment=info.modified),
            "Y": str(int(info.modified.timestamp())),
            "z": _stat_time(moment=info.changed),
            "Z": str(int(info.changed.timestamp())),
            "x": _stat_time(moment=info.modified),
            "X": str(int(info.modified.timestamp())),
            "h": links,
            "%": "%",
        }
        output = ""
        index = 0
        while index < len(template):
            character = template[index]
            if character == "%" and index + 1 < len(template):
                output += fields.get(template[index + 1], "?")
                index += 2
                continue
            output += character
            index += 1
        return output


def _kind_label(info: NodeInfo) -> str:
    if info.kind is NodeKind.DIRECTORY:
        return "directory"
    if info.size == 0:
        return "regular empty file"
    return "regular file"


def _stat_time(moment: datetime) -> str:
    return moment.strftime(_STAT_TIME_FORMAT)
