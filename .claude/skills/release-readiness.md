---
name: release-readiness
tags: [release, quality]
appliesTo: [ship, close, spawn]
---
# Release Readiness

Pre-merge and release checklist.

## Release Checklist

- `/review` clean (or warnings accepted)
- `/verify-ci` results recorded (where applicable)
- Docs updated (README, API docs, code comments)
- Rollback plan noted
- Changelog impact noted

## Incident / Hotfix

- Stabilize first: rollback or feature flag
- Minimize blast radius
- Add a regression test
- Postmortem (RCA) after stabilization

## Docs Quality

- README and feature docs updated
- Examples are copy-pasteable
- State and next steps are clear
