# Changelog
<!-- effort: low -->

Generate/update `CHANGELOG.md` from commit history.

## Arguments

`/changelog`  
`/changelog <from>..<to>`  
`/changelog --full`

## Your Task

1. Determine range:
- default: last tag to `HEAD`
- explicit range: use provided range
- `--full`: full history

2. Collect commits:
```bash
git log <range> --pretty=format:"%h|%s|%b" --no-merges
```

3. Categorize using conventional prefixes:
- `feat` -> Added
- `fix` -> Fixed
- `refactor`/`perf` -> Changed
- `docs` -> Documentation
- `security` -> Security
- `deprecate` -> Deprecated
- `remove` -> Removed
- `BREAKING CHANGE` -> Breaking Changes
Skip internal-only noise (`test`, `chore`) unless user asks for full detail.

4. Build a Keep-a-Changelog entry under `[Unreleased]` (or version block if requested).

5. Preview before write, then update `CHANGELOG.md`.

6. If repository has compare/release links, update link refs at bottom.

## Output

- Range used
- Category summary counts
- Preview snippet
- Confirmation that `CHANGELOG.md` was updated
