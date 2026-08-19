> **STATUS: SUPERSEDED**
> This early draft has been replaced by the complete, production-ready design in
> **`DATABASE_DESIGN.md`** (tables, PKs, FKs, indexes, constraints, audit, soft delete, history,
> ER diagrams for every service database). Do not implement from this file. Use `DATABASE_DESIGN.md`.

# DATABASE_SCHEMA_MASTER_DESIGN.md

# Enterprise Hospital Operating System (EHOS)

# Master Database Architecture & Data Model Standard

**Version:** 1.0.0  
**Document Type:** Healthcare Enterprise Database Blueprint  
**Audience:** Database Engineers, Backend Engineers, Data Architects, AI Engineers, Security Teams

---

# 1. Purpose

This document defines the master database architecture for EHOS.

The database must support:

- Patient care
- Clinical documentation
- Hospital operations
- Billing
- Inventory
- Human resources
- Analytics
- AI systems
- Security auditing

---

# 2. Database Philosophy

EHOS follows:

> Healthcare data must be accurate, traceable, secure, and available whenever clinicians need it.

---

# 3. Database Architecture Overview

EHOS uses a hybrid data architecture.

```

                 EHOS PLATFORM


                      │


        ┌─────────────┼─────────────┐


        │             │             │


 Operational     Analytical      AI Data

 Databases       Warehouse       Platform


```

---

# 4. Database Technology

Recommended:

Primary transactional database:

- PostgreSQL

Supporting systems:

- Redis
- Object Storage
- Vector Database
- Data Warehouse

---

# 5. Database Separation Strategy

Separate domains:

```

patient_db

ehr_db

billing_db

inventory_db

hr_db

analytics_db

ai_db

audit_db


```

---

# 6. Common Table Standards

Every table should include:

```sql
id

created_at

updated_at

created_by

updated_by

status

version

```

---

# 7. Patient Database

Database:

```
patient_db

```

Purpose:

Store patient identity and demographics.

---

# 8. Patient Table

Table:

```
patients

```

Fields:

```
id

patient_number

first_name

last_name

date_of_birth

gender

contact_information

address

national_identifier

blood_group

emergency_contact

registration_date

```

---

# 9. Patient Identifier Table

Purpose:

Support multiple identifiers.

```
patient_identifiers

```

Fields:

```
id

patient_id

identifier_type

identifier_value

issuer

valid_from

valid_to

```

---

# 10. Patient Consent Table

```
patient_consents

```

Stores:

- Data sharing permissions
- Research permissions
- Telehealth consent

Fields:

```
id

patient_id

consent_type

granted

date_given

expiry_date

```

---

# 11. Encounter Database

Database:

```
ehr_db

```

---

# 12. Encounter Table

Stores visits.

```
encounters

```

Fields:

```
id

patient_id

department_id

provider_id

encounter_type

start_time

end_time

status

```

---

# 13. Clinical Notes Table

```
clinical_notes

```

Stores:

- Doctor notes
- Nursing notes
- AI-generated drafts

Fields:

```
id

encounter_id

author_id

note_type

content

approval_status

approved_by

```

---

# 14. Diagnosis Table

```
diagnoses

```

Fields:

```
id

encounter_id

diagnosis_code

description

diagnosed_by

date

```

---

# 15. Treatment Table

```
treatments

```

Stores:

- Procedures
- Interventions
- Care plans

Fields:

```
id

patient_id

encounter_id

treatment_type

description

provider_id

performed_at

```

---

# 16. Medication Database

Database:

```
pharmacy_db

```

---

# 17. Medication Table

```
medications

```

Fields:

```
id

name

generic_name

manufacturer

strength

form

status

```

---

# 18. Prescription Table

```
prescriptions

```

Fields:

```
id

patient_id

doctor_id

medication_id

dosage

frequency

duration

status

```

---

# 19. Medication Administration Table

Critical clinical record.

```
medication_administration

```

Fields:

```
id

patient_id

medication_id

administered_by

time_given

dose

route

```

