# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- `/bug` command for routing bug work (quick vs debug vs discuss) with branch/test guidance
- `/brainstorm` command for ideation + narrowing (Q&A + options) before `/discuss`
- `/close` command for post-merge cleanup (close memory epic and optionally archive feature artifacts)
- `/research` command for deep research artifacts to de-risk decisions during `/discuss`
- `/validate` command to enforce workflow rules (slugs, contracts, plan size)
- `/verify-ci` command for non-interactive (CI-friendly) verification artifacts
- Machine-checkable workflow contracts (`*.json`) for feature context, plans, summaries, and reviews
- `.cnogo/scripts/workflow_validate.py` validator (no dependencies) and optional `.githooks/pre-commit` enforcement
- `/rollback` command for quick reverts (supports `last`, `<commit-hash>`, and `branch` modes)
- `/init` command to auto-populate templates based on stack detection
- `/mcp` command for Model Context Protocol integrations (GitHub, Jira, Sentry, Figma, etc.)
- `/background` command for fire-and-forget long-running tasks
- `/spawn` command for specialized subagents (security, tests, docs, perf, api, refactor)
- `PreToolUse` hooks for security validation before command execution
- Stack-specific CLAUDE.md templates for Java, TypeScript, Python, Go, and Rust
- Anthropic API key pattern (`sk-ant-*`) to secret scanning
- Azure storage key pattern to secret scanning
- GCP service account JSON detection to secret scanning
- `Bash(rm:*)` to allow list (dangerous patterns remain blocked)
- `docs/templates/` directory with opinionated stack defaults

### Changed

- Total commands increased from 15 to 28

### Fixed

- 

### Security

- Added `PreToolUse` hooks to block dangerous commands before execution
- Added `PreToolUse` hooks to require approval for reading sensitive files
- Enhanced secret scanning now covers 8 key patterns (AWS, Anthropic, OpenAI, GitHub, Slack, Azure, GCP, private keys)

### Deprecated

- 

### Removed

- 

---

## [1.0.0] - 2026-01-24

### Added

- Initial release of Universal Development Workflow Pack
- 15 slash commands for the full development lifecycle
- Parallel session coordination across multiple checkouts (Boris Cherny style)
- Secret scanning built into pre-commit hooks
- Stack auto-detection (Java, TypeScript, Python, Go, Rust)
- Enterprise templates (ADR, CODEOWNERS, PR template, release notes)
- SBOM generation support (CycloneDX)
- PostToolUse auto-formatting hooks
- PreCommit secret scanning and test running
- PostCommit confirmation

### Core Commands

- `/discuss` - Capture decisions before coding
- `/plan` - Create implementation tasks (≤3 per plan)
- `/implement` - Execute a plan with verification
- `/verify` - User acceptance testing
- `/review` - Quality gates (lint, test, security, SAST)
- `/ship` - Commit, push, create PR
- `/quick` - Small fixes without full ceremony
- `/tdd` - Test-driven development flow
- `/status` - Current position, blockers, next steps
- `/pause` - Create handoff for later resume
- `/resume` - Restore from paused session
- `/sync` - Coordinate across parallel sessions
- `/context` - Load relevant files for a feature
- `/debug` - Systematic debugging with state tracking
- `/changelog` - Generate changelog from git history
- `/release` - Create release with notes, tag, SBOM

---

[Unreleased]: https://github.com/owner/repo/compare/v1.0.0...HEAD
[1.0.0]: https://github.com/owner/repo/releases/tag/v1.0.0
