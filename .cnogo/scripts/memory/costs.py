#!/usr/bin/env python3
"""Transcript-based cost tracking for Claude Code sessions.

Parses session JSONL transcripts to extract token usage and estimate
costs with model-specific pricing. Python stdlib only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

PRICING = {
    "opus": {"input": 15.0, "output": 75.0, "cache_read": 1.50, "cache_creation": 3.75},
    "sonnet": {"input": 3.0, "output": 15.0, "cache_read": 0.30, "cache_creation": 0.75},
    "haiku": {"input": 0.80, "output": 4.0, "cache_read": 0.08, "cache_creation": 0.20},
}


@dataclass
class TranscriptUsage:
    input_tokens: int = 0
    output_tokens: int = 0
    cache_read_tokens: int = 0
    cache_creation_tokens: int = 0
    model: str = ""


def detect_model(model_str: str) -> str:
    """Detect model family from model string. Returns 'opus', 'sonnet', or 'haiku'."""
    lower = model_str.lower()
    for key in ("opus", "sonnet", "haiku"):
        if key in lower:
            return key
    return "sonnet"


def parse_transcript(path: Path) -> TranscriptUsage:
    """Parse a single JSONL transcript and aggregate token usage across all turns."""
    usage = TranscriptUsage()
    with open(path, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
            except json.JSONDecodeError:
                continue
            if not isinstance(entry, dict):
                continue
            if entry.get("type") != "assistant":
                continue
            # Extract model from first response that has it
            if not usage.model:
                model_str = entry.get("model", "")
                if model_str:
                    usage.model = detect_model(model_str)
            # Extract usage block
            u = entry.get("usage")
            if not isinstance(u, dict):
                continue
            usage.input_tokens += u.get("input_tokens", 0)
            usage.output_tokens += u.get("output_tokens", 0)
            usage.cache_read_tokens += u.get("cache_read_input_tokens", 0)
            usage.cache_creation_tokens += u.get("cache_creation_input_tokens", 0)
    return usage


def estimate_cost(usage: TranscriptUsage) -> float:
    """Estimate cost in USD from token usage using PRICING rates."""
    model_key = usage.model if usage.model in PRICING else "sonnet"
    rates = PRICING[model_key]
    cost = (
        usage.input_tokens * rates["input"] / 1_000_000
        + usage.output_tokens * rates["output"] / 1_000_000
        + usage.cache_read_tokens * rates["cache_read"] / 1_000_000
        + usage.cache_creation_tokens * rates["cache_creation"] / 1_000_000
    )
    return cost


def find_session_transcripts(project_slug: str) -> list[Path]:
    """Find all JSONL session transcripts for a Claude Code project."""
    base = Path.home() / ".claude" / "projects" / project_slug
    if not base.exists():
        return []
    return sorted(base.glob("*.jsonl"))


def summarize_project_costs(project_slug: str) -> dict:
    """Parse all transcripts for a project and return aggregated cost summary."""
    transcripts = find_session_transcripts(project_slug)
    total_input = 0
    total_output = 0
    total_cache_read = 0
    total_cache_creation = 0
    total_cost = 0.0
    sessions = []
    for t in transcripts:
        usage = parse_transcript(t)
        cost = estimate_cost(usage)
        total_input += usage.input_tokens
        total_output += usage.output_tokens
        total_cache_read += usage.cache_read_tokens
        total_cache_creation += usage.cache_creation_tokens
        total_cost += cost
        sessions.append({
            "path": str(t),
            "model": usage.model,
            "tokens": usage.input_tokens + usage.output_tokens,
            "cost_usd": cost,
        })
    return {
        "project": project_slug,
        "total_input_tokens": total_input,
        "total_output_tokens": total_output,
        "total_cache_read_tokens": total_cache_read,
        "total_cache_creation_tokens": total_cache_creation,
        "total_estimated_cost_usd": total_cost,
        "sessions": sessions,
    }
