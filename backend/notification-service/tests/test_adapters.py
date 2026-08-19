"""Tests for notification channel transport adapters."""

from __future__ import annotations

import smtplib

import pytest

from notification_service.channel.adapters import EmailAdapter, PushAdapter, SmsAdapter, build_adapters
from notification_service.configuration import NotificationSettings


def _settings(transport: str, **overrides) -> NotificationSettings:
    defaults = {"notifications_transport": transport}
    defaults.update(overrides)
    return NotificationSettings(**defaults)


class TestEmailAdapter:
    def test_log_transport_returns_deterministic_id(self, monkeypatch) -> None:
        monkeypatch.setattr(
            "notification_service.configuration.NotificationSettings.smtp_enabled",
            property(lambda self: False),
        )
        adapter = EmailAdapter(_settings("log"))
        response = adapter.send(recipient="a@example.com", subject="Hi", body="Hello")
        assert response["provider"] == "log"
        assert response["messageId"].startswith("email-")

    def test_rejects_invalid_recipient(self) -> None:
        adapter = EmailAdapter(_settings("log"))
        with pytest.raises(ValueError):
            adapter.send(recipient="not-an-email", subject="Hi", body="Hello")

    def test_smtp_transport_sends_real_mail(self, monkeypatch) -> None:
        sent: dict = {}

        class FakeSMTP:
            def __init__(self, host, port, timeout):
                sent["host"] = host
                sent["port"] = port
                sent["timeout"] = timeout

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def starttls(self, context=None):
                sent["tls"] = True

            def login(self, user, password):
                sent["login"] = (user, password)

            def sendmail(self, from_addr, to, message):
                sent["mail"] = (from_addr, to, message)

        monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
        adapter = EmailAdapter(
            _settings("smtp", smtp_host="relay.example", smtp_port=587, smtp_username="user", smtp_password="pw")
        )
        response = adapter.send(recipient="a@example.com", subject="Hi", body="Hello body")
        assert response["provider"] == "smtp"
        assert sent["host"] == "relay.example"
        assert sent["tls"] is True
        assert sent["login"] == ("user", "pw")
        assert sent["mail"][0] == "noreply@ehos.example"
        assert sent["mail"][1] == "a@example.com"
        assert "Hello body" in sent["mail"][2]


class TestSmsAdapter:
    def test_log_transport(self) -> None:
        adapter = SmsAdapter(_settings("log"))
        response = adapter.send(recipient="+1555000", subject=None, body="hi")
        assert response["provider"] == "log"
        assert response["messageId"].startswith("sms-")

    def test_http_transport_posts_to_provider(self, monkeypatch) -> None:
        class FakeTransport:
            def __init__(self):
                self.calls = []

            # post() is called as module-level httpx.post/url
            def __call__(self, url, *, json=None, headers=None, timeout=None):
                self.calls.append((url, json, headers))
                return _FakeResponse()

        class _FakeResponse:
            def raise_for_status(self):
                return None

            @property
            def text(self):
                return "msg-42"

        transport = FakeTransport()
        monkeypatch.setattr("notification_service.channel.adapters.httpx.post", transport)
        adapter = SmsAdapter(
            _settings("http", sms_http_url="https://gateway/sms", sms_http_token="tok")
        )
        response = adapter.send(recipient="+1555000", subject=None, body="hello")
        assert response["provider"] == "http-sms"
        url, payload, headers = transport.calls[0]
        assert url == "https://gateway/sms"
        assert payload == {"to": "+1555000", "text": "hello"}
        assert headers == {"Authorization": "Bearer tok"}

    def test_http_transport_failure_raises(self, monkeypatch) -> None:
        class Boom:
            def raise_for_status(self):
                import httpx

                raise httpx.HTTPStatusError("500", request=None, response=None)

            @property
            def text(self):
                return "err"

        monkeypatch.setattr("notification_service.channel.adapters.httpx.post", lambda *a, **k: Boom())
        adapter = SmsAdapter(_settings("http", sms_http_url="https://gateway/sms"))
        with pytest.raises(RuntimeError):
            adapter.send(recipient="+1555000", subject=None, body="hello")


class TestPushAdapter:
    def test_log_transport(self) -> None:
        adapter = PushAdapter(_settings("log"))
        response = adapter.send(recipient="dev:token", subject="T", body="b")
        assert response["provider"] == "log"

    def test_http_transport(self, monkeypatch) -> None:
        seen: dict = {}

        class Fake:
            def raise_for_status(self):
                return None

            @property
            def text(self):
                return "push-9"

        def post(url, *, json=None, headers=None, timeout=None):
            seen.update({"url": url, "json": json, "headers": headers})
            return Fake()

        monkeypatch.setattr("notification_service.channel.adapters.httpx.post", post)
        adapter = PushAdapter(_settings("http", push_http_url="https://gateway/push"))
        response = adapter.send(recipient="dev:token", subject="T", body="b")
        assert response["provider"] == "http-push"
        assert seen["url"] == "https://gateway/push"
        assert seen["json"] == {"recipient": "dev:token", "title": "T", "body": "b"}


class TestBuildAdapters:
    def test_log_transport_default(self) -> None:
        adapters = build_adapters(_settings("log"))
        assert set(adapters) == {"email", "sms", "push", "in_app"}
        assert adapters["email"].send(recipient="a@example.com", subject="s", body="b")["provider"] == "log"

    def test_missing_credentials_fallback(self) -> None:
        # transport=smtp but no way to connect -> delivery raises, service retries
        adapter = EmailAdapter(_settings("smtp", smtp_host="127.0.0.1", smtp_port=9))
        with pytest.raises(RuntimeError):
            adapter.send(recipient="a@example.com", subject="s", body="b")