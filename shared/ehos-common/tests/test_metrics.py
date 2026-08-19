"""Tests for the dependency-free Prometheus metrics registry and middleware."""

from __future__ import annotations

import pytest

pytest.importorskip("fastapi")
pytest.importorskip("httpx")
from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from ehos_common.metrics import MetricRegistry, MetricsMiddleware, metrics_router  # noqa: E402


class TestMetricRegistry:
    def test_counter_and_render(self) -> None:
        registry = MetricRegistry()
        registry.inc("http_requests_total", labels={"method": "GET", "route": "/x"})
        registry.inc("http_requests_total", labels={"method": "GET", "route": "/x"})
        out = registry.render()
        assert 'ehos_http_requests_total{method="GET", route="/x"} 2' in out

    def test_labels_are_rendered_per_dimension(self) -> None:
        registry = MetricRegistry()
        registry.inc("http_requests_total", labels={"method": "GET", "route": "/a"})
        registry.inc("http_requests_total", labels={"method": "POST", "route": "/b"})
        out = registry.render()
        assert 'method="GET", route="/a"' in out
        assert 'method="POST", route="/b"' in out
        # two distinct series must not collapse into duplicate label-less lines
        assert out.count("ehos_http_requests_total{") == 2
        assert "ehos_http_requests_total 2" not in out

    def test_label_values_are_escaped(self) -> None:
        registry = MetricRegistry()
        registry.inc("http_requests_total", labels={"route": '/a"b\\c'})
        out = registry.render()
        assert 'route="/a\\"b\\\\c"' in out

    def test_gauge(self) -> None:
        registry = MetricRegistry()
        registry.set("queue_depth", value=3)
        registry.set("queue_depth", value=7)
        assert "ehos_queue_depth 7" in registry.render()

    def test_histogram_buckets_and_count(self) -> None:
        registry = MetricRegistry()
        registry.histogram("http_request_duration_seconds", 0.04)
        registry.histogram("http_request_duration_seconds", 0.2)
        out = registry.render()
        assert "ehos_http_request_duration_seconds_bucket{le=\"+Inf\"} 2" in out
        assert "ehos_http_request_duration_seconds_count 2" in out
        assert "ehos_http_request_duration_seconds_sum 0.24" in out

    def test_invalid_name_rejected(self) -> None:
        registry = MetricRegistry()
        with pytest.raises(ValueError):
            registry.inc("bad name")


def _make_app() -> TestClient:
    registry = MetricRegistry()
    app = FastAPI()
    app.add_middleware(MetricsMiddleware, registry=registry)
    app.include_router(metrics_router)

    @app.get("/hello")
    async def hello():
        return {"ok": True}

    @app.get("/boom")
    async def boom():
        from fastapi import HTTPException

        raise HTTPException(500, "boom")

    client = TestClient(app)
    client.app.state.registry = registry
    return client


class TestMetricsMiddleware:
    def test_endpoint_renders_prometheus(self) -> None:
        client = _make_app()
        client.get("/hello")
        response = client.get("/metrics")
        assert response.status_code == 200
        assert response.headers["content-type"].startswith("text/plain")
        assert "ehos_" in response.text

    def test_requests_recorded(self) -> None:
        client = _make_app()
        registry = client.app.state.registry
        client.get("/hello")
        client.get("/hello")
        out = registry.render()
        assert "ehos_http_requests_total" in out
        assert "ehos_http_request_duration_seconds_count" in out

    def test_errors_recorded(self) -> None:
        client = _make_app()
        registry = client.app.state.registry
        response = client.get("/boom")
        assert response.status_code == 500
        assert "ehos_http_errors_total" in registry.render()