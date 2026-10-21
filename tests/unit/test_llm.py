from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import pytest

from debugmas.llm.cache import LLMCache, cache_key
from debugmas.llm.client import LLMClient, LLMError
from debugmas.llm.fake import FakeLLM
from debugmas.llm.usage import Usage


def completion(content: str = "ok", usage: dict | None = None, tool_calls=None) -> dict:
    msg: dict = {"role": "assistant", "content": content}
    if tool_calls:
        msg["tool_calls"] = tool_calls
    body = {
        "id": "x",
        "object": "chat.completion",
        "created": 0,
        "model": "m",
        "choices": [{"index": 0, "message": msg, "finish_reason": "stop"}],
    }
    if usage is not None:
        body["usage"] = usage
    return body


USAGE = {
    "prompt_tokens": 10,
    "completion_tokens": 5,
    "total_tokens": 15,
    "completion_tokens_details": {"reasoning_tokens": 2},
    "prompt_tokens_details": {"cached_tokens": 4},
}


class FakeServer:
    def __init__(self) -> None:
        self.queue: list[tuple[int, dict]] = []
        self.requests: list[dict] = []
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self) -> None:  # noqa: N802
                n = int(self.headers.get("Content-Length", 0))
                outer.requests.append(json.loads(self.rfile.read(n)))
                status, body = outer.queue.pop(0) if outer.queue else (200, completion())
                data = json.dumps(body).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(data)))
                self.end_headers()
                self.wfile.write(data)

            def log_message(self, *args) -> None:
                pass

        self.httpd = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.httpd.server_address[1]}/v1"
        threading.Thread(target=self.httpd.serve_forever, daemon=True).start()

    def close(self) -> None:
        self.httpd.shutdown()


@pytest.fixture
def server():
    s = FakeServer()
    yield s
    s.close()


def client(server: FakeServer, cache: LLMCache | None = None, **kw) -> LLMClient:
    params = {"max_retries": 3, "backoff_base_s": 0.0, "sleep": lambda s: None}
    params.update(kw)
    return LLMClient("m", server.url, "k", cache=cache, **params)


MSGS = [{"role": "user", "content": "hi"}]


def test_cache_key_separates_provider_endpoints():
    a = cache_key("http://provider-a/v1", "same-model", MSGS, None, {}, 0)
    b = cache_key("http://provider-b/v1", "same-model", MSGS, None, {}, 0)
    assert a != b


def test_usage_parsed(server):
    server.queue.append((200, completion("hello", USAGE)))
    r = client(server).chat(MSGS)
    assert r.content == "hello"
    assert (r.usage.input, r.usage.output, r.usage.reasoning, r.usage.cached_input) == (10, 5, 2, 4)
    assert r.usage.calls_without_usage == 0 and r.raw_usage["total_tokens"] == 15
    assert server.requests[0]["temperature"] == 0.0


def test_tool_calls_parsed(server):
    tc = [{"id": "c1", "type": "function", "function": {"name": "run_tests", "arguments": "{}"}}]
    server.queue.append((200, completion("", USAGE, tool_calls=tc)))
    r = client(server).chat(MSGS, tools=[{"type": "function", "function": {"name": "run_tests"}}])
    assert [(t.id, t.name, t.arguments) for t in r.tool_calls] == [("c1", "run_tests", "{}")]
    assert r.assistant_message()["tool_calls"][0]["function"]["name"] == "run_tests"


def test_missing_usage_is_counted_not_estimated(server):
    server.queue.append((200, completion("some answer text")))
    r = client(server).chat(MSGS)
    assert r.usage.calls_without_usage == 1 and r.usage.total == 0


def test_failed_request_without_usage_is_counted(server):
    server.queue += [(500, {"error": {"message": "x"}}), (200, completion("ok", USAGE))]
    r = client(server).chat(MSGS)
    assert r.usage.failed_calls == 1 and r.usage.failed_without_usage == 1


def test_retry_on_429_and_5xx_counts_failed_tokens(server):
    err_usage = {"prompt_tokens": 7, "completion_tokens": 0}
    server.queue += [
        (429, {"error": {"message": "rate"}}),
        (500, {"error": {"message": "boom"}, "usage": err_usage}),
        (200, completion("ok", USAGE)),
    ]
    r = client(server).chat(MSGS)
    assert r.content == "ok" and len(server.requests) == 3
    assert r.usage.failed_calls == 2 and r.usage.input == 17


def test_gives_up_after_retries(server):
    server.queue += [(503, {"error": {"message": "x"}, "usage": {"prompt_tokens": 3}})] * 5
    with pytest.raises(LLMError) as ei:
        client(server, max_retries=2).chat(MSGS)
    assert len(server.requests) == 3
    assert ei.value.usage.failed_calls == 3 and ei.value.usage.input == 9


def test_no_retry_on_400(server):
    server.queue.append((400, {"error": {"message": "bad"}}))
    with pytest.raises(LLMError):
        client(server).chat(MSGS)
    assert len(server.requests) == 1


def test_cache_hit_miss_and_repeat_idx(server, tmp_path: Path):
    cache = LLMCache(tmp_path)
    server.queue += [(200, completion("first", USAGE)), (200, completion("second", USAGE))]
    c0 = client(server, cache=cache)
    a = c0.chat(MSGS)
    b = c0.chat(MSGS)
    assert not a.cache_hit and b.cache_hit and b.content == "first"
    assert b.usage.input == 10 and b.usage.cache_hits == 1  # затраты из сохранённого usage
    assert len(server.requests) == 1
    c1 = client(server, cache=cache, repeat_idx=1)
    c = c1.chat(MSGS)
    assert not c.cache_hit and c.content == "second" and len(server.requests) == 2
    d = c0.chat(MSGS + [{"role": "user", "content": "more"}])
    assert not d.cache_hit


def test_fake_llm_script_and_errors():
    llm = FakeLLM(
        [
            {"content": "a"},
            {"tool_calls": [{"name": "submit", "arguments": {"code": "x"}}]},
            {"error": "down", "usage": {"input": 3}},
        ]
    )
    assert llm.chat(MSGS).content == "a"
    r = llm.chat(MSGS)
    assert r.tool_calls[0].name == "submit" and json.loads(r.tool_calls[0].arguments) == {
        "code": "x"
    }
    with pytest.raises(LLMError) as ei:
        llm.chat(MSGS)
    assert ei.value.usage.input == 3 and ei.value.usage.failed_calls == 1
    assert len(llm.calls) == 3


def test_usage_arithmetic_and_cost():
    u = Usage(input=1_000_000, output=500_000) + Usage(input=0, output=500_000)
    assert u.total == 2_000_000
    assert u.cost(1.0, 1.0, 2.0) == pytest.approx(3.0)
