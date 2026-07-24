<div align="center">

<img src="docs/banner.png" alt="agentcikit — 面向 AI agent、MCP 服务器和开源贡献的 CI 级证据工具集" width="100%">

[![PyPI](https://img.shields.io/pypi/v/agentcikit.svg)](https://pypi.org/project/agentcikit/)
[![Python](https://img.shields.io/pypi/pyversions/agentcikit.svg)](https://pypi.org/project/agentcikit/)
[![License: MIT](https://img.shields.io/badge/License-MIT-blue.svg)](LICENSE)
[![Tests](https://github.com/he-yufeng/agentcikit/actions/workflows/ci.yml/badge.svg)](https://github.com/he-yufeng/agentcikit/actions)

[**安装**](#安装) · [**mcp-gate**](#mcp-gate) · [**ci-repro**](#ci-repro) · [**tool-fence**](#tool-fence) · [English](README.md)

</div>

<p align="center"><img src="docs/demo.png" alt="agentci mcp-gate check" width="620"></p>

面向 AI agent、MCP 服务器和开源贡献工作的「CI 级证据与安全」工具集。

用 AI agent 写代码、维护 MCP 服务器、给上游项目提 PR 时，难的往往不是写出改动，而是**证明改动是对的**：说明一条 CI 失败是真回归而不是噪声、把真正相关的几个文件喂给 agent、把坏掉的 MCP 服务器挡在 `main` 之外、把协议 bug 变成维护者能直接读的 transcript、以及测试 agent 不会因为某段不可信文本就去调危险工具。

`agentcikit` 把五个小而专注的命令行工具打包到一起，每个都产出这类证据、都能干净地接进 CI：

| 子命令 | 作用 |
|---|---|
| `agentci ci-repro` | 把 GitHub Actions 失败日志变成本地复现计划 + PR 证据包。 |
| `agentci patch-context` | 针对一个 issue / 失败测试 / 补丁，构建小而可解释的「该读哪些文件」上下文包。 |
| `agentci mcp-gate` | MCP 服务器的 CI 门禁：握手、列工具、校验工具契约、扫描泄露的密钥。 |
| `agentci mcp-replay` | 把 MCP JSON-RPC 流量录制 / 回放成脱敏、可评审的 fixture。 |
| `agentci tool-fence` | agent 工具调用的确定性安全回归测试，在 CI 里用 fixture 回放。 |

每个工具都能单独用。合起来，它们覆盖了「以可评审证据、而不是截图和『我这边能跑』」来贡献和运维 agent/MCP 项目的整个回路。

## 安装

```bash
pip install agentcikit
```

装好后是一个 `agentci` 命令带五个子命令。`agentci --help` 看总览，`agentci <子命令> --help` 看单个工具。

## ci-repro

把 CI 日志变成分类后的失败报告 + PR 评论草稿。它不是 `act` 那种本地 runner，也不是 `actionlint` 那种 linter；它读你已经有的日志，找到第一条可处理的失败，分类（真回归 / 权限门 / 网络限制 / 依赖安装 / 本地测试失败），并提取一条可能的本地复现命令。

```bash
gh run view 123456789 --repo owner/repo --log > run.log
agentci ci-repro plan run.log --out repro.md
agentci ci-repro comment run.log            # 从第一条失败生成 PR 评论草稿
```

## patch-context

把一个窄任务真正相关的文件喂给 coding agent。它读 issue 文本、堆栈、失败日志、git diff、文件名、内容词，以及轻量的 Python/JS/TS 导入关系，排出 agent 应该先读的文件。整库交接用 Repomix，长期文档用 RepoWiki；任务是「修这个 issue」或「调这个 CI 失败」时用 `patch-context`。

```bash
agentci patch-context scan --repo . --issue issue.md --top 12 > context.md
pytest -q 2>&1 | tee pytest.log
agentci patch-context from-failure --repo . pytest.log --format md
agentci patch-context from-diff --repo . --base main --format json
```

## mcp-gate

别再把坏掉的 MCP 服务器发出去。`mcp-gate` 启动一个 stdio MCP 服务器，跑客户端握手、列工具、校验工具契约形状、扫描可见的元数据和 stderr 里有没有泄露密钥，并写出能接进 GitHub Actions 的 Markdown/JSON 报告。必需检查不过时返回非零退出码，于是 PR 会在坏服务器落地前先失败。

```bash
agentci mcp-gate check \
  --command "python -m your_mcp_server" \
  --report mcp-gate-report.md \
  --json mcp-gate-report.json
```

需要警告也让 CI 失败时加 `--fail-on-warn`。

## mcp-replay

把 MCP JSON-RPC 流量录制 / 回放成小的 JSONL fixture。MCP 服务器坏了时，维护者需要的是消息序列而不是截图：发了哪个请求、回了哪个响应、id 对不对得上、有没有 token 或本地路径泄露。`mcp-replay` 把这些抓下来、脱敏，再用同样的客户端消息回放到服务器上比对响应形状。

```bash
agentci mcp-replay record --command "python -m my_mcp_server" --out transcript.jsonl
agentci mcp-replay inspect transcript.jsonl --format md
agentci mcp-replay redact transcript.jsonl --out transcript.safe.jsonl
agentci mcp-replay replay transcript.safe.jsonl --command "python -m my_mcp_server"
```

## tool-fence

把 agent 工具调用的安全用例放进仓库、在 CI 里跑。它不调用真实模型，而是回放 transcript fixture，检查 agent 会不会调用那些本该被拒绝、本该先确认、或在读到不可信工具输出后该被当作高风险的工具。真实事故往往发生在「答案看起来没问题」之后那一步：agent 读了一个 issue、网页或工具结果，然后调用了危险工具。`tool-fence` 让这条边界测起来很便宜。

```bash
agentci tool-fence init                 # 写出起步 fixture
agentci tool-fence run tests/toolfence --markdown
```

## GitHub Action

仓库自带一个 composite action，一行就能把整套工具接进 workflow：选一个工具跑起来，报告自动贴在 PR 评论里（重复跑会更新同一条）。

```yaml
- uses: he-yufeng/agentcikit@main
  with:
    tool: tool-fence                 # 或 mcp-gate / ci-repro
    args: run fixtures/ --output /tmp/results.json
```

```yaml
- uses: he-yufeng/agentcikit@main
  with:
    tool: mcp-gate
    args: node server.js
```

输入项：`tool`（必填）、`args`（原样透传）、`package`（pip 安装规格，默认 `agentcikit`）、`python-version`（默认 `3.12`）、`comment`（是否贴报告，默认 `true`）、`github-token`。本仓库在 `.github/workflows/agentci-action.yml` 里自用验证。

## 后续规划

五个工具本身已经稳定、有测试覆盖，接下来的重点是扩大覆盖面、让产出的证据更容易接进真实流水线：

- **开箱即用的 GitHub Action**：一个 composite action，在 PR 上跑 `mcp-gate` / `tool-fence` 并把报告贴成评论，接入只需几行 YAML，而不是手写整套 workflow。
- **支持 Streamable-HTTP 的 MCP 服务器**：`mcp-gate` 和 `mcp-replay` 目前走 stdio，随着越来越多服务器改用 HTTP 传输，这是最该补的下一块。
- **更丰富的 CI 日志分类器**：`ci-repro` 已经能识别常见失败形态（真回归、权限门、网络限制、依赖安装、本地测试失败），接下来值得教它认长尾情况（flaky 重试标记、OOM 被杀、缓存损坏）。
- **统一的证据包**：让这几个工具能输出一份合并、脱敏后的产物（CI 复现 + MCP transcript + tool-fence 结论），维护者在一个地方就能读完。

每个工具仍然可以单独用，这份规划是为了让整套工具更好地嵌进流水线，而不是为加功能而加功能。欢迎提 issue 和想法。

## 相关项目

agentcikit 把我几个 agent-CI 小工具整合到了一起，下面是跟它最接近的几个：

- **[CoreCoder](https://github.com/he-yufeng/CoreCoder)** — 想搞懂一个 coding agent 到底怎么运作？把整套约 1000 行引擎从头读到尾，而不是当黑箱。
- **[RepoWiki](https://github.com/he-yufeng/RepoWiki)** — 被丢进一个陌生代码库？它给你一份带「从哪读起」路径的 wiki，一个可自托管的 DeepWiki 替代。
- **[AgentProbe](https://github.com/he-yufeng/AgentProbe)** — 抓住 LLM agent 行为悄悄变样的那一刻：给 agent 做快照测试，跑在 pytest 里。
- **[LiteBench](https://github.com/he-yufeng/LiteBench)** — 一条命令给任意 LLM 跑基准：内置 HumanEval、GSM8K、MMLU，也能加你自己的任务。

## 开发

```bash
git clone https://github.com/he-yufeng/agentcikit
cd agentcikit
pip install -e ".[dev]"
ruff check .
ruff format --check .
pytest
```

## 许可证

MIT
