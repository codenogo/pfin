# Validate
<!-- effort: low -->

Enforce workflow rules with a machine-checkable validator. Use this before `/review` and before shipping.

## Your Task

Run the workflow validator and report results clearly.

### Step 1: Run Validation

```bash
python3 .cnogo/scripts/workflow_validate.py
```

If the user is about to commit, validate only what’s staged:

```bash
python3 .cnogo/scripts/workflow_validate.py --staged
```

### Step 2: Interpret Results

- If there are **ERROR** findings: explain each error and how to fix it, then stop.
- If there are only **WARN** findings: summarize warnings and ask if they want to proceed.
- If clean: confirm validation passed.

### Step 3: Common Fixes

- Slug issues: rename directories to kebab-case (e.g. `websocket-notifications`)
- Missing contracts: create the required `*.json` next to the markdown artifact
- Plan too large: split to keep **≤3 tasks per plan**

### Step 4: Optional — Enforce Outside Claude (Git Hooks)

If user wants the same checks when committing outside Claude:

```bash
chmod +x .githooks/pre-commit .cnogo/hooks/install-githooks.sh
./.cnogo/hooks/install-githooks.sh
```

## Output

- Pass/fail summary
- List of errors/warnings (with paths)
- Next recommended action (`/plan`, `/implement`, `/review`, or `/ship`)

