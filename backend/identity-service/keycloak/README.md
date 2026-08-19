<# Keep secrets out of git.

Keycloak realm import uses environment variables substituted at runtime via the
Keycloak container. Never commit real client secrets or admin passwords.
See README.md.