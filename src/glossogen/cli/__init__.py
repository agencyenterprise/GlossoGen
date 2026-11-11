"""The ``glossogen`` command line.

``cli_entry`` builds the parser and dispatches to a subcommand. Each other module
holds one subcommand, or a family of them, with its flags beside its handler. A new
subcommand gets its own module here: its ``add_<command>_parser`` is called from
``cli_entry._build_parser`` and its handler goes in ``cli_entry``'s dispatch table.
"""
