# ehr-service

EHOS ehr-service: the Clinical EHR. Every module is linked to the Patient
(`/api/v1/patients/{patient_id}/...`, cross-db reference to patient-service).

## Modules

| Module | Table(s) | Endpoint group |
|--------|----------|----------------|
| Encounters | `encounters` | `/encounters` |
| SOAP Notes | `clinical_notes` (note_type SOAP, structured S/O/A/P) | `/soap` |
| Clinical Notes | `clinical_notes` + versions + amendments | `/notes` |
| Progress Notes | `clinical_notes` (note_type PROGRESS) | `/progress-notes` |
| Discharge Summary | `clinical_notes` (note_type DISCHARGE) | `/discharge-summary` |
| Vitals | `vital_signs` (single + batch) | `/vitals` |
| Diagnoses | `diagnoses` (ICD-10/11/SNOMED-CT) | `/diagnoses` |
| Medications | `medications` (clinical medication orders) | `/medications` |
| Orders | `clinical_orders` (LAB/IMAGING/PROCEDURE/CONSULT/NURSING/DIET/BLOOD) | `/orders` |
| Allergies | `patient_allergies` | `/allergies` |
| Problem List | `problem_list` | `/problems` |
| Medical History | `medical_history` (past/surgical/family/social/…) | `/medical-history` |
| Clinical Timeline | `clinical_timeline` (source-tagged event feed) | `/timeline` |
| Patient Chart (aggregate) | all of the above | `/chart` |

Schema: `database/ehr_db/V001__init.sql` (core) + `V002__clinical_modules.sql`
(medications, orders, allergies, problem list, medical history, timeline),
applied to `ehos_ehr` as `ehos_ehr_app` by `database/apply.py`. PHI tables use
RLS and `ehos_make_history()`.

## Notes

- Notes are versioned: `PATCH /notes/{id}` snapshots the previous revision into
  `clinical_note_versions` and bumps `version`; signed notes (`POST
  /notes/{id}/sign`) are immutable and reject further edits (409).
- Diagnoses are encounter-scoped (V001 DDL: `diagnoses.encounter_id NOT NULL`),
  so open an encounter first.
- Allergies are unique per `(patient_id, allergen, allergen_type)`; duplicates
  return 409.
- Every mutation writes a `clinical_timeline` event (NOTE_CREATED,
  VITALS_RECORDED, MEDICATION_ORDERED, …).

## Development

```bash
pip install -e .[test]
pytest                                # unit tests (sqlite in memory)
ruff check src tests                  # lint
uvicorn ehr_service.main:app --reload --port 8502
```

OpenAPI: `openapi.yaml`; live docs at `/docs`.