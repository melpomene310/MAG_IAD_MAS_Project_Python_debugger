# Единственная точка входа. Все цели выполняются внутри контейнера app.
# Если make уже запущен внутри контейнера (/.dockerenv), команды выполняются напрямую.
ifeq ($(wildcard /.dockerenv),)
DC := docker compose run --rm app
else
DC :=
endif

PY := $(DC) python -m debugmas

PRESET ?= paper3
SOLVER ?= workflow
CONFIG ?= configs/workflow.yaml
SPLIT ?= val
RUNS ?=
RUN_TAG ?=
TASK ?=
ARGS ?=

.PHONY: build shell fetch-tests data split test lint smoke run final report case lock

build:
	docker compose build

shell:
	docker compose run --rm app bash

lock:
	docker run --rm -v $(CURDIR):/w -w /w ghcr.io/astral-sh/uv:0.4.30-python3.11-bookworm-slim uv lock

# Тесты AtCoder вместо Test.zip (на хосте, нужны git и сеть; можно прерывать и продолжать)
fetch-tests:
	./scripts/fetch_tests.sh

data:
	$(PY) data --config configs/data.yaml

split:
	$(PY) split --preset $(PRESET)

test:
	$(DC) sh -c "ruff check --no-cache src tests && ruff format --no-cache --check src tests && pytest -q"

lint:
	$(DC) sh -c "ruff format --no-cache src tests && ruff check --no-cache --fix src tests"

smoke:
	$(PY) smoke --solver $(SOLVER)

run:
	$(PY) run --config $(CONFIG) --split $(SPLIT) $(ARGS)

final:
	$(PY) final --config $(CONFIG) --run-tag $(RUN_TAG)

report:
	$(PY) report $(RUNS)

case:
	$(PY) case --run $(RUN) --task $(TASK)