---

# 20. Laboratory Database

Database:

```
laboratory_db

```

---

# 21. Laboratory Order Table

```
lab_orders

```

Fields:

```
id

patient_id

doctor_id

test_type

priority

status

ordered_at

```

---

# 22. Laboratory Result Table

```
lab_results

```

Fields:

```
id

order_id

result_value

unit

reference_range

verified_by

verified_at

```

---

# 23. Imaging Database

Database:

```
imaging_db

```

---

Stores:

- DICOM references
- Reports
- Imaging metadata

---

# 24. Appointment Database

Database:

```
scheduling_db

```

---

Table:

```
appointments

```

Fields:

```
id

patient_id

provider_id

department_id

appointment_time

status

reason

```

---

# 25. Billing Database

Database:

```
billing_db

```

---

# 26. Charge Table

```
charges

```

Fields:

```
id

patient_id

encounter_id

item_type

description

amount

created_time

```

---

# 27. Invoice Table

```
invoices

```

Fields:

```
id

patient_id

total_amount

insurance_amount

patient_amount

status

issued_date

```

---

# 28. Payment Table

```
payments

```

Fields:

```
id

invoice_id

amount

payment_method

payment_date

```

---

# 29. Inventory Database

Database:

```
inventory_db

```

---

# 30. Inventory Item Table

```
inventory_items

```

Fields:

```
id

item_name

category

quantity

minimum_level

expiry_date

location

```

---

# 31. Stock Movement Table

Tracks every movement.

```
stock_movements

```

Fields:

```
id

item_id

movement_type

quantity

performed_by

timestamp

reference_event

```

---

# 32. Procurement Table

```
purchase_orders

```

Fields:

```
id

supplier

item_id

quantity

status

order_date

```

---

# 33. HR Database

Database:

```
hr_db

```

---

# 34. Employee Table

```
employees

```

Fields:

```
id

employee_number

name

department

role

qualification

license_number

status

```

---

# 35. Shift Table

```
staff_shifts

```

Fields:

```
id

employee_id

start_time

end_time

shift_type

department

```

---

# 36. Payroll Table

```
payroll_records

```

Fields:

```
id

employee_id

hours_worked

overtime

salary

period

```

---

# 37. AI Database

Database:

```
ai_db

```

---

# 38. AI Model Registry Table

```
ai_models

```

Fields:

```
id

model_name

version

purpose

training_source

approval_status

created_date

```

---

# 39. AI Interaction Audit Table

```
ai_requests

```

Stores:

- User
- Model
- Input reference
- Output reference

---

# 40. Vector Knowledge Database

Stores:

- Medical guidelines
- Hospital policies
- Approved knowledge

---

Example:

```
knowledge_documents

document_embeddings

```

---

# 41. Audit Database

Database:

```
audit_db

```

---

# 42. Audit Log Table

Critical security table.

```
audit_logs

```

Fields:

```
id

user_id

action

resource

timestamp

ip_address

details

```

---

# 43. Event Database

Stores:

```
events

```

Fields:

```
id

event_type

source

payload

timestamp

processed_status

```

---

# 44. Database Security

Required:

- Encryption
- Access control
- Backup
- Monitoring

---

# 45. Database Performance

Implement:

- Indexing
- Query optimization
- Partitioning
- Replication

---

# 46. Backup Strategy

Maintain:

- Daily backups
- Incremental backups
- Offline backup copies

---

# 47. Data Retention

Policies must define:

- Clinical retention
- Financial retention
- Audit retention

---

# 48. Data Governance

Every dataset requires:

- Owner
- Purpose
- Access policy
- Classification

---

# 49. Forbidden Database Practices

Never:

❌ Delete clinical history without policy approval

❌ Allow direct uncontrolled access

❌ Store passwords

❌ Modify medical records without audit

---

# 50. Final Database Principle

> The EHOS database is the permanent memory of the hospital. It must remain accurate, secure, traceable, and available throughout the patient journey.

# END OF DATABASE MASTER DESIGN