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

import llm_client  # noqa: E402
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
