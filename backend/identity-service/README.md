# Identity Service (Keycloak)

EHOS identity, SSO, OAuth2/OIDC, and MFA via Keycloak (Phase 0).

## What is provided

- Realm definition in `keycloak/realm-ehos.json` (realm `ehos`).
- Client `ehos-api` for the API gateway + staff/patient portals.
- Roles: `administrator`, `doctor`, `nurse`, `pharmacist`, `finance`, `auditor`.
- Bootstrap user `admin` with the administrator role.
- Browser flow with conditional OTP (MFA).

## Secrets

The realm file uses environment placeholders substituted by the Keycloak
container at startup:

| Placeholder | Env var |
|---|---|
| `${EHOS_CLIENT_SECRET}` | client secret for `ehos-api` |
| `${EHOS_BOOTSTRAP_ADMIN_PASSWORD}` | admin user password |

These are set in the root `.env` (not committed). Secrets are never written to
source files (CODING_STANDARDS.md section 15).

## Realm import

The realm is imported automatically on first container start via the
`--import-realm` flag in docker-compose (see `infrastructure/docker-compose.yml`).

## Notes

- Dev token lifespan: 15 minutes; SSO max 8 hours (tune for compliance).
- Requires TLS at the gateway in production (`sslRequired: external`).
- MFA is enforced through the browser flow; service accounts (machine-to-machine)
  authenticate via client credentials, not usernames.