# Research Output Contract

Use this structure when writing research artifacts.

## `RESEARCH.md`

Keep the markdown concise and decision-oriented:

1. Topic and decision to resolve
2. Evidence summary
3. Options and tradeoffs
4. Recommendation
5. Open questions
6. Next command

## `RESEARCH.json`

Keep the JSON contract lean and durable:

- `schemaVersion`
- `topic`
- `slug`
- `timestamp`
- `mode`
- `sources[]`
- `summary[]`
- `recommendation`

## Routing Rule

- Recommend `/shape <initiative>` when the research changes initiative direction, architecture, sequencing, or feature inventory.
- Recommend `/discuss <feature>` only when the uncertainty is already contained within one feature.
