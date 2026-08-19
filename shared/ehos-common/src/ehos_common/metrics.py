"""Lightweight Prometheus metrics for EHOS services (no extra dependencies).

A small registry plus an ASGI middleware and a ``/metrics`` router that render
the Prometheus text exposition format (``text/plain; version=0.0.4``) so the
existing Prometheus stack in ``infrastructure/monitoring`` can scrape them.

Three metric kinds are supported — counter, gauge and histogram — keyed by
``(name, label_key... label_value...)``. The middleware records request rate,
latency and error counts per route. If the service has no registry attached, the
module-level default is used.
"""

from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, Request, Response

metrics_router = APIRouter(tags=["metrics"])

_TYPE_LABEL = {
    "counter": "counter",
    "gauge": "gauge",
    "histogram": "histogram",
}

_PREFIX = "ehos_"


class MetricError(ValueError):
    pass


def _sanitize(name: str) -> str:
    if not name or not name.isidentifier() or ":" in name:
        raise MetricError(f"metric name {name!r} is not valid")
    return name


def _labels_key(labels: dict | None) -> tuple:
    return tuple(sorted((labels or {}).items()))


class MetricRegistry:
    """Process-local metric store rendering the Prometheus text format."""

    def __init__(self, prefix: str = _PREFIX) -> None:
        self.prefix = prefix
        self._values: dict[tuple[str, tuple], tuple[Literal["counter", "gauge"], float]] = {}
        self._histograms: dict[tuple[str, tuple], list] = {}
        self._help: dict[str, str] = {}
        self._labels: dict[str, str | None] = {}

    def describe(self, name: str, *, help: str = "", label: str | None = None) -> None:  # noqa: A002
        # track which labels are valid so render can pre-declare label dimensions
        if help:
            self._help[name] = help
        if label is not None:
            self._labels[name] = label

    # ---- instruments -------------------------------------------------------

    def inc(self, name: str, *, labels: dict | None = None, value: float = 1.0) -> None:
        self._values[(_sanitize(name), _labels_key(labels))] = ("counter", self._counter(name, labels) + value)

    def _counter(self, name: str, labels: dict | None) -> float:
        entry = self._values.get((name, _labels_key(labels)))
        return entry[1] if entry and entry[0] == "counter" else 0.0

    def set(self, name: str, *, labels: dict | None = None, value: float) -> None:
        self._values[(_sanitize(name), _labels_key(labels))] = ("gauge", float(value))

    def histogram(self, name: str, value: float, *, labels: dict | None = None) -> None:
        key = (_sanitize(name), _labels_key(labels))
        entry = self._histograms.get(key)
        if entry is None:
            entry = ["histogram", [], 0]
            self._histograms[key] = entry
        entry[1].append(float(value))
        entry[2] += 1

    def snapshot(self) -> dict:
        return {"values": dict(self._values), "histograms": dict(self._histograms), "help": dict(self._help)}

    # ---- rendering ---------------------------------------------------------

    @staticmethod
    def _format_labels(labels) -> str:
        """Render a label dimension set as ``{k1="v1",k2="v2"}`` (escaped)."""
        if not labels:
            return ""
        parts = []
        for key, value in labels:
            text = str(value).replace("\\", "\\\\").replace('"', '\\"')
            parts.append(f'{key}="{text}"')
        return "{" + ", ".join(parts) + "}"

    @staticmethod
    def _hist_labels(label_key, extra) -> str:
        return MetricRegistry._format_labels(tuple(list(label_key) + list(extra)))

    def render(self) -> str:
        lines: list[str] = []
        seen: set[str] = set()
        for (name, label_key), (kind, value) in sorted(self._values.items()):
            self._declare(lines, seen, name, kind)
            lines.append(f"{self.prefix}{name}{self._format_labels(label_key)} {value:g}")
        for (name, label_key), (_kind, samples, count) in sorted(self._histograms.items()):
            self._declare(lines, seen, name, "histogram")
            for edge in self._bucket_edges(samples):
                cumulative = sum(1 for v in samples if v <= edge)
                lines.append(
                    f"{self.prefix}{name}_bucket{self._hist_labels(label_key, (('le', f'{edge:g}'),))} {cumulative}"
                )
            lines.append(
                f"{self.prefix}{name}_bucket{self._hist_labels(label_key, (('le', '+Inf'),))} {len(samples)}"
            )
            labels = self._format_labels(label_key)
            lines.append(f"{self.prefix}{name}_sum{labels} {sum(samples):g}")
            lines.append(f"{self.prefix}{name}_count{labels} {count}")
        return "\n".join(lines) + "\n"

    @staticmethod
    def _bucket_edges(samples: list[float]) -> list[float]:
        # Prometheus default buckets scaled to observed range
        default = [0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0, 2.5, 5.0, 10.0]
        return default

    def _declare(self, lines: list[str], seen: set[str], name: str, kind: str) -> None:
        qualified = f"{self.prefix}{name}"
        if qualified in seen:
            return
        seen.add(qualified)
        lines.append(f"# HELP {qualified} {self._help.get(name, name)}")
        lines.append(f"# TYPE {qualified} {_TYPE_LABEL[kind]}")


_default_registry = MetricRegistry()


def get_registry() -> MetricRegistry:
    return _default_registry


@metrics_router.get("/metrics", operation_id="metrics")
async def metrics(request: Request) -> Response:
    """Prometheus text exposition for the service registry (default if unattached)."""
    registry = request.scope.get("ehos.metrics_registry") or get_registry()
    return Response(content=registry.render(), media_type="text/plain; version=0.0.4")


class MetricsMiddleware:
    """ASGI middleware: record duration, hits and 5xx per route."""

    def __init__(self, app, registry: MetricRegistry | None = None):
        self.app = app
        self.registry = registry or _default_registry
        state = getattr(app, "state", None)
        if state is not None and getattr(state, "metrics_registry", None) is None:
            state.metrics_registry = self.registry

    async def __call__(self, scope, receive, send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        scope["ehos.metrics_registry"] = self.registry
        start = time.perf_counter()
        sent_status = {"status": 500}

        async def http_send(message):
            if message["type"] == "http.response.start":
                sent_status["status"] = message["status"]
            await send(message)

        try:
            await self.app(scope, receive, http_send)
        finally:
            elapsed = time.perf_counter() - start
            route = scope.get("path", "").split("?")[0]
            status = sent_status["status"]
            self.registry.inc("http_requests_total", labels={"method": scope.get("method", ""), "route": route})
            self.registry.histogram(
                "http_request_duration_seconds",
                elapsed,
                labels={"method": scope.get("method", ""), "route": route},
            )
            if status >= 500:
                self.registry.inc("http_errors_total", labels={"route": route, "status": str(status)})