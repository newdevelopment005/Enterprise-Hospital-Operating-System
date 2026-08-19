# CODING_STANDARDS.md

# Enterprise Hospital Operating System (EHOS)

**Version:** 1.0.0  
**Document Type:** Software Development Standards  
**Audience:** Developers, AI Coding Agents, Architects, Reviewers

---

# 1. Purpose

This document defines mandatory coding standards for the Enterprise Hospital Operating System.

The purpose is to ensure:

- High-quality software
- Secure development practices
- Maintainable code
- Consistent architecture
- Reliable healthcare systems
- Safe AI-assisted development

All human developers and AI coding assistants must follow these standards.

---

# 2. Core Development Principles

## Clean Code

Code must be:

- Easy to understand
- Easy to test
- Easy to modify
- Clearly documented

---

## Simplicity

Prefer:

- Simple solutions
- Clear logic
- Explicit behavior

Avoid:

- Unnecessary complexity
- Clever shortcuts
- Hidden behavior

---

## Maintainability

Every feature should be designed for future developers.

A developer unfamiliar with the code should understand it quickly.

---

# 3. Architecture Rules

EHOS follows:

- Domain-Driven Design
- Clean Architecture
- SOLID Principles
- Microservice Architecture
- Event-Driven Architecture

---

# 4. Service Structure Standard

Every backend service must follow:

```
service-name/

├── src/main/

│   ├── controller/
│   ├── service/
│   ├── domain/
│   ├── repository/
│   ├── entity/
│   ├── dto/
│   ├── mapper/
│   ├── event/
│   ├── security/
│   ├── configuration/
│   └── exception/

├── src/test/

├── migrations/

├── docs/

├── Dockerfile

├── README.md

└── openapi.yaml
```

---

# 5. Naming Standards

## General Rules

Use:

- Clear names
- Full words
- Domain terminology

Avoid:

- Short variables
- Ambiguous names
- Personal abbreviations

---

## Examples

Good:

```
patientRegistrationDate
calculateInvoiceTotal()
MedicationInventoryService
```

Bad:

```
prd
calc()
MIS
```

---

# 6. Class Naming

Use:

PascalCase

Examples:

```
PatientService

BillingController

MedicationRepository
```

---

# 7. Function Naming

Use:

camelCase

Examples:

```
createPatient()

calculateBill()

validatePrescription()
```

Functions should describe actions.

---

# 8. Variable Naming

Use meaningful names.

Good:

```
patientId

medicalRecordNumber

appointmentDate
```

Bad:

```
x

temp

data
```

---

# 9. Database Standards

## Rules

Every table must have:

- Primary key
- Created timestamp
- Updated timestamp
- Audit fields

Example:

```
id

created_at

updated_at

created_by

updated_by
```

---

## Naming

Tables:

snake_case

Examples:

```
patients

medical_records

billing_transactions
```

---

# 10. Database Rules

Never:

- Delete clinical records permanently
- Store passwords directly
- Store secrets in databases
- Share databases between services

---

Clinical data must support:

- Version history
- Audit trails
- Legal retention

---

# 11. API Standards

Every API must:

- Have documentation
- Validate input
- Return standard errors
- Support authentication
- Be versioned

Example:

```
GET /api/v1/patients/{id}

POST /api/v1/patients
```

---

# 12. API Response Standard

Success:

```json
{
 "success": true,
 "data": {},
 "timestamp": ""
}
```

---

Error:

```json
{
 "success": false,
 "errorCode": "",
 "message": "",
 "timestamp": ""
}
```

---

# 13. Exception Handling

Never expose:

- Database errors
- Stack traces
- Internal details

to users.

---

Example:

Bad:

```
SQL Error: connection failed at line 245
```

Good:

```
SERVICE_UNAVAILABLE
Please try again later
```

---

# 14. Logging Standards

Every service must implement structured logging.

Required fields:

```
timestamp

service

userId

requestId

operation

result

duration
```

---

Never log:

- Passwords
- Medical secrets
- Authentication tokens
- Full patient records

---

# 15. Security Standards

Mandatory:

- Input validation
- Authentication checks
- Authorization checks
- Encryption
- Secure headers
- Audit logging

---

Never:

- Hardcode credentials
- Disable security checks
- Store secrets in source code

---

# 16. Event Standards

All events must be:

- Immutable
- Versioned
- Documented

Example:

```json
{
"id":"12345",
"type":"PatientRegistered",
"version":"1",
"time":"2026-01-01",
"payload":{}
}
```

---

# 17. Event Processing Rules

Consumers must be:

- Idempotent
- Fault tolerant
- Retry capable

---

Example:

If an invoice event is received twice:

The system must not create two invoices.

---

# 18. Testing Standards

Every feature requires:

## Unit Tests

Minimum:

80% coverage target

---

## Integration Tests

Required for:

- Database operations
- APIs
- Events

---

## Security Tests

Required for:

- Authentication
- Authorization
- Data access

---

## Performance Tests

Required for:

- Critical clinical workflows
- Billing
- Search
- AI services

---

# 19. AI Generated Code Rules

AI-generated code must:

- Follow this document
- Include tests
- Include documentation
- Explain architectural decisions
- Avoid unnecessary dependencies

AI must not:

- Create insecure shortcuts
- Ignore existing patterns
- Modify unrelated modules
- Remove security controls

---

# 20. Frontend Standards

React applications must use:

- TypeScript
- Component-based design
- Reusable components
- State management pattern
- Form validation
- Accessibility standards

---

# 21. Mobile Standards

Flutter applications must:

- Support offline mode
- Encrypt local storage
- Validate all inputs
- Protect patient information

---

# 22. Python AI Service Standards

AI services must include:

```
src/

├── models/

├── services/

├── pipelines/

├── api/

├── tests/

└── configuration/
```

---

AI services must support:

- Model versioning
- Monitoring
- Evaluation
- Rollback

---

# 23. Documentation Requirements

Every module requires:

README.md

Architecture diagram

API documentation

Database documentation

Deployment instructions

Testing instructions

---

# 24. Code Review Rules

Every change must be reviewed for:

- Security
- Architecture compliance
- Performance
- Testing
- Documentation

---

# 25. Forbidden Practices

Never:

❌ Build unnecessary monoliths

❌ Skip tests

❌ Bypass authentication

❌ Store sensitive data in logs

❌ Share databases between services

❌ Hardcode configuration

❌ Ignore errors

❌ Deploy untested code

---

# 26. Definition of Done

A feature is complete only when:

✓ Code written

✓ Tests added

✓ Security reviewed

✓ Documentation updated

✓ API documented

✓ Events documented

✓ Deployment verified

---

# 27. Final Coding Principle

> Write software as if it will protect millions of patients. Every line must prioritize safety, security, reliability, and maintainability.