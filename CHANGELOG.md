# Changelog

All notable changes to `abap_wiki` are documented in this file. The format is
inspired by [Keep a Changelog](https://keepachangelog.com/en/1.1.0/); versions
follow [SemVer](https://semver.org/lang/en/).

## [1.0.0] - unreleased

First public release. The date will be set on publication day.

### Added

- **Engine (L0/L1)**: deterministic L0 inventory from a TADIR export
  (`init-db`, `import-tadir`, `resolve-sources`, `ingest-l0`, `enqueue-l1`,
  `ingest-metadata`); gated L1 code analysis with an independent adversarial
  judge, fail-closed promotion (no `--force`), idempotent apply, per-batch
  commits, deterministic include-edge derivation, and full loop recovery
  (`claim`, `submit-author`, `submit-verdict`, `apply`, `recover`, `project`,
  `reopen-l1`, `rerender-pages`, `link-includes`, `requeue-skipped`,
  `retry-reset`, `gc-runs`).
- **L2 functional process**: slice manifests with a mandatory real owner,
  gap discovery and multi-source auto-research, expert questionnaires with
  pre-filled hypotheses, answer capture, functional synthesis with line- and
  evidence-anchored claims, an independent fidelity gate, and gated promotion
  (`slice-init`, `slice-rederive`, `slice-show`, `slice-targets`,
  `submit-research`, `questionnaire`, `capture-answer`, `l2-progress`,
  `submit-functional`, `submit-process`, `submit-l2-verdict`, `apply-l2`).
- **State and views**: SQLite as the single source of truth; wiki pages,
  indexes, dashboard, membership, Excel export and the operation log are
  regenerated projections (`progress`, `dashboard`, `export-excel`, `log`,
  `log-op`, `token-metrics`, `spot-check`).
- **Quality guardrails**: encoding check (UTF-8, mojibake, banned typographic
  characters), mandatory three-part context headers on every engine code
  file, environment doctor with a fail-closed staged secret scan in the
  pre-commit hook, agent-contract synchronization check, wiki lint
  (frontmatter, wikilinks, citation resolution), and a 450+ case unit suite.
- **Agent contracts and skills** for Claude Code and Codex CLI: author,
  adversarial judge, functional researcher/author/gate agents; ingest, query,
  lint, slice and answer-capture skills; autonomous L1 loop documentation.
- **Demos and evidence**: a one-command, zero-token L0 demo on a bundled
  synthetic package; a token-saving example knowledge base with measured
  compression; and the committed model-comparison benchmark: the full
  L0→L1→L2 ingest of the 153k-line abapGit standalone program executed
  seven times across Claude author/judge pairings, with per-agent tokens,
  gate verdicts, retries, final pages, methodology and model recommendations.
- **Documentation**: architecture, pipeline, adversarial gate, L2 process,
  lessons learned, runbook, testing, autonomous loop, section semantics,
  first-clone SAP input guide, roadmap, agent runtime and cost, FAQ.
- **Community files**: README, CONTRIBUTING, SECURITY (private vulnerability
  reporting), CODE_OF_CONDUCT, issue and PR templates, dependabot, CI.
