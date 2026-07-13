"""Unit tests for llm_client (headless L1 runner HTTP client).

What it does: validates profile loading (env-only api keys, same-model warning,
hard errors), the two wire adapters (Anthropic Messages / OpenAI chat-completions),
the deterministic text helpers (code-fence strip, frontmatter strip), and
complete() retry/truncation/secret-safety - all without network (fake transport).
How it works: builds profiles from tmp_path YAML files + plain dict env; fake
transports return canned (status, payload) tuples and record calls; a recording
sleeper asserts the backoff sequence.
Connections: exercises core/src/tools/llm_client.py; no fixture dependencies
beyond tmp_path (block_network guards against accidental real HTTP).
"""

import json

import llm_client
import pytest


def _write_profiles(tmp_path, author_model="model-a", judge_model="model-b"):
    p = tmp_path / "llm-profiles.yaml"
    p.write_text(
        f"""author:
  api_shape: anthropic
  base_url: https://api.example.test
  model: {author_model}
  api_key_env: TEST_AUTHOR_KEY
  max_tokens: 1234
judge:
  api_shape: openai
  base_url: http://127.0.0.1:9/v1
  model: {judge_model}
  api_key_env: TEST_JUDGE_KEY
""",
        encoding="utf-8",
    )
    return p


ENV = {"TEST_AUTHOR_KEY": "sk-author-secret", "TEST_JUDGE_KEY": "sk-judge-secret"}


def test_load_profiles_ok(tmp_path):
    author, judge, warnings = llm_client.load_profiles(_write_profiles(tmp_path), ENV)
    assert author.name == "author" and author.api_shape == "anthropic"
    assert author.api_key == "sk-author-secret" and author.max_tokens == 1234
    assert judge.name == "judge" and judge.api_shape == "openai"
    assert judge.max_tokens == llm_client.DEFAULT_MAX_TOKENS
    assert warnings == []


def test_load_profiles_same_model_warns_but_accepts(tmp_path):
    path = _write_profiles(tmp_path, author_model="same", judge_model="same")
    author, judge, warnings = llm_client.load_profiles(path, ENV)
    assert author.model == judge.model == "same"
    assert len(warnings) == 1 and "same model" in warnings[0]


def test_load_profiles_missing_file_points_to_example(tmp_path):
    with pytest.raises(llm_client.ProfileError) as exc:
        llm_client.load_profiles(tmp_path / "nope.yaml", ENV)
    assert "llm-profiles.yaml.example" in str(exc.value)


def test_load_profiles_missing_env_var_raises(tmp_path):
    with pytest.raises(llm_client.ProfileError) as exc:
        llm_client.load_profiles(_write_profiles(tmp_path), {"TEST_AUTHOR_KEY": "x"})
    assert "TEST_JUDGE_KEY" in str(exc.value)


def test_load_profiles_bad_shape_raises(tmp_path):
    p = tmp_path / "llm-profiles.yaml"
    p.write_text(
        "author:\n  api_shape: grpc\n  base_url: x\n  model: m\n  api_key_env: TEST_AUTHOR_KEY\n"
        "judge:\n  api_shape: openai\n  base_url: x\n  model: m2\n  api_key_env: TEST_JUDGE_KEY\n",
        encoding="utf-8",
    )
    with pytest.raises(llm_client.ProfileError) as exc:
        llm_client.load_profiles(p, ENV)
    assert "api_shape" in str(exc.value)


def test_profile_repr_never_leaks_the_key(tmp_path):
    author, judge, _ = llm_client.load_profiles(_write_profiles(tmp_path), ENV)
    assert "sk-author-secret" not in repr(author) + str(author)
    assert "sk-judge-secret" not in repr(judge) + str(judge)


def _author_profile(tmp_path):
    return llm_client.load_profiles(_write_profiles(tmp_path), ENV)[0]


def _judge_profile(tmp_path):
    return llm_client.load_profiles(_write_profiles(tmp_path), ENV)[1]


def test_build_request_anthropic(tmp_path):
    url, headers, body = llm_client.build_request(_author_profile(tmp_path), "SYS", "USER")
    assert url == "https://api.example.test/v1/messages"
    assert headers["x-api-key"] == "sk-author-secret"
    assert headers["anthropic-version"] == "2023-06-01"
    assert body == {
        "model": "model-a",
        "max_tokens": 1234,
        "system": "SYS",
        "messages": [{"role": "user", "content": "USER"}],
    }


def test_build_request_openai(tmp_path):
    url, headers, body = llm_client.build_request(_judge_profile(tmp_path), "SYS", "USER")
    assert url == "http://127.0.0.1:9/v1/chat/completions"
    assert headers["authorization"] == "Bearer sk-judge-secret"
    assert body["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USER"},
    ]


def test_parse_response_anthropic(tmp_path):
    res = llm_client.parse_response(
        _author_profile(tmp_path),
        {"content": [{"type": "text", "text": "hello"}], "stop_reason": "end_turn"},
    )
    assert res.text == "hello" and res.truncated is False


