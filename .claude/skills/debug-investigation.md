---
name: debug-investigation
tags: [domain, debug]
appliesTo: [spawn]
---
# Debug Investigation

Systematic root cause analysis for errors and failures.

## Bug Triage

- **Impact**: severity, affected users, prod vs dev, data loss risk
- **Repro**: steps, frequency, environment, inputs
- **Signals**: logs, metrics, error tracking
- **Routing**: small fix → `/quick`, unclear cause → `/debug`, multi-service → `/discuss`

## Investigation Process

1. Reproduce locally (or document why not)
2. Identify the smallest failing scenario
3. Add instrumentation (temporary logs) if needed
4. Inspect recent changes (`git log -p`)
5. Form 2-3 hypotheses, test most likely first
6. Confirm root cause with evidence

## Common Patterns

- Off-by-one errors and boundary conditions
- Null/undefined references and type mismatches
- Race conditions and timing issues
- Configuration mismatches between environments
- Dependency version conflicts

## Root Cause Analysis

- Timeline (UTC), detection, mitigation, recovery
- Root cause (technical + contributing factors)
- Why it wasn't caught (tests, monitoring, process)
- Preventative actions (tests, alerts, guardrails)
