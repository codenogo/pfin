# cnogo Workflow

Workflow engine documentation. Claude reads this automatically alongside your project's CLAUDE.md.

## Operating Principles

Apply these on every non-trivial task.

1. **Think Before Coding** — surface confusion and tradeoffs; ask when ambiguous
2. **Simplicity First** — minimum code that solves the problem; no speculative abstractions
3. **Surgical Changes** — touch only what's needed; don't refactor unrelated areas
4. **Goal-Driven Execution** — define success criteria; verify with commands/tests; loop until proven
5. **TDD Is Core** — treat test-first as default behavior for code changes; `/tdd` is the deep, explicit workflow
6. **Verification Before Completion** — no success claims without fresh command evidence
7. **Prefer Shared Utility Packages Over Hand-Rolled Helpers** — reuse shared helpers/packages before adding new utility implementations
8. **Don't Probe Data YOLO-Style** — avoid guess-and-check reads; use explicit schemas/contracts
9. **Validate Boundaries** — validate input/output at API, DB, filesystem, and network boundaries
10. **Typed SDKs** — prefer official typed SDKs/clients over ad-hoc HTTP calls when available

## Memory Engine

Structured task tracking (initialized at install via `install.sh`, or manually via `python3 .cnogo/scripts/workflow_memory.py init`):

```bash
# CLI access
python3 .cnogo/scripts/workflow_memory.py ready          # Show unblocked tasks
python3 .cnogo/scripts/workflow_memory.py prime           # Token-efficient context summary
python3 .cnogo/scripts/workflow_memory.py stats           # Aggregate statistics
python3 .cnogo/scripts/workflow_memory.py create "title"  # Create an issue
python3 .cnogo/scripts/workflow_memory.py show <id>       # Show issue details
python3 .cnogo/scripts/workflow_memory.py session-reconcile  # Fix orphaned issues after compaction
python3 .cnogo/scripts/workflow_checks.py discover --since-days 30  # Missed token-savings report
```

```python
# Python API access (from commands/scripts)
import sys; sys.path.insert(0, '.cnogo')
from scripts.memory import is_initialized, create, ready, claim, close, prime
```

Key files:
- `.cnogo/scripts/memory/` — Python package (stdlib only)
- `.cnogo/memory.db` — SQLite runtime (gitignored)
- `.cnogo/issues.jsonl` — Git-tracked sync format

### Phase Transitions

Feature phases: `discuss` → `plan` → `implement` → `review` → `ship` (forward-only, advisory).
`/shape` is a persistent initiative workspace that lives before feature memory phases begin and can remain active while features branch into `discuss`.
Use `phase-get`/`phase-set` commands once work enters `discuss`. Backward transitions emit stderr warnings but do not block.

## Planning Docs

- Current state: memory engine (`prime()` for context summary)
- Project vision: `docs/planning/PROJECT.md`
- Roadmap: `docs/planning/ROADMAP.md`
- Initiative shaping: `docs/planning/work/ideas/`
- Feature work: `docs/planning/work/features/`
- Quick tasks: `docs/planning/work/quick/`
- Research: `docs/planning/work/research/`

## Skills Library

Reusable domain expertise, lazy-loaded by commands:
- `.claude/skills/` — code review, security scanning, performance analysis, API review, test writing, debug investigation, refactor safety, release readiness
- workflow skills: contract integrity, worktree merge recovery, memory sync reconciliation, changed-scope verification, artifact token budgeting, boundary/SDK enforcement, feature lifecycle closure

## Security

- Never commit: secrets, keys, credentials, `.env` files
- PreToolUse hooks block dangerous commands, scan commit input for secrets, and log token-optimization hints
- Always validate user input at system boundaries
