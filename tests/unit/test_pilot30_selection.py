from pathlib import Path

from debugmas.data.pilot_selection import (
    PAPER3_BINS,
    PILOT30_EXISTING,
    available_tasks,
    select_candidates,
)


def test_candidates_are_deterministic_and_keep_original_pilot() -> None:
    difficulties = {
        **{f"easy_{i}": 10 for i in range(30)},
        **{f"medium_{i}": 500 for i in range(30)},
        **{f"hard_{i}": 1500 for i in range(30)},
    }
    difficulties |= {
        "abc223_a": 6,
        "abc224_b": 81,
        "abc225_d": 778,
        "abc223_d": 1069,
        "abc223_e": 1510,
        "abc223_f": 1641,
    }
    a = select_candidates(difficulties, set(difficulties), per_bin=10)
    assert a == select_candidates(difficulties, set(difficulties), per_bin=10)
    assert {"abc223_a", "abc224_b", "abc225_d", "abc223_d", "abc223_e", "abc223_f"} <= set(a)


def test_sample_is_balanced_unique_and_keeps_original_pilot() -> None:
    difficulties = {
        **{f"easy_{i}": 10 for i in range(8)},
        **{f"medium_{i}": 500 for i in range(8)},
        **{f"hard_{i}": 1500 for i in range(8)},
        "abc223_a": 6,
        "abc224_b": 81,
        "abc225_d": 778,
        "abc223_d": 1069,
        "abc223_e": 1510,
        "abc223_f": 1641,
    }
    manifest = select_candidates(difficulties, set(difficulties), per_bin=10)

    assert len(manifest) == len(set(manifest)) == 30
    assert PILOT30_EXISTING <= set(manifest)
    assert {
        name: sum(
            PAPER3_BINS[name][0] <= difficulties[task] < (PAPER3_BINS[name][1] or float("inf"))
            for task in manifest
        )
        for name in PAPER3_BINS
    } == {"easy": 10, "medium": 10, "hard": 10}


def test_available_tasks_requires_both_test_directories(tmp_path: Path) -> None:
    raw = tmp_path / "ConDefects"
    tests = tmp_path / "Test"
    (raw / "Code" / "abc001_a" / "Python").mkdir(parents=True)
    (raw / "difficulty.txt").write_text("abc001_a 10\n")
    (tests / "abc001" / "A" / "in").mkdir(parents=True)

    assert available_tasks(raw, tests) == {}

    (tests / "abc001" / "A" / "out").mkdir()
    assert available_tasks(raw, tests) == {}

    (tests / "abc001" / "A" / "in" / "sample.in").write_text("1\n")
    (tests / "abc001" / "A" / "out" / "sample.in").write_text("1\n")
    assert available_tasks(raw, tests) == {"abc001_a": 10}
