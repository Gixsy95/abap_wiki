"""HTTP client for the headless L1 runner: LLM profiles + wire adapters.

What it does: loads and validates the author/judge LLM profiles
(llm-profiles.yaml, api keys resolved from environment variables only) and
performs single-shot chat completions against Anthropic-Messages- or
OpenAI-chat-completions-shaped endpoints via stdlib urllib (no new deps).
How it works: load_profiles parses the YAML and returns (author, judge,
warnings), failing fast with ProfileError on hard errors; build_request /
parse_response translate one (system, user) exchange to/from each wire shape;
complete() adds bounded retry with exponential backoff on 429/5xx/network
errors and fails on truncated or empty output; strip_code_fences /
strip_frontmatter are deterministic text helpers. Pure functions plus an
injectable transport/sleeper: unit-testable without network. Error messages
and reprs never carry api keys or prompt/response bodies (customer code).
Connections: imported by headless_l1 (orchestrator); user config documented
in llm-profiles.yaml.example. Doc: core/docs/15-headless-l1-runner.md.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

import yaml

API_SHAPES = ("anthropic", "openai")
DEFAULT_MAX_TOKENS = 16000
DEFAULT_TIMEOUT_SEC = 600
RETRY_STATUS = {429, 500, 502, 503, 504}
MAX_ATTEMPTS = 3


class ProfileError(ValueError):
    """Hard configuration error: the runner must not start."""


class LLMError(RuntimeError):
    """LLM call failure (network, HTTP, truncated/empty output). Message is
    safe to log: never carries the api key nor prompt/response bodies."""


@dataclass(frozen=True)
class LLMProfile:
    name: str
    api_shape: str
    base_url: str
    model: str
    api_key_env: str
    api_key: str = field(repr=False, default="")
    max_tokens: int = DEFAULT_MAX_TOKENS
    timeout_sec: int = DEFAULT_TIMEOUT_SEC


@dataclass(frozen=True)
class LLMResult:
    text: str
    stop_reason: str
    truncated: bool


def _build_profile(name: str, raw: dict, env: Mapping[str, str]) -> LLMProfile:
    if not isinstance(raw, dict):
        raise ProfileError(f"profile '{name}' must be a mapping")
    shape = str(raw.get("api_shape") or "").strip()
    if shape not in API_SHAPES:
        raise ProfileError(f"{name}: api_shape must be one of {API_SHAPES}, got {shape!r}")
    base_url = str(raw.get("base_url") or "").strip()
    model = str(raw.get("model") or "").strip()
    key_env = str(raw.get("api_key_env") or "").strip()
    if not base_url or not model or not key_env:
        raise ProfileError(f"{name}: base_url, model and api_key_env are all required")
    api_key = str(env.get(key_env) or "").strip()
    if not api_key:
        raise ProfileError(
            f"{name}: environment variable {key_env} is not set "
            "(api keys live only in the environment, never in the file)"
        )
    return LLMProfile(
        name=name,
        api_shape=shape,
        base_url=base_url,
        model=model,
        api_key_env=key_env,
        api_key=api_key,
        max_tokens=int(raw.get("max_tokens") or DEFAULT_MAX_TOKENS),
        timeout_sec=int(raw.get("timeout_sec") or DEFAULT_TIMEOUT_SEC),
    )


def load_profiles(path: Path, env: Mapping[str, str]) -> tuple[LLMProfile, LLMProfile, list[str]]:
    """Loads the author+judge profiles. Raises ProfileError on hard errors;
    a same-model pair is accepted with a warning (recommended, not mandatory:
    context separation is guaranteed by the two independent HTTP calls)."""
    if not path.exists():
        raise ProfileError(
            f"profiles file not found: {path} "
            "(copy llm-profiles.yaml.example to llm-profiles.yaml and fill it in)"
        )
    data = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    if not isinstance(data, dict) or "author" not in data or "judge" not in data:
        raise ProfileError(f"{path.name}: expected top-level 'author' and 'judge' mappings")
    author = _build_profile("author", data["author"], env)
    judge = _build_profile("judge", data["judge"], env)
    warnings: list[str] = []
    if author.model == judge.model:
        warnings.append(
            "author and judge use the same model: a different judge model is "
            "recommended for the adversarial gate (context separation still "
            "holds via independent calls)"
        )
    return author, judge, warnings
