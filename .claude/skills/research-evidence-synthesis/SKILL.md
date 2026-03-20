---
name: research-evidence-synthesis
description: Evidence-first research workflow for technical, architectural, and product uncertainty. Use when Codex is running `/research`, comparing options, synthesizing repo/MCP/web sources, ranking source quality, or deciding whether uncertainty should route back to `/shape` or forward to `/discuss`.
tags: [workflow, research, evidence]
appliesTo: [research, spawn]
---
# Research Evidence Synthesis

Use this skill to reduce uncertainty with source-ranked evidence instead of freeform brainstorming.

## Goal

Produce a durable recommendation that is grounded in the best available evidence for this repo and this decision.

## Read Next

- `references/source-quality.md` when sources conflict, quality is uneven, or web evidence is involved.
- `references/research-output-contract.md` when drafting `RESEARCH.md` or `RESEARCH.json`.

## Rules

1. Keep one manager agent responsible for framing, synthesis, and artifact writes.
2. Use read-only scouts only for bounded tasks such as repo feasibility scans, official-doc lookup, or risk challenge. Cap this at 1-3 scouts.
3. Gather evidence in this order unless the question clearly requires otherwise:
- repo code, docs, history
- MCP systems enabled by policy
- official/spec sources on the web
4. Prefer primary sources over commentary. If you must rely on secondary sources, say so.
5. Keep evidence, inference, and recommendation separate. Capture findings as:
- evidence: what the source says or what the repo proves
- inference: what that evidence implies for this project
- recommendation: what we should do now
6. Mark uncertainty explicitly. If the evidence is insufficient, say what is missing instead of overcommitting.
7. Keep quotes short and purposeful. Prefer paraphrase plus source links.
8. Stop when uncertainty has materially dropped and the next command is clear.
9. Route cross-feature or initiative-level uncertainty back to `/shape`. Route feature-local uncertainty to `/discuss`.

## Output

- source-ranked findings
- recommendation with tradeoffs
- open questions or missing evidence
- next-step routing to `/shape` or `/discuss`
