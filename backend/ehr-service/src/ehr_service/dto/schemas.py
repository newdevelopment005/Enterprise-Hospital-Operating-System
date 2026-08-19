"""Pydantic DTOs for the ehr-service REST API.

Field names snake_case to match the SQL DDL. Validation mirrors the database
CHECK constraints plus a few clinical sanity rules (future dates, required
values, measurable-vitals handling).
"""

from __future__ import annotations

from datetime import UTC, date, datetime

from pydantic import BaseModel, Field, field_validator, model_validator

# --- shared validation helpers -------------------------------------------------


def _not_future_date(value: date | None) -> date | None:
    if value is None:
        return value
    if value > date.today():
        raise ValueError("date cannot be in the future")
    return value


def _aware(value: datetime | None) -> datetime | None:
    if value is not None and value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value


# --- encounters ----------------------------------------------------------------


class EncounterIn(BaseModel):
    encounter_type: str = Field(pattern="^(OUTPATIENT|INPATIENT|ED|SURGERY|TELEHEALTH|HOME)$")
    department_id: str | None = None
    provider_id: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    visit_number: str | None = Field(default=None, max_length=50)
    reason: str | None = Field(default=None, max_length=2000)

    @field_validator("start_time", "end_time", mode="before")
    @classmethod
    def _default_and_aware(cls, value: datetime | None) -> datetime | None:
        return _aware(value)

    @model_validator(mode="after")
    def _end_after_start(self) -> EncounterIn:
        if self.start_time and self.end_time and self.end_time < self.start_time:
            raise ValueError("end_time must be on or after start_time")
        return self


class EncounterOut(BaseModel):
    id: str
    patient_id: str
    encounter_type: str
    visit_number: str | None
    department_id: str | None
    provider_id: str | None
    start_time: datetime
    end_time: datetime | None
    reason: str | None
    status: str
    created_at: datetime


# --- notes (clinical / SOAP / progress / discharge) ----------------------------


class NoteIn(BaseModel):
    note_type: str = Field(
        pattern="^(SOAP|PROGRESS|ADMISSION|DISCHARGE|CONSULT|NURSING|OPNOTE|AI_DRAFT)$"
    )
    content: str = Field(min_length=1, max_length=100000)
    content_struct: dict | None = None
    encounter_id: str | None = None
    author_id: str = Field(min_length=1, max_length=36)
    author_role: str | None = Field(default=None, max_length=100)
    source: str | None = Field(default=None, pattern="^(MANUAL|AI_DRAFT|VOICE|IMPORTED)$")
    change_reason: str | None = Field(default=None, max_length=1000)


class SOAPNoteIn(BaseModel):
    subjective: str = Field(default="", max_length=40000)
    objective: str = Field(default="", max_length=40000)
    assessment: str = Field(default="", max_length=40000)
    plan: str = Field(default="", max_length=40000)
    encounter_id: str | None = None
    author_id: str = Field(min_length=1, max_length=36)
    author_role: str | None = Field(default=None, max_length=100)
    source: str | None = Field(default=None, pattern="^(MANUAL|AI_DRAFT|VOICE|IMPORTED)$")

    @model_validator(mode="after")
    def _not_blank(self) -> SOAPNoteIn:
        if not any((self.subjective, self.objective, self.assessment, self.plan)):
            raise ValueError("at least one SOAP section is required")
        return self


class ProgressNoteIn(BaseModel):
    content: str = Field(min_length=1, max_length=100000)
    progress_note: dict | None = None
    encounter_id: str | None = None
    author_id: str = Field(min_length=1, max_length=36)
    author_role: str | None = Field(default=None, max_length=100)
    change_reason: str | None = Field(default=None, max_length=1000)


class DischargeSummaryIn(BaseModel):
    admission_date: date | None = None
    discharge_date: date | None = None
    admitting_diagnosis: str | None = Field(default=None, max_length=2000)
    discharge_diagnosis: str | None = Field(default=None, max_length=2000)
    summary: str = Field(min_length=1, max_length=100000)
    discharge_condition: str | None = Field(default=None, max_length=2000)
    medications_on_discharge: str | None = Field(default=None, max_length=10000)
    follow_up_plan: str | None = Field(default=None, max_length=10000)
    patient_instructions: str | None = Field(default=None, max_length=10000)
    encounter_id: str | None = None
    author_id: str = Field(min_length=1, max_length=36)
    author_role: str | None = Field(default=None, max_length=100)

    @field_validator("admission_date", "discharge_date")
    @classmethod
    def _dates(cls, value: date | None) -> date | None:
        return _not_future_date(value)

    @model_validator(mode="after")
    def _discharge_after_admission(self) -> DischargeSummaryIn:
        if self.admission_date and self.discharge_date and self.discharge_date < self.admission_date:
            raise ValueError("discharge_date must be on or after admission_date")
        return self


class AmendmentIn(BaseModel):
    amendment: str = Field(min_length=1, max_length=20000)
    author_id: str | None = Field(default=None, min_length=1)


