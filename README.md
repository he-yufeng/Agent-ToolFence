<div align="center">

<img src="docs/banner.png" alt="agentcikit — CI-grade evidence for AI agents, MCP servers, and upstream contributions" width="100%">

[![PyPI](https://img.shields.io/pypi/v/agentcikit.svg)](https://pypi.org/project/agentcikit/)
[![Python](https://img.shields.io/pypi/pyversions/agentcikit.svg)](https://pypi.org/project/agentcikit/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Tests](https://github.com/he-yufeng/agentcikit/actions/workflows/ci.yml/badge.svg)](https://github.com/he-yufeng/agentcikit/actions)

[**Install**](#install) · [**mcp-gate**](#mcp-gate) · [**ci-repro**](#ci-repro) · [**tool-fence**](#tool-fence) · [中文](README_CN.md)

</div>

<p align="center"><img src="docs/demo.png" alt="agentci mcp-gate check" width="620"></p>

CI-grade evidence and safety tools for AI agents, MCP servers, and open-source contribution work.

When you ship code with AI agents, or maintain MCP servers, or send pull requests to upstream
projects, the hard part is rarely writing the change. It is proving the change is right: showing a
CI failure is a real regression and not noise, handing an agent the few files that actually matter,
keeping a broken MCP server out of `main`, turning a protocol bug into a transcript a maintainer can
read, and testing that an agent will not run a dangerous tool just because some untrusted text told
it to.

`agentcikit` bundles five small, focused command-line tools that each produce that kind of
evidence and fit cleanly into CI:

| Subcommand | What it does |
|---|---|
| `agentci ci-repro` | Turn GitHub Actions failure logs into a local repro plan and a PR evidence pack. |
| `agentci patch-context` | Build a small, explainable context pack of the files that matter for one issue, failing test, or patch. |
| `agentci mcp-gate` | A CI gate for MCP servers: handshake, list tools, check the tool contract, scan for leaked secrets. |
| `agentci mcp-replay` | Record and replay MCP JSON-RPC traffic as redacted, reviewable fixtures. |
| `agentci tool-fence` | Deterministic safety regression tests for agent tool calls, replayed from fixtures in CI. |

Each tool works on its own. Together they cover the loop of contributing to and operating
agent/MCP projects with reviewable evidence instead of screenshots and "works on my machine".

## Install

```bash
pip install agentcikit
```

This installs a single `agentci` command with five subcommands. Run `agentci --help` for the map,
or `agentci <subcommand> --help` for any tool.

## ci-repro

Turn a CI log into a categorized failure report and a PR comment draft. It is not a local runner
like `act` and not a linter like `actionlint`; it reads the logs you already have, finds the first
actionable failure, classifies it (regression, permission gate, network limit, dependency install,
local test failure), and extracts a likely local repro command.

```bash
gh run view 123456789 --repo owner/repo --log > run.log
agentci ci-repro plan run.log --out repro.md
agentci ci-repro comment run.log            # draft a PR comment from the first failure
```

## patch-context

Give a coding agent the files that matter for one narrow task. It reads issue text, stack traces,
failure logs, git diffs, file names, content terms, and light Python/JS/TS import links, then ranks
the files an agent should read first. Use Repomix for the whole repo and RepoWiki for durable docs;
use `patch-context` when the task is "fix this issue" or "debug this CI failure".

```bash
agentci patch-context scan --repo . --issue issue.md --top 12 > context.md
pytest -q 2>&1 | tee pytest.log
agentci patch-context from-failure --repo . pytest.log --format md
agentci patch-context from-diff --repo . --base main --format json
```

## mcp-gate

Stop shipping broken MCP servers. `mcp-gate` starts a stdio MCP server, runs the client handshake,
lists tools, checks the tool contract shape, scans observed metadata and stderr for obvious secret
leaks, and writes Markdown/JSON reports that fit into GitHub Actions. It exits non-zero when a
required check fails, so a pull request fails before a broken server lands.

```bash
agentci mcp-gate check \
  --command "python -m your_mcp_server" \
  --report mcp-gate-report.md \
  --json mcp-gate-report.json
```

Use `--fail-on-warn` if warnings should also fail CI.

## mcp-replay

Record and replay MCP JSON-RPC traffic as small JSONL fixtures. When an MCP server breaks, a
maintainer needs the message sequence, not a screenshot: which request was sent, which response came
back, whether ids matched, whether a token or local path leaked. `mcp-replay` captures that, redacts
secrets, and replays the same client messages against a server to compare response shape.

```bash
agentci mcp-replay record --command "python -m my_mcp_server" --out transcript.jsonl
agentci mcp-replay inspect transcript.jsonl --format md
agentci mcp-replay redact transcript.jsonl --out transcript.safe.jsonl
agentci mcp-replay replay transcript.safe.jsonl --command "python -m my_mcp_server"
```

## tool-fence

Put agent tool-call safety cases in your repository and run them in CI. It does not call a live
model. It replays transcript fixtures and checks whether an agent would call tools that should be
denied, confirmed first, or treated as high-risk after untrusted tool output. Real incidents usually
happen one step after the answer looks fine, when the agent reads an issue, web page, or tool result
and then calls a dangerous tool. `tool-fence` makes that boundary cheap to test.

```bash
agentci tool-fence init                 # write starter fixtures
agentci tool-fence run tests/toolfence --markdown
```

## GitHub Action

Drop the suite into a workflow with the bundled composite action. It runs one tool and posts the report as a sticky PR comment:

```yaml
- uses: he-yufeng/agentcikit@main
  with:
    tool: tool-fence                 # or mcp-gate / ci-repro
    args: run fixtures/ --output /tmp/results.json
```

```yaml
- uses: he-yufeng/agentcikit@main
  with:
    tool: mcp-gate
    args: node server.js
```

Inputs: `tool` (required), `args` (passed through), `package` (pip spec, default `agentcikit`), `python-version` (default `3.12`), `comment` (post the report, default `true`), `github-token`. The repo dogfoods it in `.github/workflows/agentci-action.yml`.

## Roadmap

The five tools are stable and tested; the work now is widening coverage and making the evidence easier to wire into a real pipeline:

- **A ready-made GitHub Action** — a single composite action that runs `mcp-gate` / `tool-fence` on a PR and posts the report as a comment, so adoption is a few lines of YAML instead of a hand-written workflow.
- **Streamable-HTTP MCP servers** — `mcp-gate` and `mcp-replay` speak stdio today; the HTTP transport is the obvious next surface as more servers ship that way.
- **Richer CI-log classifiers** — `ci-repro` recognises the common failure shapes (real regression, permission gate, network limit, dependency install, local test); the long tail (flaky-retry markers, OOM kills, cache corruption) is worth teaching it next.
- **A shared evidence bundle** — let the tools emit one combined, redacted artifact (CI repro + MCP transcript + tool-fence verdict) that a maintainer can read in one place.

Each tool stays usable on its own — the roadmap is about making the suite easier to drop into a pipeline, not adding surface for its own sake. Issues and ideas welcome.

## Related Projects

agentcikit pulls together a few of my agent-CI tools. The ones closest to it:

- **[CoreCoder](https://github.com/he-yufeng/CoreCoder)** — want to understand how a coding agent really works? Read the whole ~1k-line engine end to end, not a black box.
- **[RepoWiki](https://github.com/he-yufeng/RepoWiki)** — dropped into an unfamiliar codebase? It gives you a guided wiki and a where-to-start reading path, a self-hostable DeepWiki alternative.
- **[AgentProbe](https://github.com/he-yufeng/AgentProbe)** — catch when your LLM agent silently changes behavior: snapshot tests for agents, run in pytest.
- **[LiteBench](https://github.com/he-yufeng/LiteBench)** — benchmark any LLM in one command: HumanEval, GSM8K and MMLU built in, plus your own tasks.

## Development

```bash
git clone https://github.com/he-yufeng/agentcikit
cd agentcikit
pip install -e ".[dev]"
ruff check .
ruff format --check .
pytest
```

## License

MIT
