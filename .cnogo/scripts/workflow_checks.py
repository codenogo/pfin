#!/usr/bin/env python3
"""Compatibility wrapper for workflow checks.

`workflow_checks_core.py` holds implementation details. This wrapper preserves
existing entrypoint and import paths (`scripts/workflow_checks.py`).
"""

from __future__ import annotations

try:
    import _bootstrap  # noqa: F401
except ImportError:
    pass  # imported as module; caller manages sys.path

try:
    import workflow_checks_core as _core
except ModuleNotFoundError:
    from . import workflow_checks_core as _core  # type: ignore

# Re-export all non-dunder symbols for backward compatibility.
for _name in dir(_core):
    if not _name.startswith("__"):
        globals()[_name] = getattr(_core, _name)

del _name

if __name__ == "__main__":
    raise SystemExit(_core.main())