def test_parse_response_anthropic_truncated(tmp_path):
    res = llm_client.parse_response(
        _author_profile(tmp_path),
        {"content": [{"type": "text", "text": "cut"}], "stop_reason": "max_tokens"},
    )
    assert res.truncated is True


def test_parse_response_openai(tmp_path):
    res = llm_client.parse_response(
        _judge_profile(tmp_path),
        {"choices": [{"message": {"content": "hi"}, "finish_reason": "stop"}]},
    )
    assert res.text == "hi" and res.truncated is False


def test_parse_response_openai_truncated(tmp_path):
    res = llm_client.parse_response(
        _judge_profile(tmp_path),
        {"choices": [{"message": {"content": "cut"}, "finish_reason": "length"}]},
    )
    assert res.truncated is True


def test_strip_code_fences_variants():
    assert llm_client.strip_code_fences("plain: 1") == "plain: 1"
    assert llm_client.strip_code_fences("```yaml\nkey: v\n```") == "key: v"
    assert llm_client.strip_code_fences('```json\n{"a": 1}\n```') == '{"a": 1}'
    assert llm_client.strip_code_fences("  ```\nx\n```  ") == "x"
    # unbalanced fence: leave untouched (fail visible downstream, not silent edit)
    assert llm_client.strip_code_fences("```yaml\nkey: v").startswith("```")


def test_strip_frontmatter():
    text = "---\nname: x\nmodel: y\n---\n\n# Body\nrest"
    assert llm_client.strip_frontmatter(text) == "# Body\nrest"
    assert llm_client.strip_frontmatter("# No fm\nbody") == "# No fm\nbody"


def test_complete_retries_on_429_with_backoff(tmp_path):
    profile = _author_profile(tmp_path)
    calls, sleeps = [], []
    responses = [
        (429, {}),
        (503, {}),
        (200, {"content": [{"type": "text", "text": "done"}], "stop_reason": "end_turn"}),
    ]

    def transport(url, headers, body, timeout):
        calls.append(url)
        return responses[len(calls) - 1]

    out = llm_client.complete(profile, "S", "U", transport=transport, sleeper=sleeps.append)
    assert out == "done"
    assert len(calls) == 3 and sleeps == [1, 2]


def test_complete_gives_up_after_max_attempts(tmp_path):
    profile = _author_profile(tmp_path)

    def transport(url, headers, body, timeout):
        return 503, {}

    with pytest.raises(llm_client.LLMError) as exc:
        llm_client.complete(profile, "S", "U", transport=transport, sleeper=lambda s: None)
    assert "HTTP 503" in str(exc.value)
    assert "sk-author-secret" not in str(exc.value)


def test_complete_does_not_retry_client_errors(tmp_path):
    profile = _author_profile(tmp_path)
    calls = []

    def transport(url, headers, body, timeout):
        calls.append(1)
        return 401, {}

    with pytest.raises(llm_client.LLMError):
        llm_client.complete(profile, "S", "U", transport=transport, sleeper=lambda s: None)
    assert len(calls) == 1


def test_complete_truncated_output_raises(tmp_path):
    profile = _author_profile(tmp_path)

    def transport(url, headers, body, timeout):
        return 200, {"content": [{"type": "text", "text": "cut"}], "stop_reason": "max_tokens"}

    with pytest.raises(llm_client.LLMError) as exc:
        llm_client.complete(profile, "S", "U", transport=transport, sleeper=lambda s: None)
    assert "truncated" in str(exc.value)


def test_complete_network_error_is_retried_and_safe(tmp_path):
    import urllib.error

    profile = _author_profile(tmp_path)
    calls = []

    def transport(url, headers, body, timeout):
        calls.append(1)
        raise urllib.error.URLError("boom sk-author-secret")

    with pytest.raises(llm_client.LLMError) as exc:
        llm_client.complete(profile, "S", "U", transport=transport, sleeper=lambda s: None)
    assert len(calls) == llm_client.MAX_ATTEMPTS
    assert "sk-author-secret" not in str(exc.value)  # only the exception CLASS is reported


def test_complete_empty_completion_raises(tmp_path):
    profile = _author_profile(tmp_path)

    def transport(url, headers, body, timeout):
        return 200, {"content": [], "stop_reason": "end_turn"}

    with pytest.raises(llm_client.LLMError) as exc:
        llm_client.complete(profile, "S", "U", transport=transport, sleeper=lambda s: None)
    assert "empty" in str(exc.value)


def test_complete_malformed_200_body_is_retried_and_safe(tmp_path):
    profile = _author_profile(tmp_path)
    calls = []

    def transport(url, headers, body, timeout):
        calls.append(1)
        raise json.JSONDecodeError("Expecting value", "sk-author-secret-body", 0)

    with pytest.raises(llm_client.LLMError) as exc:
        llm_client.complete(profile, "S", "U", transport=transport, sleeper=lambda s: None)
    assert len(calls) == llm_client.MAX_ATTEMPTS
    assert "JSONDecodeError" in str(exc.value)
    assert "sk-author-secret-body" not in str(exc.value)
