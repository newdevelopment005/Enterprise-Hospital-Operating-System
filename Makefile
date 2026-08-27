# EHOS Makefile
# Enterprise Hospital Operating System - development helpers

SHELL := /bin/bash

COMPOSE_FILE := infrastructure/docker-compose.yml

.DEFAULT_GOAL := help

.PHONY: help
help: ## Show available targets
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-22s\033[0m %s\n", $$1, $$2}'

.PHONY: init
init: ## Copy .env.example to .env and create data directories
	cp -n .env.example .env || true
	@mkdir -p data/minio data/postgres

.PHONY: build
build: ## Build all service images
	docker compose build

.PHONY: up
up: ## Start the full stack
	docker compose up -d

.PHONY: down
down: ## Stop the full stack
	docker compose down

.PHONY: logs
logs: ## Tail logs for all services
	docker compose logs -f --tail=100

.PHONY: ps
ps: ## Show running containers
	docker compose ps

.PHONY: kafka-topics
kafka-topics: ## List Kafka topics
	docker compose exec kafka kafka-topics.sh --list --bootstrap-server localhost:9092

.PHONY: seed-keycloak
seed-keycloak: ## Import the EHOS Keycloak realm
	@echo "Realm import runs automatically on first Keycloak start (see backend/identity-service/keycloak)."

.PHONY: test
test: ## Run all service tests
	@for svc in backend/configuration-service backend/audit-service backend/notification-service backend/api-gateway backend/authentication-service backend/patient-service backend/ehr-service backend/appointment-service backend/queue-service backend/billing-service backend/prescription-service backend/pharmacy-service backend/laboratory-service backend/radiology-service backend/inventory-service backend/workflow-service backend/clinical-documentation-service backend/insurance-service backend/reporting-service backend/knowledge-service backend/ai-service backend/prediction-service backend/analytics-service; do \
		echo "==> $$svc"; \
		(cd $$svc && python -m pytest -q) || exit 1; \
	done

.PHONY: lint
lint: ## Run ruff lint on all services
	@for svc in backend/configuration-service backend/audit-service backend/notification-service backend/api-gateway backend/authentication-service backend/patient-service backend/ehr-service backend/appointment-service backend/queue-service backend/billing-service backend/prescription-service backend/pharmacy-service backend/laboratory-service backend/radiology-service backend/inventory-service backend/workflow-service backend/clinical-documentation-service backend/insurance-service backend/reporting-service backend/knowledge-service backend/ai-service backend/prediction-service backend/analytics-service shared/ehos-common; do \
		echo "==> $$svc"; \
		(cd $$svc && python -m ruff check src tests) || exit 1; \
	done

.PHONY: migrate
migrate: ## Apply all SQL migrations (shared + per-db V*__*.sql)
	python database/apply.py
