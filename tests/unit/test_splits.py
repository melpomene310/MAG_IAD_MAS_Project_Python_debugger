import random

import pytest

from debugmas.config import CONFIGS_DIR, load_yaml
from debugmas.data.splits import bin_of, make_splits

CFG = load_yaml(CONFIGS_DIR / "splits.yaml")


def _index(n: int = 600, seed: int = 0):
    rng = random.Random(seed)
    return [{"task_id": f"t{i:04d}", "difficulty": rng.randint(0, 3500)} for i in range(n)]


@pytest.mark.parametrize("preset", list(CFG["presets"]))
def test_deterministic_and_disjoint(preset):
    bins = CFG["presets"][preset]["bins"]
    a = make_splits(_index(), bins, CFG["sizes"], 42, preset)
    b = make_splits(list(reversed(_index())), bins, CFG["sizes"], 42, preset)
    assert a == b
    sets = [set(v) for v in a.values()]
    assert sum(len(s) for s in sets) == len(set().union(*sets))


def test_seed_changes_split():
    bins = CFG["presets"]["paper3"]["bins"]
    a = make_splits(_index(), bins, CFG["sizes"], 42, "paper3")
    b = make_splits(_index(), bins, CFG["sizes"], 7, "paper3")
    assert a["test"] != b["test"]


def test_stratified_by_bin():
    bins = CFG["presets"]["paper3"]["bins"]
    idx = _index()
    diff = {r["task_id"]: r["difficulty"] for r in idx}
    s = make_splits(idx, bins, CFG["sizes"], 42, "paper3")
    for split, n in (("val", 15), ("test", 50)):
        per_bin = {b: sum(bin_of(diff[t], bins) == b for t in s[split]) for b in bins}
        assert all(v == n for v in per_bin.values()), per_bin


def test_half_open_bins_and_hard_only():
    bins = CFG["presets"]["paper3"]["bins"]
    assert bin_of(399, bins) == "easy" and bin_of(400, bins) == "medium"
    assert bin_of(1300, bins) == "hard" and bin_of(None, bins) is None
    hard = CFG["presets"]["hard_only"]["bins"]
    assert bin_of(100, hard) is None
    s = make_splits(_index(), hard, CFG["sizes"], 42, "hard_only")
    diff = {r["task_id"]: r["difficulty"] for r in _index()}
    assert all(diff[t] >= 400 for v in s.values() for t in v)


def test_small_bin_shrinks_with_warning(caplog):
    idx = [{"task_id": f"t{i}", "difficulty": 10} for i in range(13)]
    s = make_splits(idx, {"easy": [0, 400]}, {"val": 15, "test": 50}, 42, "p")
    assert len(s["val"]) == 3 and len(s["test"]) == 10 and len(s["dev"]) == 0
    assert "уменьшены" in caplog.text
