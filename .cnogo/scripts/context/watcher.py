"""Live file watcher for the context graph.

Watches source files for changes and triggers re-indexing. Uses watchfiles
for efficient filesystem notification with extension and gitignore filtering.
"""

from __future__ import annotations

import threading
from pathlib import Path
from typing import Any, Callable

from watchfiles import Change, DefaultFilter, watch

from scripts.context.walker import SUPPORTED_EXTENSIONS, _DEFAULT_SKIP, _load_gitignore, _is_ignored


class SourceFileFilter(DefaultFilter):
    """Filter that accepts only source files, rejecting skip dirs and gitignore matches."""

    def __init__(self, repo_root: str | Path) -> None:
        self._repo_root = Path(repo_root).resolve()
        self._gitignore_patterns = _load_gitignore(self._repo_root)
        # Use _DEFAULT_SKIP dirs plus DefaultFilter's own ignore dirs
        all_ignore_dirs = list(_DEFAULT_SKIP | set(DefaultFilter.ignore_dirs))
        super().__init__(ignore_dirs=all_ignore_dirs)

    def __call__(self, change: Change, path: str) -> bool:
        if not super().__call__(change, path):
            return False

        p = Path(path)

        # For deleted files, we can't check extension on disk — accept if extension matches
        # For added/modified, also check extension
        suffix = p.suffix
        if suffix not in SUPPORTED_EXTENSIONS:
            return False

        # Check gitignore patterns using relative path
        try:
            rel_path = p.relative_to(self._repo_root)
        except ValueError:
            return False

        if _is_ignored(rel_path, self._gitignore_patterns):
            return False

        return True


class FileWatcher:
    """Watches a repo for source file changes and invokes a callback.

    Usage:
        watcher = FileWatcher("/path/to/repo", on_change=my_callback)
        watcher.start()  # blocks until stop() is called or KeyboardInterrupt
    """

    def __init__(
        self,
        repo_path: str | Path,
        on_change: Callable[[set[tuple[Change, str]]], Any],
        debounce_ms: int = 1600,
    ) -> None:
        self._repo_path = Path(repo_path).resolve()
        self._on_change = on_change
        self._debounce_ms = debounce_ms
        self._stop_event = threading.Event()
        self._filter = SourceFileFilter(self._repo_path)

    def start(self) -> None:
        """Start watching. Blocks until stop() is called or KeyboardInterrupt."""
        for changes in watch(
            self._repo_path,
            watch_filter=self._filter,
            debounce=self._debounce_ms,
            stop_event=self._stop_event,
        ):
            if self._stop_event.is_set():
                break
            self._on_change(changes)

    def stop(self) -> None:
        """Signal the watcher to stop."""
        self._stop_event.set()
