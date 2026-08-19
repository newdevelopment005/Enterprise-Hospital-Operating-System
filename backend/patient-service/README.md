# patient-service

EHOS patient-service: patient master registry (MPI) with registration, national
ID, insurance capture, biometrics readiness, photos, emergency contacts, medical
alerts, search, patient merge and an audited patient timeline.

## Features

| Feature | Implementation |
|---------|----------------|
| Patient registration | `POST /api/v1/patients` with full demographics + children |
| National ID | `national_identifier` + `patient_identifiers` (multi-issuer, validated) |
| Insurance | `patient_insurance` card snapshot (provider, card/policy/member no.) |
| Biometrics ready | `patient_biometrics` registry + `patients.biometrics_ready` flag |
| Photo | `patient_photos` (base64 upload, bytea or object-store ref) |
| Emergency contact | structured `emergency_contact` + `patient_contacts` |
| Medical alerts | `medical_alerts` (allergies, fall-risk, critical conditions) |
| Patient search | fuzzy `%term%` across name/MRN/number/NID with pagination |
| Patient merge | re-homes children into the survivor, creates SAME_PERSON link |
| Patient timeline | `patient_timeline` source-tagged, audited events |

## Endpoints (prefix `/api/v1/patients`)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/` | Register a patient (201) |
| GET | `/` | Search (`q`, `limit`, `offset`, `include_inactive`) |
| GET | `/{id}` | Patient detail |
| PATCH | `/{id}` | Update demographics |
| GET | `/{id}/timeline` | Patient timeline |
| POST | `/{id}/alerts` | Add medical alert |
| POST | `/{id}/alerts/{alert_id}/resolve` | Resolve an alert |
| POST | `/{id}/biometrics` | Enroll biometric modality |
| POST | `/{id}/photo` | Upload patient photo |
| POST | `/{id}/insurance` | Add insurance card snapshot |
| POST | `/{id}/identifiers` | Add identifier (NID/passport/insurance card) |
| POST | `/{id}/emergency-contact` | Set emergency contact |
| POST | `/merge?survivor_id=&duplicate_id=` | Merge two records |

Responses use the standard EHOS envelope
(`{"success": true, "data": ...}` / `{"success": false, "errorCode": ...}`).

## Validation

- Names: required, no digits. DOB: real past date (1900..today).
- National ID: ISO NID format (3-6-1 digits or 8-16 digits).
- Passport: `XX1234567`. Phone: `+` + 8-15 digits.
- Insurance card/policy/member: `[A-Z0-9-]{6,20}`.
- Duplicate National ID is rejected at registration (409).

## Development

```bash
pip install -e .[test]
pytest                          # unit tests (sqlite in memory)
ruff check src tests            # lint
uvicorn patient_service.main:app --reload --port 8501
```

Database DDL lives in `../database/patient_db/V001__init.sql` and
`V002__registration_features.sql`, applied by `../database/apply.py` to
`ehos_patient` as `ehos_patient_app`. Alembic revisions are available under
`migrations/` for the async engine.