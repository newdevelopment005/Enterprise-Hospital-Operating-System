# authentication-service

EHOS authentication-service: JWT issuance/validation, opaque refresh-token
rotation with reuse detection, RBAC + ABAC authorization, TOTP MFA, password
policies, session management, immutable auth audit log, and an OIDC discovery
endpoint so the platform stays SSO/Keycloak-ready.

## Responsibilities

- **verify** passwords with bcrypt and enforce the configured password policy
  (length, character classes, common-password blacklist, history reuse, max age).
- **issue** RS256 access JWTs carrying roles and effective permissions.
- **rotate** opaque refresh tokens on each use; reuse after rotation revokes the
  entire token family and its sessions.
- **enforce** concurrent-session limits and account lockout after repeated failures.
- **record** every security-relevant event in `auth_events` and publish
  `UserAuthenticated` / `PasswordChanged` events on `auth.topic`.
- **expose** OIDC discovery at `.well-known/openid-configuration`.

## Endpoints (prefix `/api/v1/auth`)

| Method | Path                     | Auth  | Description                              |
|--------|--------------------------|-------|------------------------------------------|
| POST   | `/register`              | no    | Register a new account                   |
| POST   | `/login`                 | no    | Login (returns token pair or MFA chase)  |
| POST   | `/mfa/verify`            | no    | Complete login with an MFA code          |
| POST   | `/refresh`               | no    | Rotate a refresh token                   |
| POST   | `/logout`                | no    | Revoke refresh token + session           |
| POST   | `/introspect`            | no    | Validate an access token                 |
| GET    | `/policy/password`       | no    | Current password policy                  |
| GET    | `/.well-known/...`       | no    | OIDC discovery document                  |
| GET    | `/me`                    | yes   | Current profile, roles, permissions      |
| PUT    | `/me/password`           | yes   | Change own password                      |
| GET    | `/sessions`              | yes   | List my sessions                         |
| DELETE | `/sessions/{id}`         | yes   | Revoke one session                       |
| POST   | `/mfa/enroll`, `/mfa/confirm`, GET `/mfa` | yes | TOTP enrollment          |
| GET    | `/roles`, `/permissions` | yes   | RBAC listings                            |
| POST   | `/roles`, `/permissions` | yes   | RBAC creation                            |
| GET/POST | `/users/{id}/roles`, `/roles/{code}/permissions` | yes | Assignments      |
| GET/POST | `/abac/policies`, `/abac/check` | yes | ABAC management & eval           |
| GET    | `/users`                 | yes   | List users (admin)                       |
| DELETE | `/users/{id}`            | yes   | Deactivate a user                        |

Responses use the standard EHOS envelope:
`{"success": true, "data": ...}` / `{"success": false, "errorCode": "...", "message": "..."}`.

## Configuration

Subclasses `ehos_common.config.ServiceSettings` (see `src/auth_service/configuration.py`).
In development, when no `jwt_private_key_pem` is provided, an ephemeral RSA key
pair is generated at startup.

## Development

```bash
pip install -e .[test]
pytest                      # run unit tests (sqlite in memory)
ruff check src tests        # lint
uvicorn auth_service.main:app --reload --port 8500
```

Database migrations: alembic revisions target `ehos_identity`; the canonical
DDL lives in `../database/identity_db/V001__init.sql` + `V002__auth.sql` and is
applied by `../database/apply.py`.