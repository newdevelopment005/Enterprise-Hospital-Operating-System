"""Delivery channel adapters.

Each channel exposes ``send``/``send_async``. Transport is selected by
``NotificationSettings.notifications_transport``:

- ``log`` (default): record and return a deterministic MessageId; exercises the
  pipeline without external credentials.
- ``smtp``: real SMTP delivery via the standard library (AUTH + TLS optional).
- ``http``: SMS/push POST to a provider webhook with bearer auth.

Any provider failure raises, and the core service retries every channel up to
``MAX_ATTEMPTS`` before marking the notification failed.
"""

from __future__ import annotations

import smtplib
import ssl
import time
from abc import ABC, abstractmethod

import httpx
import structlog

from notification_service.configuration import NotificationSettings

log = structlog.get_logger("notification-service")


class ChannelAdapter(ABC):
    name: str = "base"

    @abstractmethod
    def send(self, *, recipient: str, subject: str | None, body: str) -> dict:
        """Deliver a message. Raise on failure; return a provider response dict."""


def _message_id(prefix: str, recipient: str) -> str:
    return f"{prefix}-{int(time.time() * 1000)}-{abs(hash(recipient)) % 1_000_000:06d}"


class EmailAdapter(ChannelAdapter):
    name = "email"

    def __init__(self, settings: NotificationSettings):
        self.settings = settings

    def send(self, *, recipient: str, subject: str | None, body: str) -> dict:
        if "@" not in recipient:
            raise ValueError("Email adapter requires a valid email recipient")
        if not self.settings.smtp_enabled:
            log.info("email_logged", recipient=recipient, subject=subject)
            return {"provider": "log", "messageId": _message_id("email", recipient)}
        return self._send_smtp(recipient, subject or "", body)

    def _send_smtp(self, recipient: str, subject: str, body: str) -> dict:
        message = (
            f"From: {self.settings.smtp_from}\r\n"
            f"To: {recipient}\r\n"
            f"Subject: {subject}\r\n"
            "Content-Type: text/plain; charset=utf-8\r\n"
            "\r\n"
            f"{body}"
        )
        try:
            with smtplib.SMTP(
                self.settings.smtp_host, self.settings.smtp_port, timeout=self.settings.smtp_timeout
            ) as server:
                if self.settings.smtp_use_tls:
                    server.starttls(context=ssl.create_default_context())
                if self.settings.smtp_username and self.settings.smtp_password:
                    server.login(self.settings.smtp_username, self.settings.smtp_password)
                server.sendmail(self.settings.smtp_from, recipient, message)
        except (smtplib.SMTPException, OSError) as exc:
            raise RuntimeError(f"SMTP delivery failed: {exc}") from exc
        log.info("email_sent", recipient=recipient, subject=subject)
        return {"provider": "smtp", "messageId": _message_id("email", recipient)}


class SmsAdapter(ChannelAdapter):
    name = "sms"

    def __init__(self, settings: NotificationSettings):
        self.settings = settings

    def send(self, *, recipient: str, subject: str | None, body: str) -> dict:
        if self.settings.http_enabled and self.settings.sms_http_url:
            return self._send_http(self.settings.sms_http_url, self.settings.sms_http_token, recipient, body)
        log.info("sms_logged", recipient=recipient, body_length=len(body))
        return {"provider": "log", "messageId": _message_id("sms", recipient)}

    def _send_http(self, url: str, token: str | None, recipient: str, body: str) -> dict:
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        try:
            response = httpx.post(url, json={"to": recipient, "text": body}, headers=headers, timeout=10.0)
            response.raise_for_status()
        except httpx.HTTPError as exc:
            raise RuntimeError(f"SMS provider failed: {exc}") from exc
        return {"provider": "http-sms", "messageId": response.text[:128] or str(hash(recipient))}


class PushAdapter(ChannelAdapter):
    name = "push"

    def __init__(self, settings: NotificationSettings):
        self.settings = settings

    def send(self, *, recipient: str, subject: str | None, body: str) -> dict:
        if self.settings.http_enabled and self.settings.push_http_url:
            headers = (
                {"Authorization": f"Bearer {self.settings.push_http_token}"}
                if self.settings.push_http_token
                else {}
            )
            try:
                response = httpx.post(
                    self.settings.push_http_url,
                    json={"recipient": recipient, "title": subject or "", "body": body},
                    headers=headers,
                    timeout=10.0,
                )
                response.raise_for_status()
            except httpx.HTTPError as exc:
                raise RuntimeError(f"Push provider failed: {exc}") from exc
            return {"provider": "http-push", "messageId": response.text[:128] or str(hash(recipient))}
        log.info("push_logged", recipient=recipient, subject=subject, body_length=len(body))
        return {"provider": "log", "messageId": _message_id("push", recipient)}


class InAppAdapter(ChannelAdapter):
    name = "in_app"

    def __init__(self, settings: NotificationSettings):
        self.settings = settings

    def send(self, *, recipient: str, subject: str | None, body: str) -> dict:
        log.info("in_app_notification", recipient=recipient, subject=subject, body_length=len(body))
        return {"provider": "in-app", "messageId": _message_id("app", recipient)}


def build_adapters(settings: NotificationSettings | None = None) -> dict[str, ChannelAdapter]:
    settings = settings or NotificationSettings()
    return {
        adapter.name: adapter
        for adapter in (EmailAdapter(settings), SmsAdapter(settings), PushAdapter(settings), InAppAdapter(settings))
    }