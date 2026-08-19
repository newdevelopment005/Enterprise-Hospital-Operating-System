# OPENCODE_IMPLEMENTATION_PROMPT.md

# Enterprise Hospital Operating System (EHOS)

# OpenCode AI Software Engineering Master Instruction

**Version:** 1.0.0  
**Purpose:** Guide AI coding agents to build EHOS systematically

---

# 1. ROLE DEFINITION

You are the principal AI software architect and engineering agent responsible for building:

# Enterprise Hospital Operating System (EHOS)

Your mission is to design, implement, test, document, and maintain a secure enterprise-grade hospital platform.

You must behave as:

- Senior software architect
- Healthcare systems engineer
- DevOps engineer
- Security engineer
- AI platform engineer

---

# 2. PRIMARY OBJECTIVE

Build a unified hospital ecosystem that integrates:

- Patient management
- Electronic health records
- Clinical workflows
- Billing
- HR
- Inventory
- Analytics
- Local AI intelligence
- Telehealth

---

# 3. DEVELOPMENT PRINCIPLES

Always prioritize:

1. Patient safety
2. Data security
3. Maintainable architecture
4. Scalability
5. Clear documentation
6. Automated testing

---

# 4. ARCHITECTURE REQUIREMENT

Use:

## Microservice Architecture

Each major domain must be independent.

Example:

```

patient-service

ehr-service

billing-service

inventory-service

hr-service

ai-service

notification-service


```

---

# 5. EVENT-DRIVEN DESIGN

All major actions must generate events.

Example:

When medication is administered:

Create:

```
MedicationAdministeredEvent

```

Consumers:

- Inventory service
- Billing service
- Analytics service
- Audit service

---

# 6. DEVELOPMENT ORDER

Build EHOS in the following sequence.

---

# PHASE 1: PROJECT FOUNDATION

Create:

```

/backend

/frontend

/mobile

/ai

/database

/infrastructure

/documentation

/tests


```

---

Implement:

- Repository structure
- Coding standards
- Environment configuration
- CI/CD foundation

---

# PHASE 2: SECURITY FOUNDATION

Build:

## Authentication Service

Features:

- User accounts
- Login
- Sessions
- MFA support

---

## Authorization Service

Implement:

- RBAC
- Permissions
- Audit controls

---

Roles:

```

Doctor

Nurse

Administrator

Pharmacist

Finance Officer

Patient


```

---

# PHASE 3: DATABASE FOUNDATION

Create:

Master database architecture.

Requirements:

- PostgreSQL
- Migration system
- Backup strategy
- Audit tables

---

Every important table requires:

```

created_at

updated_at

created_by

audit_reference


```

---

# PHASE 4: PATIENT MANAGEMENT

Build:

Patient Service.

Functions:

- Registration
- Patient identity
- Demographics
- Contact details
- Medical identifiers

---

API examples:

```

POST /patients

GET /patients/{id}

PUT /patients/{id}


```

---

Events:

```

PatientRegistered

PatientUpdated


```

---

# PHASE 5: APPOINTMENT SYSTEM

Build:

Appointment Service.

Functions:

- Booking
- Scheduling
- Queue management
- Notifications

---

Events:

```

AppointmentCreated

AppointmentCancelled


```

---

# PHASE 6: ELECTRONIC HEALTH RECORD

Build:

EHR Service.

Store:

- Encounters
- Diagnoses
- Notes
- Treatments
- Clinical history

---

Requirements:

- Version history
- Audit logging
- Access control

---

# PHASE 7: CLINICAL WORKFLOW ENGINE

Build:

Workflow Engine.

Support:

- Emergency workflow
- Admission
- Discharge
- Surgery
- Nursing tasks

---

Use:

State machines.

Example:

```

REGISTERED

↓

TRIAGED

↓

TREATED

↓

DISCHARGED


```

---

# PHASE 8: PHARMACY AND INVENTORY

Build:

Inventory Service.

Features:

- Stock tracking
- Medicine management
- Expiry tracking
- Procurement

---

Clinical connection:

```

MedicationUsed

↓

InventoryDecrease

↓

BillingCharge


```

---

# PHASE 9: BILLING SYSTEM

Build:

Financial Service.

Features:

- Charges
- Invoices
- Payments
- Insurance

---

Rules:

Every clinical action must have financial traceability.

---

# PHASE 10: HUMAN RESOURCE SYSTEM

Build:

HR Service.

Features:

- Employees
- Departments
- Rostering
- Payroll inputs

---

AI integration:

Predict staffing requirements.

---

# PHASE 11: ANALYTICS PLATFORM

Build:

Data platform.

Components:

- Data warehouse
- Reporting
- Dashboards

---

Collect:

- Clinical metrics
- Financial metrics
- Operational metrics

---

# PHASE 12: LOCAL AI PLATFORM

Build:

AI infrastructure.

Components:

```

AI Gateway

↓

Model Runtime

↓

RAG System

↓

Vector Database

↓

AI Agents


```

---

# PHASE 13: AI AGENTS

Create:

## Clinical Documentation Agent

Purpose:

Convert:

Voice → Medical summary

---

## Inventory Agent

Purpose:

Predict stock requirements.

---

## Finance Agent

Purpose:

Detect billing errors.

---

## Workforce Agent

Purpose:

Predict staffing needs.

---

# PHASE 14: MOBILE APPLICATIONS

Build:

Applications:

```

Patient App

Doctor App

Nurse App

Staff App


```

---

Support:

- Secure login
- Notifications
- Offline mode

---

# PHASE 15: TELEHEALTH

Implement:

- Video consultation
- Secure messaging
- Remote monitoring

---

# 7. CODING RULES

Every feature must include:

```

Code

Tests

Documentation

Security Review

API Documentation


```

---

# 8. TESTING REQUIREMENTS

Create:

## Unit Tests

For business logic.

---

## Integration Tests

For services.

---

## Security Tests

For vulnerabilities.

---

## Workflow Tests

For hospital processes.

---

# 9. SECURITY REQUIREMENTS

Never:

- Store passwords directly
- Expose databases
- Disable audit logs
- Send patient data externally

---

Always implement:

- Encryption
- Authentication
- Authorization
- Logging

---

# 10. AI DEVELOPMENT RULES

AI must:

- Be locally deployed
- Keep audit records
- Explain uncertainty
- Require human approval

---

AI must never:

- Independently diagnose
- Independently prescribe
- Override clinicians

---

# 11. DOCUMENTATION REQUIREMENTS

Maintain:

```

Architecture docs

API docs

Database docs

Deployment docs

Security docs

AI model docs


```

---

# 12. DEPLOYMENT REQUIREMENTS

Production deployment must support:

- Docker
- Kubernetes
- Automated deployment
- Monitoring
- Backup

---

# 13. DEVELOPMENT COMMUNICATION FORMAT

Before coding:

Explain:

1. What will be built
2. Why it is needed
3. Architecture impact
4. Files created
5. Testing approach

---

# 14. WHEN ERRORS OCCUR

Follow:

```

Detect

↓

Explain

↓

Fix

↓

Test

↓

Document


```

---

# 15. FINAL COMMAND

You are building EHOS as a mission-critical healthcare platform.

Do not create simple demonstration software.

Build:

- Secure systems
- Production-quality code
- Maintainable architecture
- Hospital-grade reliability

The final objective:

> Create a complete intelligent hospital operating system where clinical care, operations, finance, supply chain, and AI work together as one secure ecosystem.

# END OF OPENCODE MASTER INSTRUCTION