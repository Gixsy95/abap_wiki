# Security policy

## Supported versions

The latest state of `main` is the only supported version. There are no
backported fixes.

## Reporting a vulnerability

Please report vulnerabilities **privately**: do not open a public issue.

- **Email:** [gixsy95github@gmail.com](mailto:gixsy95github@gmail.com)
- **GitHub:** private vulnerability reporting on this repository
  ("Report a vulnerability" under the Security tab), if enabled.

You will get an acknowledgement within a few days. Please allow up to 90 days
of coordinated disclosure before publishing details; most fixes should land
much faster.

## Scope

abap_wiki is a **local-only** tool: no network services, no telemetry, no
credentials handled by the engine itself. The interesting vulnerability
classes are the ones that could betray those guarantees:

- **Secret-scan bypasses**: content that defeats `doctor.py --secret-scan`
  or the staged scan in `gitops.commit_batch` (patterns, allowlist tiers,
  the `pragma: allowlist secret` escape hatch);
- **Path traversal**: slugs or artifact paths escaping the repository root
  (`render.py` `PathContainmentError`, `_safe_repo_path` guards);
- **Unsafe deserialization**: anything that would require more than
  `yaml.safe_load`/`safe_dump` or that sneaks `eval`/`exec`/`pickle` into the
  engine;
- **Data exfiltration into tracked files**: any path by which content of the
  immutable `raw/` inbox (real SAP exports) could end up staged or committed
  against the guards.

Reports that come with a failing test are the fastest to fix: see
[CONTRIBUTING.md](CONTRIBUTING.md).
