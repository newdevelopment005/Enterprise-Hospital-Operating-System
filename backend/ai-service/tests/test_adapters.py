"""Tests for the OpenAI-compatible inference adapter and HTTP media backends."""

import base64
import json

import httpx
import pytest

from ai_service.service.ai_service import AiService
from ai_service.service.engines import AiError, InferenceEngine


class FakeTransport(httpx.AsyncBaseTransport):
    def __init__(self, responses: list):
        self.responses = responses
        self.requests = []

    async def handle_async_request(self, request):
        self.requests.append((request.url, request.headers, request.content))
        if not self.responses:
            return httpx.Response(500, request=request)
        item = self.responses.pop(0)
        payload, status = (item, 200) if isinstance(item, dict) else item
        return httpx.Response(
            status,
            json=payload,
            headers={"content-type": "application/json"},
            request=request,
        )


@pytest.fixture
def settings():
    from ai_service.configuration import AiSettings

    s = AiSettings()
    s.service_name = "ai-service"
    s.database_name = "ehos_ai"
    return s


_REAL_ASYNC_CLIENT = httpx.AsyncClient


def _client_factory(transport):
    def _make(**kwargs):
        kwargs.pop("timeout", None)
        return _REAL_ASYNC_CLIENT(transport=kwargs.pop("transport", transport), **kwargs)

    return _make


async def test_openai_inference_sends_chat_completions(monkeypatch, settings):
    settings.inference_adapter = "openai"
    settings.openai_base_url = "https://provider.example/v1"
    settings.openai_api_key = "k123"

    transport = FakeTransport(
        [{"choices": [{"message": {"content": "The patient should rest."}}]}]
    )
    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))

    engine = InferenceEngine(settings)
    result = await engine.complete("ehos-gpt", "Summarize the note", max_tokens=64)

    assert result.text == "The patient should rest."
    url, headers, _body = transport.requests[0]
    assert str(url).endswith("/chat/completions")
    assert headers["Authorization"] == "Bearer k123"
    assert json.loads(_body)["model"] == "ehos-gpt"


async def test_openai_inference_failure_surfaces_503(monkeypatch, settings):
    settings.inference_adapter = "openai"

    class Boom:
        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return False

        async def post(self, *args, **kwargs):
            raise httpx.ConnectError("refused")

    monkeypatch.setattr(httpx, "AsyncClient", lambda **kwargs: Boom())
    engine = InferenceEngine(settings)
    with pytest.raises(AiError) as exc:
        await engine.complete("ehos-gpt", "prompt")
    assert exc.value.status_code == 503
    assert exc.value.error_code == "RUNTIME_UNAVAILABLE"


class FakeMediaTransport(httpx.AsyncBaseTransport):
    def __init__(self, payload, *, binary=False):
        self.payload = payload
        self.binary = binary
        self.requests = []

    async def handle_async_request(self, request):
        self.requests.append(request)
        if self.binary:
            return httpx.Response(
                200, content=self.payload, headers={"content-type": "audio/wav"}, request=request
            )
        return httpx.Response(200, json=self.payload, request=request)


async def test_stt_http_backend_posts_audio(monkeypatch, settings):
    settings.stt_adapter = "http"
    settings.stt_http_url = "https://provider.example/stt"
    settings.stt_http_token = "tok"
    transport = FakeMediaTransport({"text": "Blood pressure 120 over 80"})
    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))
    service = AiService(settings)
    text, engine = await service.stt_transcribe(b"RIFF\x00audio")
    assert text == "Blood pressure 120 over 80"
    assert engine == "http"
    assert transport.requests[0].headers["Authorization"] == "Bearer tok"


async def test_tts_http_backend_returns_base64_audio(monkeypatch, settings):
    settings.tts_adapter = "http"
    settings.tts_http_url = "https://provider.example/tts"
    transport = FakeMediaTransport(b"\x00\x00WAVdata", binary=True)
    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))
    service = AiService(settings)
    b64, media_type = await service.tts_synthesize("Discharge tomorrow")
    assert base64.b64decode(b64) == b"\x00\x00WAVdata"
    assert media_type == "audio/wav"


async def test_ocr_http_backend_posts_image(monkeypatch, settings):
    settings.ocr_adapter = "http"
    settings.ocr_http_url = "https://provider.example/ocr"
    transport = FakeMediaTransport({"text": "AMOXICILLIN 500MG"})
    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))
    service = AiService(settings)
    text, engine = await service.ocr_extract(b"\x89PNG", "label.png")
    assert text == "AMOXICILLIN 500MG"
    assert engine == "http"


async def test_http_backend_missing_endpoint_surfaces_503(settings):
    settings.stt_adapter = "http"
    service = AiService(settings)
    with pytest.raises(AiError) as exc:
        await service.stt_transcribe(b"audio")
    assert exc.value.status_code == 503


class RawTransport(httpx.AsyncBaseTransport):
    def __init__(self, content: bytes, headers=None):
        self.content = content
        self.headers = headers or {}
        self.requests = []

    async def handle_async_request(self, request):
        self.requests.append((request.url, request.headers))
        return httpx.Response(200, content=self.content, headers=self.headers, request=request)


async def test_openai_non_json_response_surfaces_502(monkeypatch, settings):
    settings.inference_adapter = "openai"
    settings.openai_base_url = "https://provider.example/v1"
    transport = RawTransport(b"<html>gateway error</html>")
    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))
    engine = InferenceEngine(settings)
    with pytest.raises(AiError) as exc:
        await engine.complete("ehos-gpt", "prompt")
    assert exc.value.error_code == "RUNTIME_BAD_RESPONSE"
    assert exc.value.status_code == 502


async def test_openai_message_without_content_returns_empty(monkeypatch, settings):
    settings.inference_adapter = "openai"
    settings.openai_base_url = "https://provider.example/v1"
    transport = FakeTransport([{"choices": [{"message": {"refusal": "I cannot"}}]}])
    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))
    engine = InferenceEngine(settings)
    result = await engine.complete("ehos-gpt", "prompt")
    assert result.text == ""


async def test_stt_non_json_response_surfaces_502(monkeypatch, settings):
    settings.stt_adapter = "http"
    settings.stt_http_url = "https://provider.example/stt"
    settings.stt_http_token = "tok"
    transport = RawTransport(b"<html>bad gateway</html>")
    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))
    service = AiService(settings)
    with pytest.raises(AiError) as exc:
        await service.stt_transcribe(b"audio")
    assert exc.value.error_code == "RUNTIME_BAD_RESPONSE"


async def test_ping_runtime_sends_openai_auth_header(monkeypatch, settings):
    settings.inference_adapter = "openai"
    settings.openai_base_url = "https://provider.example/v1"
    settings.openai_api_key = "k123"
    transport = RawTransport(b"{}")
    monkeypatch.setattr(httpx, "AsyncClient", _client_factory(transport))
    service = AiService(settings)
    await service._ping_runtime()
    url, headers = transport.requests[0]
    assert str(url).endswith("/models")
    assert headers["Authorization"] == "Bearer k123"
