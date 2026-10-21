from debugmas.config import (
    ExperimentConfig,
    Settings,
    parse_overrides,
    resolve_llm,
    resolved_config_dict,
)


def test_run_hash_depends_on_model_not_prices():
    cfg = ExperimentConfig()
    a = resolve_llm(cfg, Settings(model="m1", price_input_per_1m=0))
    b = resolve_llm(cfg, Settings(model="m2", price_input_per_1m=0))
    c = resolve_llm(cfg, Settings(model="m1", price_input_per_1m=5))
    d = resolve_llm(cfg, Settings(model="m1", openai_base_url="http://other/v1"))
    assert cfg.short_hash(a) != cfg.short_hash(b)
    assert cfg.short_hash(a) != cfg.short_hash(d)
    assert cfg.short_hash(a) == cfg.short_hash(c)


def test_overrides_parsed_as_yaml():
    assert parse_overrides(["max_attempts=2", "llm.reasoning={enabled: false}"]) == {
        "max_attempts": 2,
        "llm": {"reasoning": {"enabled": False}},
    }


def test_selected_profile_replaces_default_env_file(tmp_path, monkeypatch):
    selected = tmp_path / ".env.selected"
    selected.write_text(
        "OPENAI_BASE_URL=http://localhost:1234/v1\n"
        "OPENAI_API_KEY=private-test-value\n"
        "MODEL=local-test\n"
        "PRICE_INPUT_PER_1M=0\n"
        "PRICE_OUTPUT_PER_1M=0\n",
        encoding="utf-8",
    )
    for name in (
        "OPENAI_BASE_URL",
        "OPENAI_API_KEY",
        "MODEL",
        "PRICE_INPUT_PER_1M",
        "PRICE_OUTPUT_PER_1M",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("DEBUGMAS_ENV_FILE", str(selected))
    settings = Settings()
    assert settings.openai_base_url == "http://localhost:1234/v1"
    assert settings.model == "local-test"
    assert settings.openai_api_key == "private-test-value"
    assert "private-test-value" not in str(resolved_config_dict(ExperimentConfig(), settings))
