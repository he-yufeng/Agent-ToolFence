# Changelog

## 0.2.0 (unreleased)

- `agentci mcp-gate check` accepts `--url` with repeatable `--header` next to `--command`, so remote MCP servers are gated over streamable HTTP. URL query strings are stripped from reports, and both the old and new `mcp` client spellings are supported.
- Composite GitHub Action (`action.yml`) runs `mcp-gate`, `tool-fence`, or `ci-repro` on a pull request and posts the report as a sticky comment. Dogfooded in `.github/workflows/agentci-action.yml`.
- `ci-repro` classifies two more failure shapes: cache corruption and flaky retry, both routed to rerun advice instead of a local repro.
