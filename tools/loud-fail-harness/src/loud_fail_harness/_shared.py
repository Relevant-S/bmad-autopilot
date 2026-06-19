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

``atomic_write_text`` (added in story 22.5, the H1 cleanup-window promotion)
is the single source for the five config/artifact writers that previously
each carried a private ``_atomic_write_text`` copy
(``project_type_detection``, ``init_non_destructive_guard``,
``onboarding_benchmark``, ``install_path``, ``tea_boundary_orientation``).

The helpers exposed here have been moved verbatim from
``envelope_validator.py`` (their original landing in story 1.2). No behavioural
changes are intended; the extraction is purely structural to satisfy the
third-caller / DRY discipline (story 1.4 named story 1.5 as the right moment).

See ADR-003 substrate components 1/2/3/4. Nothing in this module is shipped to
user installations: the harness itself is CI-only (View 2 distribution unit).
"""

from __future__ import annotations

import os
import pathlib
import secrets
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


def atomic_write_text(path: pathlib.Path, body: str) -> None:
    """Pattern 4 atomic write — ``mkdir`` parents, then temp-file + ``os.replace``.

    Ensures ``path.parent`` exists, writes ``body`` to a collision-resistant
    temp file (``<path>.tmp.<pid>.<token_hex>``), ``os.fsync``s it, then
    ``os.replace``s it over ``path`` (atomic on POSIX). On any failure between
    create and replace the temp file is unlinked, so ``path`` is never partial.

    Distinct from :func:`loud_fail_harness.run_state.atomic_write_text`, which
    does NOT create the parent directory (its run-state-family callers
    initialise ``_bmad/automation/`` at init time). This helper is the single
    source for the config/artifact writers that must ensure their own target
    directory; promoted here from five byte-identical private copies in the
    story 22.5 H1 cleanup window.
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_path = path.with_name(
        f"{path.name}.tmp.{os.getpid()}.{secrets.token_hex(4)}"
    )
    try:
        fd = os.open(temp_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o644)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(body)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(temp_path, path)
    except BaseException:
        temp_path.unlink(missing_ok=True)
        raise
