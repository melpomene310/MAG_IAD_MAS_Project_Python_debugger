FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_LINK_MODE=copy

# git — для клонирования ConDefects и записи коммита; unzip — для Test.zip.
# Сборочные пакеты нужны gmpy2/bitarray, удаляются в том же слое.
COPY requirements-atcoder.txt /tmp/requirements-atcoder.txt
RUN apt-get update \
    && apt-get install -y --no-install-recommends git make unzip build-essential libgmp-dev libmpfr-dev libmpc-dev \
    && /usr/local/bin/python -m pip install --no-cache-dir -r /tmp/requirements-atcoder.txt \
    && apt-get purge -y build-essential \
    && apt-get autoremove -y \
    && apt-get install -y --no-install-recommends libgmp10 libmpfr6 libmpc3 \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:0.4.30 /uv /usr/local/bin/uv

WORKDIR /app
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --frozen --no-install-project

COPY . .
RUN uv sync --frozen

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH=/app/src
RUN git config --global --add safe.directory '*'

CMD ["bash"]
