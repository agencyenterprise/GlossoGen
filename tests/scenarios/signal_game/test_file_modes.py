"""How ``ls`` and ``stat`` print a mode on the shared server."""

from glossogen.scenarios.signal_game.file_modes import octal_mode, render_mode


def test_ls_prints_the_mode_with_the_sticky_bit() -> None:
    assert render_mode(mode=0o644, is_directory=False) == "-rw-r--r--"
    assert render_mode(mode=0o1777, is_directory=True) == "drwxrwxrwt"
    assert render_mode(mode=0o1770, is_directory=True) == "drwxrwx--T"


def test_stat_prints_four_octal_digits() -> None:
    assert octal_mode(mode=0o640) == "0640"
    assert octal_mode(mode=0o1777) == "1777"
