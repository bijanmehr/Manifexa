"""Eminexa — the people-connection subsystem of Manifexa.

Open ``manifexa`` on an Eminexa folder, ``add`` a researcher by OpenAlex id /
ORCID / Scholar link, and the engine pulls their 5-year record and grows a graph
of ``person`` nodes joined by ``coauthored`` and inferred ``same_group`` edges.
People live in the SQLite cache (``source="eminexa"``) and project into the
derived graph on every rebuild, so discovery works on them for free.
"""
