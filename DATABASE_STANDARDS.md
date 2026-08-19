# DATABASE_STANDARDS.md

# Enterprise Hospital Operating System (EHOS)

**Version:** 1.0.0  
**Document Type:** Database Architecture & Data Governance Standards  
**Audience:** Database Engineers, Backend Developers, Architects, Security Teams, AI Engineers

---

# 1. Purpose

This document defines the database standards for EHOS.

The objectives are:

- Protect patient information
- Maintain clinical data integrity
- Enable enterprise scalability
- Support audit requirements
- Prevent data corruption
- Ensure reliable system operation

Healthcare data is mission-critical and must be treated as a permanent legal record.

---

# 2. Database Philosophy

EHOS follows these principles:

## Data Ownership

Every service owns its data.

No service may directly access another service's database.

---

## Data Integrity

Clinical information must never be silently changed or deleted.

---

## Auditability

Every important action must be traceable.

---

## Security

All sensitive data must be protected.

---

## Availability

Healthcare systems must remain operational.

---

# 3. Database Architecture

EHOS uses a database-per-service architecture.

```
                 Microservices

                     │

 ┌───────────────────┼───────────────────┐

 │                   │                   │

Patient DB       Billing DB        Inventory DB

 │                   │                   │

PostgreSQL       PostgreSQL        PostgreSQL
```

---

# 4. Approved Database Technologies

## Primary Database

PostgreSQL

Version:

16+

Used for:

- Patient records
- Clinical data
- Finance
- HR
- Inventory
- Scheduling

---

## Cache Database

Redis

Used for:

- Sessions
- Temporary data
- Performance optimization
- Queues

---

## Object Storage

MinIO

Used for:

- Medical documents
- Images
- Reports
- Audio files
- Scanned documents

---

## Vector Database

Qdrant / Milvus

Used for:

- HospitalGPT knowledge retrieval
- Medical document search
- AI memory

---

# 5. Database Naming Standards

## Database Names

Use:

```
service_environment
```

Examples:

```
patient_prod

billing_prod

inventory_prod
```

---

## Table Names

Use:

snake_case

Examples:

```
patients

medical_records

appointment_history
```

---

## Column Names

Use:

snake_case

Examples:

```
patient_id

date_of_birth

created_at
```

---

# 6. Mandatory Table Fields

Every business table must contain:

```sql
id

created_at

updated_at

created_by

updated_by

version

status
```

---

# 7. Primary Keys

Recommended:

UUID

Example:

```
550e8400-e29b-41d4-a716-446655440000
```

Reasons:

- Distributed systems support
- Privacy improvement
- Easier replication

---

# 8. Patient Data Standards

Patient records require special handling.

Mandatory fields:

```
patient_id

medical_record_number

full_name

date_of_birth

gender

contact_information

emergency_contact

registration_date
```

---

# 9. Clinical Data Rules

Clinical information must support:

- Historical versions
- Amendments
- Audit trail
- Author identification
- Timestamp tracking

---

Example:

A doctor's note must never be overwritten.

Instead:

```
Original Note

        +

Amendment

        +

Audit Record
```

---

# 10. Medical Record Versioning

Clinical records use immutable versioning.

Example:

```
Medical Note v1

↓

Correction Added

↓

Medical Note v2

↓

Audit History
```

Previous versions remain available.

---

# 11. Soft Delete Policy

Clinical data must never be permanently deleted.

Instead:

Use:

```
deleted_at

deleted_by

deletion_reason
```

---

# 12. Audit Database

Every service must maintain audit capability.

Audit fields:

```
action

user_id

timestamp

service

record_id

old_value

new_value

ip_address
```

---

Example:

```
Doctor changed medication dose

Who:
Dr Smith

When:
2026-01-01 10:30

Old:
10mg

New:
20mg
```

---

# 13. Sensitive Data Protection

Sensitive information includes:

- Medical history
- Diagnoses
- Medication records
- Laboratory results
- Imaging
- Insurance information

Protection:

- Encryption at rest
- Encryption in transit
- Access control
- Audit logging

---

# 14. Encryption Standards

## Database Encryption

Required:

AES-256

---

## Network Encryption

Required:

TLS 1.3

---

## Backup Encryption

Required:

Encrypted backups only

---

# 15. Database Access Rules

Applications must:

- Use service accounts
- Use least privilege
- Never use admin accounts
- Rotate credentials

---

Forbidden:

```
Application → Superuser Database Access
```

---

# 16. Database Migration Standards

All schema changes require migrations.

Tools:

Recommended:

- Flyway
- Liquibase

---

Example:

```
V001_create_patient_table.sql

V002_add_patient_address.sql

V003_add_insurance_table.sql
```

---

# 17. Indexing Standards

Indexes are required for:

- Patient search
- Medical record lookup
- Appointment queries
- Billing searches

Avoid unnecessary indexes.

Every index must have a performance reason.

---

# 18. Partitioning Strategy

Large tables should support partitioning.

Examples:

Clinical events

Audit logs

Billing transactions

Patient observations

---

Possible partition keys:

- Date
- Hospital location
- Department

---

# 19. Data Retention

Retention rules must follow:

- Local healthcare regulations
- Hospital policy
- Legal requirements

Examples:

Medical records:

Long-term retention

Audit logs:

Permanent or legally defined period

---

# 20. Backup Strategy

Required:

Daily full backup

Hourly incremental backup

Point-in-time recovery

Encrypted storage

Regular restore testing

---

# 21. Disaster Recovery

Database systems must support:

- Replication
- Failover
- Recovery procedures
- Backup verification

---

Recovery objectives:

## RPO

Maximum acceptable data loss:

Defined by hospital policy

---

## RTO

Maximum recovery time:

Defined by hospital criticality

---

# 22. AI Data Requirements

AI systems must not directly access production databases.

Instead:

```
Production Database

        ↓

Approved Data Pipeline

        ↓

Anonymization

        ↓

AI Training Dataset
```

---

# 23. AI Privacy Rules

Before AI processing:

Remove or protect:

- Names
- Addresses
- Identifiers
- Sensitive personal information

unless explicitly authorized.

---

# 24. Data Warehouse

Analytical workloads must not impact clinical databases.

Architecture:

```
Production DB

      ↓

ETL Pipeline

      ↓

Data Warehouse

      ↓

Analytics / AI
```

---

# 25. Database Monitoring

Monitor:

- Query performance
- CPU
- Memory
- Storage
- Replication
- Connections
- Slow queries

Tools:

- Prometheus
- Grafana
- PostgreSQL exporters

---

# 26. Database Security Checklist

✓ Encryption enabled

✓ Access controlled

✓ Audit enabled

✓ Backups tested

✓ Credentials protected

✓ Logs monitored

✓ Vulnerabilities scanned

✓ Disaster recovery tested

---

# 27. Database Anti-Patterns

Never:

❌ Store passwords directly

❌ Delete clinical history

❌ Share databases between services

❌ Disable backups

❌ Store secrets in tables

❌ Allow unrestricted queries

❌ Modify production manually

---

# 28. Final Database Principle

> Healthcare data is not ordinary information. It is a permanent record of human life. Every database decision must protect accuracy, privacy, availability, and trust.