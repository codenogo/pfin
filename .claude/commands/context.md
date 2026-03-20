# Context: $ARGUMENTS
<!-- effort: low -->

Build a focused context pack for a feature/topic.

## Your Task

1. Locate relevant code/docs/tests with fast search:
```bash
rg -l "$ARGUMENTS" .
```
Exclude generated/vendor dirs.

2. Identify risk hotspots:
```bash
git log --since="3 months ago" --name-only --pretty=format: | sort | uniq -c | sort -rn | head -20
```
Prioritize files that are both relevant and high-churn.

3. Find related tests and configs:
- tests by name/keyword match
- configs (`yml/yaml/json/toml/xml/properties`) containing topic keywords

4. Check planning artifacts if present:
- `docs/planning/work/features/*<topic>*/CONTEXT.md`
- adjacent plan/review/summary artifacts

5. Produce context pack with:
- core files (top 3-5)
- tests
- configs
- hotspots/risk notes
- dependency touchpoints
- explicit “don’t break” contracts

6. Load the top files into working context.

## Output

A concise context pack with file paths, relevance notes, and immediate next investigation targets.
