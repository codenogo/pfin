# MCP: $ARGUMENTS
<!-- effort: medium -->

Manage Model Context Protocol server connections.

## Arguments

`/mcp` or `/mcp list`  
`/mcp add <server>`  
`/mcp remove <server>`  
`/mcp status`

## Your Task

1. Parse action from `$ARGUMENTS`.

2. `list` (default):
```bash
claude mcp list
```
If none configured, say so and show supported server names.

3. `add <server>`:
- Validate server name.
- Provide exact required env vars, then run:
```bash
claude mcp add <server>
```
- Confirm success or print actionable failure.

4. `remove <server>`:
```bash
claude mcp remove <server>
```

5. `status`:
- List configured servers.
- Test each connection (`claude mcp test <server>` when available); return pass/fail per server.

## Common Servers and Credentials

- `github`: `GITHUB_TOKEN`
- `postgres`: `DATABASE_URL`
- `jira`: `JIRA_URL`, `JIRA_TOKEN`
- `sentry`: `SENTRY_AUTH_TOKEN`
- `figma`: `FIGMA_TOKEN`
- `notion`: `NOTION_API_KEY`
- `linear`: `LINEAR_API_KEY`
- `slack`: `SLACK_BOT_TOKEN`

## Output

- Current configured servers
- Setup/removal result
- Health status summary with failing servers highlighted
