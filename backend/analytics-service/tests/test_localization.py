"""Tests for country detection, currency conversion and timezone output."""

from analytics_service.service.localization import (
    COUNTRY_PROFILES,
    convert,
    detect_country,
    locale_payload,
    profile_for,
)


def test_explicit_query_country_wins():
    assert detect_country(query_country="tz", headers={"x-country": "EG"}) == "TZ"


def test_header_country_detected():
    assert detect_country(headers={"x-country": "KE"}) == "KE"
    assert detect_country(headers={"cf-ipcountry": "NG"}) == "NG"


def test_accept_language_region_fallback():
    assert detect_country(headers={"accept-language": "ar-EG,ar;q=0.9"}) == "EG"
    assert detect_country(headers={"accept-language": "en-US,en;q=0.9"}) == "US"


def test_default_when_no_hints():
    assert detect_country(default_country="SA") == "SA"


def test_unknown_country_falls_back_to_us_profile():
    assert profile_for("XX").currency_code == "USD"


def test_currency_conversion():
    eg = COUNTRY_PROFILES["EG"]
    assert convert(100.0, eg) == 4850.0
    us = COUNTRY_PROFILES["US"]
    assert convert(250.0, us) == 250.0


def test_locale_payload_fields():
    payload = locale_payload(COUNTRY_PROFILES["TZ"])
    assert payload["countryCode"] == "TZ"
    assert payload["currencyCode"] == "TZS"
    assert payload["timezone"] == "Africa/Dar_es_Salaam"
    assert payload["utcOffset"].startswith("UTC+")
    assert "localTimeIso" in payload and "detectedAt" in payload
