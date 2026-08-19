-- EHOS database initialization (runs once on first Postgres container start).
-- Creates one database per service (database-per-service standard, never shared).
-- All values are overridden in production; DEVELOPMENT ONLY.

CREATE DATABASE ehos_keycloak;
CREATE DATABASE ehos_configuration;
CREATE DATABASE ehos_audit;
CREATE DATABASE ehos_notification;
CREATE DATABASE ehos_gateway;