"""Permission modes on the shared server as ``ls`` and ``stat`` print them.

A mode is the nine permission bits plus the sticky bit (``0o1000``); setuid and setgid
are not modelled.
"""

STICKY = 0o1000


def render_mode(mode: int, is_directory: bool) -> str:
    """The mode as ``ls -l`` prints it, such as ``drwxrwxrwt`` or ``-rw-r--r--``."""
    kind = "-"
    if is_directory:
        kind = "d"
    letters = [kind]
    for shift in (6, 3, 0):
        triple = (mode >> shift) & 0o7
        for letter, bit in (("r", 4), ("w", 2), ("x", 1)):
            shown = "-"
            if triple & bit:
                shown = letter
            letters.append(shown)
    if mode & STICKY:
        if letters[-1] == "x":
            letters[-1] = "t"
        else:
            letters[-1] = "T"
    return "".join(letters)


def octal_mode(mode: int) -> str:
    """The mode as four octal digits, as ``stat`` prints it: ``0644``, ``1777``."""
    return f"{mode:04o}"
