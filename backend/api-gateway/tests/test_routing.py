"""Tests for gateway route matching."""

from api_gateway.routing.routes import ROUTES, apply_rewrite, match_route

FRONTEND_PROXY_PREFIXES = {
    "/mpi", "/sched", "/q", "/bill", "/rx", "/pharm", "/lab", "/rad",
    "/inv", "/wf", "/doc", "/ins", "/rpt",
}


def test_route_matching_most_specific_prefix():
    assert match_route("/api/v1/entries/logger")["upstream"].endswith("8100")
    assert match_route("/api/v1/flags")["upstream"].endswith("8100")


def test_ehr_route_is_disambiguated_from_patients():
    ehr = match_route("/api/v1/ehr/patients/abc-123/notes")
    assert ehr is not None
    assert ehr["upstream"].endswith("8502")
    patients = match_route("/api/v1/patients/abc-123")
    assert patients is not None
    assert patients["upstream"].endswith("8501")


def test_route_matching_is_path_prefix_based():
    route = match_route("/api/v1/records/123")
    assert route is not None
    assert route["upstream"].endswith("8200")
    assert match_route("/api/v1/integrity")["upstream"].endswith("8200")


def test_unrouted_path_returns_none():
    assert match_route("/api/v1/nonexistent/1") is None
    assert match_route("/api/v1/") is None


def test_route_auth_requirement():
    assert match_route("/api/v1/records")["requires_auth"] is True
    assert match_route("/api/v1/records")["required_role"] is None
    admin = match_route("/api/v1/flags")
    assert admin["requires_auth"] is True
    assert admin["required_role"] == "administrator"


def test_auth_flow_route_is_public():
    assert match_route("/api/v1/auth/login")["requires_auth"] is False
    assert match_route("/api/v1/auth/register")["required_role"] is None


def test_all_data_plane_prefixes_are_gated():
    for prefix in ("/api/v1/patients", "/api/v1/ehr", "/api/v1/ai",
                   "/api/v1/knowledge", "/api/v1/predictions"):
        assert match_route(prefix + "/anything")["requires_auth"] is True, prefix


def test_notification_routes_resolve():
    assert match_route("/api/v1/templates")["upstream"].endswith("8300")
    assert match_route("/api/v1/send")["upstream"].endswith("8300")


def test_every_route_has_a_coherent_config():
    for prefix, cfg in ROUTES.items():
        assert prefix.startswith("/api/v1/") or prefix in FRONTEND_PROXY_PREFIXES, prefix
        assert cfg["upstream"].startswith("http://")
        assert isinstance(cfg["requires_auth"], bool)
        assert cfg["required_role"] is None or isinstance(cfg["required_role"], str)


def test_frontend_proxy_prefixes_resolve_and_gate():
    for prefix in FRONTEND_PROXY_PREFIXES:
        route = match_route(prefix + "/api/v1/some/resource")
        assert route is not None, prefix
        assert route["requires_auth"] is True, prefix
        assert route["upstream"].startswith("http://"), prefix


def test_frontend_proxy_prefix_is_rewritten_to_canonical_path():
    assert apply_rewrite("/mpi/api/v1/patients/abc-123", match_route("/mpi/api/v1/patients/abc-123")) == "/api/v1/patients/abc-123"
    assert apply_rewrite("/lab/api/v1/laboratory/tests", match_route("/lab/api/v1/laboratory/tests")) == "/api/v1/laboratory/tests"
    canonical = match_route("/api/v1/patients/abc-123")
    assert apply_rewrite("/api/v1/patients/abc-123", canonical) == "/api/v1/patients/abc-123"
    bare = match_route("/pharm")
    assert apply_rewrite("/pharm", bare) == "/"