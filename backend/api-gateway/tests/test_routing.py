"""Tests for gateway route matching."""

from api_gateway.routing.routes import ROUTES, match_route


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
        assert prefix.startswith("/api/v1/")
        assert cfg["upstream"].startswith("http://")
        assert isinstance(cfg["requires_auth"], bool)
        assert cfg["required_role"] is None or isinstance(cfg["required_role"], str)