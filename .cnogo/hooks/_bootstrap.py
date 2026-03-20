"""
cnogo path bootstrap.

Adds the .cnogo/ directory to sys.path so that imports like
'from scripts.memory import ...' resolve to .cnogo/scripts/memory/.

Usage in entry-point scripts:
    import _bootstrap  # noqa: F401
"""
import os
import sys

_cnogo_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _cnogo_dir not in sys.path:
    sys.path.insert(0, _cnogo_dir)
