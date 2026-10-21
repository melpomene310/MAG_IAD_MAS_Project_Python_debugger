# Единственная точка входа. Все цели выполняются внутри контейнера app.
# Если make уже запущен внутри контейнера (/.dockerenv), команды выполняются напрямую.
PROFILE ?= default
ENV_FILE ?= $(if $(filter default,$(PROFILE)),.env,.env.$(PROFILE))
COMPOSE := DEBUGMAS_ENV_FILE=$(ENV_FILE) docker compose

ifeq ($(wildcard /.dockerenv),)
DC := $(COMPOSE) run --rm app
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

.PHONY: build shell fetch-tests data split test test-targeted lint lint-targeted lint-check-targeted smoke run final report case lock

build:
	$(COMPOSE) build

shell:
	$(COMPOSE) run --rm app bash

lock:
	docker run --rm -v $(CURDIR):/w -w /w ghcr.io/astral-sh/uv:0.4.30-python3.11-bookworm-slim uv lock

# Тесты AtCoder вместо Test.zip (на хосте, нужны git и сеть; можно прерывать и продолжать)
fetch-tests:
	./scripts/fetch_tests.sh

data:
	$(PY) data --config configs/data.yaml $(ARGS)

split:
	$(PY) split --preset $(PRESET)

test:
	$(DC) sh -c "ruff check --no-cache src tests && ruff format --no-cache --check src tests && pytest -q"

test-targeted:
	$(DC) pytest -q $(ARGS)

lint-check-targeted:
	$(DC) sh -c "ruff check --no-cache $(ARGS) && ruff format --no-cache --check $(ARGS)"

lint:
	$(DC) sh -c "ruff format --no-cache src tests && ruff check --no-cache --fix src tests"

lint-targeted:
	$(DC) sh -c "ruff format --no-cache $(ARGS) && ruff check --no-cache --fix $(ARGS)"

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
