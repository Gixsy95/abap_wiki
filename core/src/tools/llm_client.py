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

import json
import time
import urllib.error
import urllib.request
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


def build_request(profile: LLMProfile, system: str, user: str) -> tuple[str, dict, dict]:
    """One (system, user) exchange -> (url, headers, json body) for the shape."""
    base = profile.base_url.rstrip("/")
    if profile.api_shape == "anthropic":
        return (
            base + "/v1/messages",
            {
                "content-type": "application/json",
                "x-api-key": profile.api_key,  # pragma: allowlist secret
                "anthropic-version": "2023-06-01",
            },
            {
                "model": profile.model,
                "max_tokens": profile.max_tokens,
                "system": system,
                "messages": [{"role": "user", "content": user}],
            },
        )
    return (
        base + "/chat/completions",
        {
            "content-type": "application/json",
            "authorization": f"Bearer {profile.api_key}",
        },
        {
            "model": profile.model,
            "max_tokens": profile.max_tokens,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
        },
    )


def parse_response(profile: LLMProfile, payload: dict) -> LLMResult:
    """Extracts (text, stop_reason, truncated) from the shape's response body."""
    if profile.api_shape == "anthropic":
        blocks = payload.get("content") or []
        text = "".join(b.get("text", "") for b in blocks if b.get("type") == "text")
        stop = str(payload.get("stop_reason") or "")
        return LLMResult(text=text, stop_reason=stop, truncated=stop == "max_tokens")
    choices = payload.get("choices") or [{}]
    message = choices[0].get("message") or {}
    finish = str(choices[0].get("finish_reason") or "")
    return LLMResult(
        text=str(message.get("content") or ""),
        stop_reason=finish,
        truncated=finish == "length",
    )


def strip_code_fences(text: str) -> str:
    """Removes a single outer ``` fence pair (models often add one despite the
    addendum). Unbalanced fences are left untouched: the schema validation
    downstream will reject them visibly instead of a silent edit here."""
    s = text.strip()
    if not s.startswith("```"):
        return s
    lines = s.splitlines()
    if len(lines) >= 2 and lines[-1].strip() == "```":
        return "\n".join(lines[1:-1]).strip()
    return s


def strip_frontmatter(text: str) -> str:
    """Drops the YAML frontmatter block (harness metadata: name/model/...) from
    a canonical contract, keeping the body used as the system prompt."""
    lines = text.splitlines()
    if not lines or lines[0].strip() != "---":
        return text
    for i in range(1, len(lines)):
        if lines[i].strip() == "---":
            return "\n".join(lines[i + 1 :]).lstrip("\n")
    return text


def _urllib_transport(url: str, headers: dict, body: dict, timeout: int) -> tuple[int, dict]:
    """Default transport: one POST, JSON in/out. HTTP error bodies are drained
    but never surfaced (they may echo the prompt, i.e. customer code)."""
    req = urllib.request.Request(
        url, data=json.dumps(body).encode("utf-8"), headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:  # noqa: S310
            return resp.status, json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as exc:
        exc.read()
        return exc.code, {}


def complete(
    profile: LLMProfile,
    system: str,
    user: str,
    *,
    transport=None,
    sleeper=time.sleep,
) -> str:
    """Single-shot completion with bounded retry (429/5xx/network, exponential
    backoff 1s/2s). Raises LLMError on exhaustion, non-retryable HTTP status,
    truncated or empty output. Error messages carry only profile name, HTTP
    status or exception class name: never the api key, prompt or response."""
    transport = transport or _urllib_transport
    url, headers, body = build_request(profile, system, user)
    last = "no attempt made"
    for attempt in range(1, MAX_ATTEMPTS + 1):
        status: int | None
        try:
            status, payload = transport(url, headers, body, profile.timeout_sec)
        # JSONDecodeError/UnicodeDecodeError: a 200 with a non-JSON or garbled body
        # (e.g. a proxy error page) must stay inside the bounded-retry, secret-safe
        # boundary.
        except (
            urllib.error.URLError,
            OSError,
            TimeoutError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as exc:
            status, payload = None, {}
            last = f"network error: {exc.__class__.__name__}"
        if status == 200:
            result = parse_response(profile, payload)
            if result.truncated:
                raise LLMError(
                    f"{profile.name}: completion truncated "
                    f"(stop_reason={result.stop_reason}); raise max_tokens"
                )
            if not result.text.strip():
                raise LLMError(f"{profile.name}: empty completion from the endpoint")
            return result.text
        if status is not None:
            last = f"HTTP {status}"
            if status not in RETRY_STATUS:
                break
        if attempt < MAX_ATTEMPTS:
            sleeper(2 ** (attempt - 1))
    raise LLMError(f"{profile.name}: LLM call failed after {MAX_ATTEMPTS} attempt(s): {last}")
