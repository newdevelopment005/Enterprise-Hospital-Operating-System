"""Country resolution, currency conversion and timezone localization.

The system predicts the country the deployment is used in by combining, in
priority order:

1. explicit ``?country=XX`` query parameter (or ``X-Country`` / ``CF-IPCountry``
   request headers set by an edge proxy or operator),
2. the region subtag of the ``Accept-Language`` header,
3. the configured ``default_country_code``.

Every stored metric is denominated in the base currency (USD); read endpoints
convert amounts to the resolved country's currency and expose its IANA
timezone so clients render local time.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class CountryProfile:
    code: str
    name: str
    currency_code: str
    currency_symbol: str
    timezone: str
    locale_tag: str
    exchange_rate: float  # units of local currency per 1 unit of base currency


COUNTRY_PROFILES: dict[str, CountryProfile] = {
    "EG": CountryProfile("EG", "Egypt", "EGP", "E£", "Africa/Cairo", "ar-EG", 48.5),
    "TZ": CountryProfile("TZ", "Tanzania", "TZS", "TSh", "Africa/Dar_es_Salaam", "en-TZ", 2540.0),
    "KE": CountryProfile("KE", "Kenya", "KES", "KSh", "Africa/Nairobi", "en-KE", 129.0),
    "NG": CountryProfile("NG", "Nigeria", "NGN", "₦", "Africa/Lagos", "en-NG", 1540.0),
    "SA": CountryProfile("SA", "Saudi Arabia", "SAR", "﷼", "Asia/Riyadh", "ar-SA", 3.75),
    "AE": CountryProfile("AE", "United Arab Emirates", "AED", "د.إ", "Asia/Dubai", "en-AE", 3.67),
    "IN": CountryProfile("IN", "India", "INR", "₹", "Asia/Kolkata", "en-IN", 83.5),
    "GB": CountryProfile("GB", "United Kingdom", "GBP", "£", "Europe/London", "en-GB", 0.79),
    "US": CountryProfile("US", "United States", "USD", "$", "America/New_York", "en-US", 1.0),
}

FALLBACK = COUNTRY_PROFILES["US"]


class LocalizationError(Exception):
    def __init__(self, message: str, status_code: int = 400):
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def profile_for(country_code: str | None) -> CountryProfile:
    if not country_code:
        return FALLBACK
    return COUNTRY_PROFILES.get(country_code.strip().upper(), FALLBACK)


def detect_country(
    query_country: str | None = None,
    headers: dict[str, str] | None = None,
    default_country: str = "EG",
) -> str:
    """Resolve the ISO-3166 alpha-2 country for this request."""
    if query_country and len(query_country.strip()) == 2 and query_country.strip().isalpha():
        return query_country.strip().upper()
    headers = headers or {}
    for header in ("x-country", "cf-ipcountry"):
        value = headers.get(header)
        if value and len(value.strip()) == 2 and value.strip().isalpha():
            return value.strip().upper()
    accept_language = headers.get("accept-language", "")
    for part in accept_language.split(","):
        region = part.split(";")[0].strip().split("-")[-1]
        if len(region) == 2 and region.isalpha() and region.isupper():
            return region.upper()
    return (default_country or FALLBACK.code).upper()


def convert(amount_base: float, profile: CountryProfile) -> float:
    """Convert a base-currency amount into the country's currency."""
    return amount_base * profile.exchange_rate


def local_now(profile: CountryProfile) -> tuple[datetime, str]:
    """Current wall-clock time in the country's timezone plus its UTC offset."""
    now_local = datetime.now(ZoneInfo(profile.timezone))
    offset = now_local.strftime("%z")
    pretty = f"UTC{offset[:3]}:{offset[3:]}"
    return now_local, pretty


def locale_payload(profile: CountryProfile) -> dict:
    now_local, utc_offset = local_now(profile)
    return {
        "countryCode": profile.code,
        "countryName": profile.name,
        "currencyCode": profile.currency_code,
        "currencySymbol": profile.currency_symbol,
        "timezone": profile.timezone,
        "localeTag": profile.locale_tag,
        "exchangeRate": profile.exchange_rate,
        "utcOffset": utc_offset,
        "localTimeIso": now_local.isoformat(),
        "detectedAt": datetime.now(UTC).isoformat(),
    }
