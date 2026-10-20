"""Живой тест с реальным endpoint: `pytest -m live`."""

import pytest

from debugmas.config import Settings
from debugmas.llm.client import LLMClient


@pytest.mark.live
def test_live_endpoint():
    s = Settings()
    client = LLMClient(s.model, s.openai_base_url, s.openai_api_key, max_retries=1)
    r = client.chat([{"role": "user", "content": "Ответь одним словом: ok"}])
    assert r.content and r.usage.total > 0
