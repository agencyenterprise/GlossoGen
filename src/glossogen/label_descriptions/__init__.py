"""A group's label glossary: what each label means, keyed on the exact label string.

Labels themselves stay plain strings in each run's ``labels.json``; a description is
recorded once per group and applies to every run carrying that label. Nothing here
imports FastAPI, so the same store answers a REST request and a ``glossogen
describe-label`` invocation that never starts a server. One contract, two backings:
Postgres when ``DATABASE_URL`` is set, a JSON file per group under
``<runs-dir>/_label_descriptions/`` when it is not.
"""