class NoteOut(BaseModel):
    id: str
    patient_id: str
    encounter_id: str | None
    note_type: str
    content: str
    content_struct: dict | None
    author_id: str | None
    author_role: str | None
    approval_status: str
    source: str | None
    created_at: datetime
    updated_at: datetime


class AmendmentOut(BaseModel):
    id: str
    note_id: str
    author_id: str | None
    amendment: str
    added_at: datetime


# --- vitals --------------------------------------------------------------------


class VitalIn(BaseModel):
    vital_type: str = Field(
        pattern="^(BP|HR|RR|TEMP|SPO2|WEIGHT|HEIGHT|BMI|GLUCOSE|PAIN|GCS)$"
    )
    value_numeric: float | None = None
    value_text: str | None = Field(default=None, max_length=100)
    unit: str | None = Field(default=None, max_length=20)
    recorded_at: datetime | None = None
    recorded_by: str | None = None
    encounter_id: str | None = None
    notion: dict | None = None

    @field_validator("recorded_at", mode="before")
    @classmethod
    def _aware_dt(cls, value: datetime | None) -> datetime | None:
        return _aware(value)

    @model_validator(mode="after")
    def _has_value(self) -> VitalIn:
        if self.value_numeric is None and not (self.value_text or "").strip():
            raise ValueError("a numeric or text value is required")
        return self


class VitalBatchIn(BaseModel):
    readings: list[VitalIn] = Field(min_length=1, max_length=50)
    encounter_id: str | None = None


class VitalOut(BaseModel):
    id: str
    patient_id: str
    encounter_id: str | None
    vital_type: str
    value_numeric: float | None
    value_text: str | None
    unit: str | None
    recorded_at: datetime
    recorded_by: str | None


# --- diagnoses -----------------------------------------------------------------


class DiagnosisIn(BaseModel):
    diagnosis_code: str = Field(min_length=1, max_length=50)
    code_system: str = Field(default="ICD-10", pattern="^(ICD-10|ICD-11|SNOMED-CT)$")
    description: str = Field(min_length=1, max_length=2000)
    type: str = Field(default="WORKING", pattern="^(WORKING|PROVISIONAL|FINAL|ADMISSION|DISCHARGE|DEATH)$")
    encounter_id: str = Field(min_length=1, max_length=36)
    onset_date: date | None = None
    diagnosed_by: str = Field(min_length=1, max_length=36)
    present_on_admission: bool | None = None

    @field_validator("onset_date")
    @classmethod
    def _onset(cls, value: date | None) -> date | None:
        return _not_future_date(value)


class DiagnosisResolveIn(BaseModel):
    resolved_by: str | None = Field(default=None, min_length=1)
    resolved_at: datetime | None = None

    @field_validator("resolved_at", mode="before")
    @classmethod
    def _aware_dt(cls, value: datetime | None) -> datetime | None:
        return _aware(value)


class DiagnosisOut(BaseModel):
    id: str
    patient_id: str
    encounter_id: str | None
    diagnosis_code: str
    code_system: str
    description: str
    type: str
    onset_date: date | None
    diagnosed_by: str | None
    diagnosed_at: datetime
    resolved_at: datetime | None
    status: str


# --- medications ---------------------------------------------------------------


class MedicationIn(BaseModel):
    medication_name: str = Field(min_length=1, max_length=255)
    medication_id: str | None = None
    strength: str | None = Field(default=None, max_length=100)
    dose: float | None = None
    dose_unit: str | None = Field(default=None, max_length=20)
    route: str = Field(
        default="ORAL",
        pattern="^(ORAL|IV|IM|SC|TOPICAL|INHALED|RECTAL|SUBLINGUAL|OTIC|OPHTHALMIC|NASAL|OTHER)$",
    )
    frequency: str | None = Field(default=None, max_length=100)
    duration: str | None = Field(default=None, max_length=100)
    prn: bool = False
    start_date: date | None = None
    end_date: date | None = None
    indication: str | None = Field(default=None, max_length=2000)
    instructions: str | None = Field(default=None, max_length=5000)
    prescriber_id: str | None = Field(default=None, min_length=1)
    encounter_id: str | None = None

    @field_validator("start_date", "end_date")
    @classmethod
    def _dates(cls, value: date | None) -> date | None:
        return _not_future_date(value)

    @model_validator(mode="after")
    def _end_after_start(self) -> MedicationIn:
        if self.start_date and self.end_date and self.end_date < self.start_date:
            raise ValueError("end_date must be on or after start_date")
        return self


class MedicationUpdateIn(BaseModel):
    status: str | None = Field(default=None, pattern="^(PLANNED|ACTIVE|COMPLETED|DISCONTINUED|HOLD|CANCELLED)$")
    instructions: str | None = None
    discontinued_by: str | None = Field(default=None, min_length=1)
    distribution_forbid: bool = False


