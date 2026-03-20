#!/usr/bin/env python3
"""Data classes for the cnogo memory engine.

All models are plain dataclasses — no ORM, no external dependencies.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

# ---------------------------------------------------------------------------
# Deterministic coordination type system (Contract 01, 03)
# ---------------------------------------------------------------------------

OBJECT_TYPES = frozenset({'epic', 'plan', 'task'})
ACTOR_ROLES = frozenset({'leader', 'worker', 'hook'})
TASK_STATES = ('open', 'in_progress', 'done_by_worker', 'verified', 'closed')
PLAN_EPIC_STATES = ('open', 'ready_to_close', 'closed')
CLOSE_REASONS = frozenset({'completed', 'rejected', 'superseded', 'blocked', 'failed'})


@dataclass
class Issue:
    """Core unit of work in the memory engine."""

    id: str
    title: str
    content_hash: str = ""
    description: str = ""
    status: str = "open"
    state: str = "open"
    issue_type: str = "task"
    priority: int = 2
    assignee: str = ""
    owner_actor: str = ""
    feature_slug: str = ""
    plan_number: str = ""
    phase: str = "discuss"
    close_reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""
    updated_at: str = ""
    closed_at: str = ""
    # Populated by show() / list queries — not stored inline in issues table
    labels: list[str] = field(default_factory=list)
    deps: list[Dependency] = field(default_factory=list)
    blocks_issues: list[str] = field(default_factory=list)
    recent_events: list[Event] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        """Serialize to dict for JSONL export. Omits empty optional fields."""
        d: dict[str, Any] = {
            "id": self.id,
            "title": self.title,
            "status": self.status,
            "issue_type": self.issue_type,
            "priority": self.priority,
            "phase": self.phase,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self.content_hash:
            d["content_hash"] = self.content_hash
        if self.description:
            d["description"] = self.description
        if self.assignee:
            d["assignee"] = self.assignee
        if self.feature_slug:
            d["feature_slug"] = self.feature_slug
        if self.plan_number:
            d["plan_number"] = self.plan_number
        if self.state != "open":
            d["state"] = self.state
        if self.owner_actor:
            d["owner_actor"] = self.owner_actor
        if self.close_reason:
            d["close_reason"] = self.close_reason
        if self.metadata:
            d["metadata"] = self.metadata
        if self.closed_at:
            d["closed_at"] = self.closed_at
        if self.labels:
            d["labels"] = self.labels
        if self.deps:
            d["deps"] = [dep.to_dict() for dep in self.deps]
        return d

    def valid_states(self) -> tuple[str, ...]:
        """Return valid state transitions for this issue type."""
        if self.issue_type in ('plan', 'epic'):
            return PLAN_EPIC_STATES
        return TASK_STATES


@dataclass
class Dependency:
    """Directed edge between issues."""

    issue_id: str
    depends_on_id: str
    dep_type: str = "blocks"
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"depends_on": self.depends_on_id, "type": self.dep_type}


@dataclass
class Event:
    """Immutable audit trail entry."""

    id: int = 0
    issue_id: str = ""
    event_type: str = ""
    actor: str = ""
    data: dict[str, Any] = field(default_factory=dict)
    created_at: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "event_type": self.event_type,
            "actor": self.actor,
            "data": self.data,
            "created_at": self.created_at,
        }
