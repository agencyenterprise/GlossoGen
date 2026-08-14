"""A scenario package shipping a preset that will not parse.

``orjson.JSONDecodeError`` subclasses ``ValueError``, the same type
``load_knobs_preset`` raises for a preset that is absent, so anything mapping
ValueError straight to "not found" tells the reader to look for a missing file
instead of at the syntax error in front of them.
"""
