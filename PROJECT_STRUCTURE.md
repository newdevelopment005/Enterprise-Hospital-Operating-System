# PROJECT_STRUCTURE.md

# Enterprise Hospital Operating System (EHOS)

**Version:** 1.0.0  
**Document Type:** Repository Structure & Organization  
**Audience:** Software Architects, Developers, DevOps Engineers, AI Engineers

---

# 1. Purpose

This document defines the standard repository structure for the Enterprise Hospital Operating System (EHOS).

Objectives:

- Keep the repository organized and scalable.
- Separate domains and responsibilities.
- Enable independent development of services.
- Support CI/CD pipelines.
- Support multiple development teams.
- Support AI-assisted development.

---

# 2. Top-Level Repository Structure

```text
ehos/
│
├── docs/
├── backend/
├── frontend/
├── mobile/
├── ai/
├── integrations/
├── infrastructure/
├── deployment/
├── monitoring/
├── security/
├── scripts/
├── shared/
├── sdk/
├── database/
├── testing/
├── tools/
├── examples/
├── assets/
├── config/
├── .github/
├── .devcontainer/
├── .vscode/
├── docker-compose.yml
├── Makefile
├── README.md
├── LICENSE
└── CHANGELOG.md
```

---

# 3. Documentation (`docs/`)

```text
docs/
├── README.md
├── MASTER_BLUEPRINT.md
├── SYSTEM_OVERVIEW.md
├── ARCHITECTURE.md
├── PROJECT_STRUCTURE.md
├── TECH_STACK.md
├── CODING_STANDARDS.md
├── DATABASE.md
├── SECURITY.md
├── AI_PLATFORM.md
├── AI_AGENTS.md
├── EVENT_BUS.md
├── DEPLOYMENT.md
├── API_SPECIFICATION.md
├── ROADMAP.md
├── TESTING_STRATEGY.md
└── CHANGELOG.md
```

---

# 4. Backend (`backend/`)

Each microservice has its own directory and is independently deployable.

```text
backend/
├── api-gateway/
├── auth-service/
├── patient-service/
├── appointment-service/
├── triage-service/
├── emergency-service/
├── ehr-service/
├── pharmacy-service/
├── laboratory-service/
├── radiology-service/
├── surgery-service/
├── icu-service/
├── bed-service/
├── telemedicine-service/
├── billing-service/
├── finance-service/
├── insurance-service/
├── hr-service/
├── payroll-service/
├── inventory-service/
├── procurement-service/
├── vendor-service/
├── asset-service/
├── notification-service/
├── reporting-service/
├── audit-service/
├── search-service/
└── configuration-service/
```

Each service contains:

```text
service-name/
├── src/
├── tests/
├── migrations/
├── docs/
├── Dockerfile
├── docker-compose.yml
├── README.md
├── openapi.yaml
└── pom.xml (or equivalent)
```

---

# 5. Frontend (`frontend/`)

```text
frontend/
├── staff-portal/
├── patient-portal/
├── executive-dashboard/
├── admin-console/
├── pharmacy-console/
├── laboratory-console/
├── radiology-console/
└── shared-ui/
```

Shared UI components, themes, and design systems should reside in `shared-ui/`.

---

# 6. Mobile (`mobile/`)

```text
mobile/
├── clinician-app/
├── nursing-app/
├── patient-app/
├── logistics-app/
└── shared/
```

---

# 7. AI Platform (`ai/`)

```text
ai/
├── hospitalgpt/
├── gateway/
├── prompt-manager/
├── model-manager/
├── inference/
├── embeddings/
├── vector-search/
├── rag/
├── speech/
├── ocr/
├── analytics/
├── forecasting/
├── medical-coding/
├── ai-agents/
├── evaluation/
└── shared/
```

---

# 8. Integrations (`integrations/`)

```text
integrations/
├── hl7/
├── fhir/
├── dicom/
├── pacs/
├── lis/
├── insurance/
├── payment/
├── sms/
├── email/
└── medical-devices/
```

Each integration should be isolated and versioned.

---

# 9. Infrastructure (`infrastructure/`)

```text
infrastructure/
├── kubernetes/
├── helm/
├── terraform/
├── ansible/
├── networking/
├── storage/
├── gpu/
└── secrets/
```

---

# 10. Deployment (`deployment/`)

```text
deployment/
├── development/
├── staging/
├── production/
└── disaster-recovery/
```

---

# 11. Monitoring (`monitoring/`)

```text
monitoring/
├── prometheus/
├── grafana/
├── loki/
├── tempo/
├── alertmanager/
└── dashboards/
```

---

# 12. Security (`security/`)

```text
security/
├── policies/
├── certificates/
├── key-management/
├── vulnerability-scans/
└── compliance/
```

---

# 13. Shared Libraries (`shared/`)

Reusable libraries:

```text
shared/
├── authentication/
├── authorization/
├── logging/
├── auditing/
├── validation/
├── events/
├── messaging/
├── configuration/
├── utilities/
└── healthcare/
```

Avoid placing domain-specific business logic here.

---

# 14. SDK (`sdk/`)

Internal client SDKs:

```text
sdk/
├── java/
├── dotnet/
├── python/
├── javascript/
└── flutter/
```

---

# 15. Database (`database/`)

```text
database/
├── schemas/
├── migrations/
├── seeds/
├── backups/
├── diagrams/
└── scripts/
```

---

# 16. Testing (`testing/`)

```text
testing/
├── unit/
├── integration/
├── contract/
├── performance/
├── security/
├── end-to-end/
└── datasets/
```

---

# 17. Tools (`tools/`)

Developer utilities:

```text
tools/
├── generators/
├── linters/
├── formatters/
├── validators/
└── migration-tools/
```

---

# 18. Assets (`assets/`)

```text
assets/
├── logos/
├── icons/
├── diagrams/
└── ui-mockups/
```

---

# 19. Configuration (`config/`)

```text
config/
├── development/
├── testing/
├── staging/
└── production/
```

Store only non-sensitive configuration. Secrets belong in a dedicated secret-management solution.

---

# 20. Repository Rules

- Each service must have its own `README.md`.
- Services own their own data and APIs.
- Shared code must remain generic.
- Configuration is environment-specific.
- Infrastructure is defined as code.
- Documentation must be updated with every architectural change.

---

# 21. Naming Conventions

Directories:

- lowercase
- kebab-case

Examples:

- `patient-service`
- `inventory-service`
- `hospitalgpt`

Avoid abbreviations unless they are standard healthcare terms (e.g., `ehr`, `icu`, `hl7`).

---

# 22. Future Expansion

Reserve space for future domains, including:

- Research Platform
- Population Health
- Clinical Trials
- Robotics
- IoT Medical Devices
- Digital Twin
- Genomics
- AI Training Pipelines
- Disaster Response
- National Health Exchange

The repository structure is intentionally modular so new capabilities can be added without disrupting existing services.