"""Substrate-shared helper module for the loud-fail harness.

Created in story 1.5 per the third-caller extraction rule deferred from
stories 1.2 + 1.3 + 1.4. Consumers:

* :mod:`loud_fail_harness.envelope_validator` (substrate component 1) —
  uses ``find_repo_root``, ``load_schema``, ``_path_pointer``.
* :mod:`loud_fail_harness.event_validator` (substrate component 2) —
  uses ``find_repo_root``, ``load_schema``, ``_path_pointer``.
* :mod:`loud_fail_harness.reconciler` (substrate component 3) —
  uses ``find_repo_root`` only.
* :mod:`loud_fail_harness.enumeration_check` (substrate component 4) —
  uses ``find_repo_root``, ``load_schema``, ``_path_pointer``.

The helpers exposed here have been moved verbatim from
``envelope_validator.py`` (their original landing in story 1.2). No behavioural
changes are intended; the extraction is purely structural to satisfy the
third-caller / DRY discipline (story 1.4 named story 1.5 as the right moment).

See ADR-003 substrate components 1/2/3/4. Nothing in this module is shipped to
user installations: the harness itself is CI-only (View 2 distribution unit).
"""

from __future__ import annotations

import pathlib
from collections.abc import Iterable

import yaml
from jsonschema import Draft202012Validator
from jsonschema.exceptions import SchemaError


def find_repo_root(start: pathlib.Path | None = None) -> pathlib.Path:
    """Walk up from ``start`` (default: this file's directory) looking for
    a directory that contains ``.github``. The harness is CI-only and always
    lives inside the repo, so this is a safe default-resolution strategy.

    Raises ``RuntimeError`` (loud-fail) if no ``.github`` ancestor is found.
    """
    here = (start or pathlib.Path(__file__)).resolve()
    for candidate in [here, *here.parents]:
        if (candidate / ".github").is_dir():
            return candidate
    raise RuntimeError(
        "harness-level error: could not locate repo root (no .github ancestor) "
        f"starting from {here}"
    )


def load_schema(schema_path: pathlib.Path) -> dict:
    """Read a YAML schema from disk and meta-validate it.

    Raises ``SchemaError`` if the document is not a valid JSON Schema 2020-12
    document. Raises ``OSError`` if the file is unreadable.
    """
    raw = yaml.safe_load(schema_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SchemaError(
            f"schema file {schema_path} did not parse to a YAML mapping at top level"
        )
    Draft202012Validator.check_schema(raw)
    return raw


def _path_pointer(path: Iterable[object]) -> str:
    """Render a JSON-pointer-like path for human-readable error output."""
    parts = [str(p) for p in path]
    return "/" + "/".join(parts) if parts else "<root>"
