from debugmas.config import ExperimentConfig, Settings, parse_overrides, resolve_llm


def test_run_hash_depends_on_model_not_prices():
    cfg = ExperimentConfig()
    a = resolve_llm(cfg, Settings(model="m1", price_input_per_1m=0))
    b = resolve_llm(cfg, Settings(model="m2", price_input_per_1m=0))
    c = resolve_llm(cfg, Settings(model="m1", price_input_per_1m=5))
    assert cfg.short_hash(a) != cfg.short_hash(b)
    assert cfg.short_hash(a) == cfg.short_hash(c)


def test_overrides_parsed_as_yaml():
    assert parse_overrides(["max_attempts=2", "llm.reasoning={enabled: false}"]) == {
        "max_attempts": 2,
        "llm": {"reasoning": {"enabled": False}},
    }