class MedicationOut(BaseModel):
    id: str
    patient_id: str
    encounter_id: str | None
    medication_name: str
    strength: str | None
    dose: float | None
    dose_unit: str | None
    route: str
    frequency: str | None
    prn: bool
    start_date: date | None
    end_date: date | None
    indication: str | None
    instructions: str | None
    prescriber_id: str | None
    prescribed_at: datetime
    discontinued_at: datetime | None
    status: str


# --- orders --------------------------------------------------------------------


class ClinicalOrderIn(BaseModel):
    order_type: str = Field(pattern="^(LAB|IMAGING|PROCEDURE|CONSULT|NURSING|DIET|BLOOD|OTHER)$")
    description: str = Field(min_length=1, max_length=2000)
    priority: str = Field(default="ROUTINE", pattern="^(ROUTINE|URGENT|STAT|ASAP)$")
    indications: str | None = Field(default=None, max_length=2000)
    requested_by: str | None = Field(default=None, min_length=1)
    encounter_id: str | None = None
    external_ref: str | None = None


class ClinicalOrderUpdateIn(BaseModel):
    status: str | None = Field(default=None, pattern="^(REQUESTED|IN_PROGRESS|COMPLETED|CANCELLED|HOLD)$")
    result_summary: str | None = None
    completed_by: str | None = Field(default=None, min_length=1)


class ClinicalOrderOut(BaseModel):
    id: str
    patient_id: str
    encounter_id: str | None
    order_type: str
    description: str
    priority: str
    indications: str | None
    requested_by: str | None
    requested_at: datetime
    result_summary: str | None
    completed_at: datetime | None
    status: str


# --- allergies -----------------------------------------------------------------


class AllergyIn(BaseModel):
    allergen: str = Field(min_length=1, max_length=255)
    allergen_type: str = Field(pattern="^(DRUG|FOOD|ENVIRONMENT|OTHER)$")
    reaction: str | None = Field(default=None, max_length=2000)
    severity: str = Field(default="UNKNOWN", pattern="^(LOW|MEDIUM|HIGH|UNKNOWN)$")
    onset_date: date | None = None
    encounter_id: str | None = None
    recorded_by: str | None = Field(default=None, min_length=1)

    @field_validator("onset_date")
    @classmethod
    def _onset(cls, value: date | None) -> date | None:
        return _not_future_date(value)


class AllergyOut(BaseModel):
    id: str
    patient_id: str
    encounter_id: str | None
    allergen: str
    allergen_type: str
    reaction: str | None
    severity: str
    onset_date: date | None
    recorded_at: datetime
    resolved_at: datetime | None
    status: str


# --- problem list --------------------------------------------------------------


class ProblemIn(BaseModel):
    problem: str = Field(min_length=1, max_length=2000)
    diagnosis_code: str | None = Field(default=None, max_length=50)
    code_system: str = Field(default="ICD-10", pattern="^(ICD-10|ICD-11|SNOMED-CT)$")
    onset_date: date | None = None
    severity: str | None = Field(default=None, pattern="^(LOW|MEDIUM|HIGH)$")
    note: str | None = Field(default=None, max_length=5000)
    recorded_by: str | None = Field(default=None, min_length=1)

    @field_validator("onset_date")
    @classmethod
    def _onset(cls, value: date | None) -> date | None:
        return _not_future_date(value)


class ProblemOut(BaseModel):
    id: str
    patient_id: str
    problem: str
    diagnosis_code: str | None
    code_system: str
    onset_date: date | None
    resolved_date: date | None
    severity: str | None
    note: str | None
    recorded_by: str | None
    status: str


# --- medical history -----------------------------------------------------------


class MedicalHistoryIn(BaseModel):
    history_type: str = Field(
        pattern="^(PAST_MEDICAL|SURGICAL|FAMILY|SOCIAL|MEDICATION|ALLERGY|OBSTETRIC|GROWTH|IMMUNIZATION|OTHER)$"
    )
    description: str = Field(min_length=1, max_length=5000)
    encounter_id: str | None = None
    occurred_date: date | None = None
    resolved_date: date | None = None
    facility: str | None = Field(default=None, max_length=255)
    notes: str | None = Field(default=None, max_length=5000)
    recorded_by: str | None = Field(default=None, min_length=1)

    @field_validator("occurred_date", "resolved_date")
    @classmethod
    def _dates(cls, value: date | None) -> date | None:
        return _not_future_date(value)


class MedicalHistoryOut(BaseModel):
    id: str
    patient_id: str
    encounter_id: str | None
    history_type: str
    description: str
    occurred_date: date | None
    resolved_date: date | None
    facility: str | None
    notes: str | None
    recorded_by: str | None
    created_at: datetime
    status: str


# --- timeline ------------------------------------------------------------------


class TimelineEntry(BaseModel):
    id: str
    patient_id: str
    event_type: str
    source: str
    entity_type: str | None
    entity_id: str | None
    occurred_at: datetime
    actor_id: str | None
    details: dict | None


# --- patient chart (aggregate) -------------------------------------------------


class PatientChart(BaseModel):
    """Aggregate clinical chart for one patient; section -> {count, items}."""

    patient_id: str
    sections: dict[str, dict] = Field(default_factory=dict)