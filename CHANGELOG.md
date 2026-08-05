# Changelog

## 0.2.1

- Declare `httpx` as a direct dependency: `mcp` 2.0 moved to `httpx2`, so fresh installs lost the transitive `httpx` and the CLI died at import with `ModuleNotFoundError`.

## 0.2.0

- `agentci mcp-gate check` accepts `--url` with repeatable `--header` next to `--command`, so remote MCP servers are gated over streamable HTTP. URL query strings are stripped from reports, and both the old and new `mcp` client spellings are supported.
- Composite GitHub Action (`action.yml`) runs `mcp-gate`, `tool-fence`, or `ci-repro` on a pull request and posts the report as a sticky comment. Dogfooded in `.github/workflows/agentci-action.yml`.
- `ci-repro` classifies two more failure shapes: cache corruption and flaky retry, both routed to rerun advice instead of a local repro.
- `ci-repro compare` diffs two CI runs and splits failures into new, fixed, and still-failing, for regression review.
