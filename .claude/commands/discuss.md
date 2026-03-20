# Discuss: $ARGUMENTS
<!-- effort: medium -->

Clarify one feature before planning or coding.

## Your Task

Treat `$ARGUMENTS` as the display name unless the user gives a slug. Always derive a kebab-case `<feature-slug>` for `docs/planning/work/features/<feature-slug>/`.

## Steps

1. **Branch**
   - Check `git branch --show-current` and `git status --porcelain`.
   - If a switch is needed and the tree is dirty, stop and ask the user to stash or commit.
   - If `feature/<feature-slug>` exists, switch to it and run `git pull --ff-only` when possible.
   - Otherwise switch to `main` or `master`, pull, and create `feature/<feature-slug>`.
   - Report the final branch before writing artifacts.

2. **Context**
   - Read `docs/planning/PROJECT.md`.
   - If `docs/planning/work/features/<feature-slug>/FEATURE.json` exists, load it first.
   - If that feature stub has `parentShape`, load the linked `SHAPE.json` and inherit only the feature-relevant cross-feature truth.
   - Treat shape as still active; this feature is an optional branch from the workspace.
   - If no feature stub exists, continue as a direct single-feature fast path.
   - Run `python3 .cnogo/scripts/workflow_memory.py phase-get <feature-slug>`.
   - Run `python3 .cnogo/scripts/workflow_memory.py prime --limit 5`.
   - Search the repo for relevant code and optional graph context:
     `python3 .cnogo/scripts/workflow_memory.py graph-enrich --keywords "<feature keywords>" --json`
   - Only use `/research "$ARGUMENTS"` when unresolved risk is feature-local.

3. **Decision conversation**
   - architecture / API shape
   - data flow / failure handling
   - UX / error behavior
   - operational risks, rollback, observability
   - do not restate initiative-wide truth that already lives in `SHAPE.json`
   - if feature-local decisions imply initiative-level follow-up, record suggested feedback for a later `/shape` pass instead of editing `SHAPE.json`

4. **Persist source of truth**
   Create `CONTEXT.json` and `CONTEXT.md` under the feature directory.

   `CONTEXT.json` must include `schemaVersion`, `feature`, `displayName`, `decisions[]`, `constraints[]`, `openQuestions[]`, `relatedCode[]`, and `timestamp`.
   - If inheriting from shape, include `parentShape` (`path`, `timestamp`, `schemaVersion`)
   - If a feature stub exists, include `featureStub` (`path`, `timestamp`, `schemaVersion`)
   - Keep inherited context as references and deltas, not copied initiative prose
   - Optional fields: `featureId`, `research[]`, `memoryEpicId`, `shapeFeedback[]`
   - `shapeFeedback[]` stores suggested workspace updates with `summary` and optional `affectedFeatures[]` / `suggestedAction`

5. **Optional memory**
   If memory is initialized, create the feature epic, store its ID in `CONTEXT.json`, and run `python3 .cnogo/scripts/workflow_memory.py phase-set <feature-slug> discuss`.

6. **Validate**
   Run `python3 .cnogo/scripts/workflow_validate.py`.

## Output

- final feature-local decisions, inherited constraints, and open questions
- any suggested feedback to bring back into `/shape`
- paths to `CONTEXT.json` and `CONTEXT.md`
- confirmation the feature is ready for `/plan <feature-slug>`
