# Research: $ARGUMENTS
<!-- effort: high -->

Produce a durable research artifact that reduces decision uncertainty.

## Arguments

`/research <topic>`

## Your Task

1. Load:
- policy from `docs/planning/WORKFLOW.json`
- `.claude/skills/research-evidence-synthesis/SKILL.md`
- only the needed reference files under `.claude/skills/research-evidence-synthesis/references/`

2. Read policy from `docs/planning/WORKFLOW.json`:
- `off`: stop and explain how to enable
- `local`: repo-only sources
- `mcp`: repo + configured MCP sources
- `web`/`auto`: include web if environment allows

3. Create artifact folder:
- `docs/planning/work/research/<slug>/RESEARCH.md`
- `docs/planning/work/research/<slug>/RESEARCH.json`

4. Gather evidence in this order:
- repo code/docs/history (`rg`, `git log`)
- MCP systems (if enabled)
- web primary sources (official docs/specs)
- keep one manager agent for synthesis; use at most 1-3 read-only scouts for bounded evidence gathering when needed

5. Synthesize for this project:
- options and fit criteria
- risks/failure modes
- recommendation with tradeoffs
- open questions
- clear separation of evidence, inference, and recommendation
- whether this uncertainty belongs in initiative-level `/shape` or feature-level `/discuss`

6. Write contracts:
- `RESEARCH.md`: concise narrative
- `RESEARCH.json`: `schemaVersion`, `topic`, `slug`, `timestamp`, `mode`, `sources[]`, `summary[]`, `recommendation`

7. Validate:
```bash
python3 .cnogo/scripts/workflow_validate.py --json
```

## Output

- Artifact paths
- Top conclusions
- Recommended next command:
  - `/shape <initiative>` when the topic changes cross-feature direction, sequencing, or architecture
  - `/discuss <feature>` only when the topic is already feature-local
