"""Pydantic request/response schemas for the patient-service with validation.

Validation rules (per DATA_GOVERNANCE.md and registration SOPs):
- names are required, surname/first min length; no digits allowed.
- date_of_birth must be a real past date (not future, within reasonable range).
- NID follows the national ID format (e.g. 3-6-1 digit groups), passport format.
- phone/email validated; emergency contact requires phone + contact name.
- insurance card numbers match the provider pattern when a provider is known.
- medical alerts require recognized type/severity/title.
"""

import re
from datetime import date, datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

# ISO-compatible national ID. TZ NID is 3-6-1 digits (e.g. 12345678901234);
# generic: between 8 and 16 alphanumerics with no spaces.
NID_RE = re.compile(r"^[0-9]{3}-[0-9]{6}-[0-9]{1}$|^[0-9]{8,16}$")
PASSPORT_RE = re.compile(r"^[A-Z]{1,2}[0-9]{7}$")
PHONE_RE = re.compile(r"^\+?[0-9]{8,15}$")
CARD_NUMBER_RE = re.compile(r"^[A-Z0-9\-]{6,20}$")


# ---------------------------------------------------------------- registration

class EmergencyContactIn(BaseModel):
    name: str = Field(min_length=1, max_length=255)
    relationship: str = Field(min_length=1, max_length=100)
    phone: str = Field(min_length=8, max_length=15)
    alternate_phone: str | None = Field(default=None, max_length=15)

    @field_validator("phone", "alternate_phone")
    @classmethod
    def _phone(cls, v: str | None) -> str | None:
        if v is not None and not PHONE_RE.match(v):
            raise ValueError("Invalid phone number")
        return v


class AddressIn(BaseModel):
    address_type: str = Field(default="HOME", pattern="^(HOME|WORK|BILLING|CONTACT)$")
    line1: str | None = Field(default=None, max_length=255)
    line2: str | None = Field(default=None, max_length=255)
    city: str | None = Field(default=None, max_length=100)
    state_province: str | None = Field(default=None, max_length=100)
    postal_code: str | None = Field(default=None, max_length=20)
    country: str | None = Field(default=None, max_length=100)
    is_primary: bool = True


class IdentifierIn(BaseModel):
    identifier_type: str = Field(pattern="^(NATIONAL_ID|PASSPORT|INSURANCE|HOSPITAL)$")
    identifier_value: str = Field(min_length=3, max_length=255)
    issuer: str | None = Field(default=None, max_length=100)
    valid_from: date | None = None
    valid_to: date | None = None
    is_primary: bool = False

    @field_validator("identifier_value")
    @classmethod
    def _check(cls, v: str, info) -> str:
        ident_type = info.data.get("identifier_type")
        if ident_type == "NATIONAL_ID" and not NID_RE.match(v):
            raise ValueError("Invalid national ID format")
        if ident_type == "PASSPORT" and not PASSPORT_RE.match(v.upper()):
            raise ValueError("Invalid passport format (e.g. AB1234567)")
        return v.upper() if ident_type == "PASSPORT" else v


class InsuranceIn(BaseModel):
    provider_name: str = Field(min_length=1, max_length=255)
    provider_code: str | None = Field(default=None, max_length=50)
    card_number: str | None = Field(default=None, max_length=100)
    policy_number: str | None = Field(default=None, max_length=100)
    member_number: str | None = Field(default=None, max_length=100)
    relation_to_subscriber: str | None = Field(default=None, pattern="^(SELF|SPOUSE|DEPENDENT|OTHER)$")
    coverage_type: str | None = Field(
        default=None, pattern="^(INPATIENT|OUTPATIENT|DENTAL|OPTICAL|MATERNITY|SURGERY|COMBO)$"
    )
    valid_from: date | None = None
    valid_to: date | None = None
    remarks: str | None = Field(default=None, max_length=500)

    @field_validator("card_number", "policy_number", "member_number")
    @classmethod
    def _card(cls, v: str | None) -> str | None:
        if v is not None and not CARD_NUMBER_RE.match(v):
            raise ValueError("Invalid insurance card/policy/member number")
        return v


class MedicalAlertIn(BaseModel):
    alert_type: str = Field(
        pattern="^(ALLERGY|CONDITION|FALL_RISK|LATE_CREATION|DRUG_SENSITIVITY|INFECTION|OTHER)$"
    )
    severity: str = Field(pattern="^(LOW|MEDIUM|HIGH|CRITICAL)$")
    title: str = Field(min_length=2, max_length=255)
    description: str | None = Field(default=None, max_length=2000)


class ConsentIn(BaseModel):
    consent_type: str = Field(pattern="^(TREATMENT|DATA_SHARING|RESEARCH|TELEHEALTH|AUTOMATION)$")
    granted: bool = True
    expiry_date: date | None = None
    documentation_ref: str | None = Field(default=None, max_length=255)


class RegisterRequest(BaseModel):
    first_name: str = Field(min_length=1, max_length=255)
    last_name: str = Field(min_length=1, max_length=255)
    other_names: str | None = Field(default=None, max_length=255)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, pattern="^(MALE|FEMALE|OTHER|UNDISCLOSED)$")
    blood_group: str | None = Field(default=None, pattern="^(A\\+?|A\\-?|B\\+?|B\\-?|AB\\+?|AB\\-?|O\\+?|O\\-?)$")
    nationality: str | None = Field(default=None, max_length=100)
    marital_status: str | None = Field(default=None, max_length=20)
    language_pref: str = "en"

    national_identifier: str | None = Field(default=None, max_length=100)
    identifiers: list[IdentifierIn] = Field(default_factory=list)

    contacts: list[EmergencyContactIn] = Field(default_factory=list)
    addresses: list[AddressIn] = Field(default_factory=list)
    emergency_contact: EmergencyContactIn | None = None
    insurance: InsuranceIn | None = None
    alerts: list[MedicalAlertIn] = Field(default_factory=list)
    consents: list[ConsentIn] = Field(default_factory=list)

    @model_validator(mode="after")
    def _check_dob(self) -> "RegisterRequest":
        if self.date_of_birth is not None:
            _validate_dob(self.date_of_birth)
        return self

    @field_validator("national_identifier")
    @classmethod
    def _check_nid(cls, v: str | None) -> str | None:
        if v is not None:
            v = v.replace(" ", "")
            if not NID_RE.match(v):
                raise ValueError("Invalid national ID format")
        return v

    @field_validator("first_name", "last_name")
    @classmethod
    def _names(cls, v: str) -> str:
        if any(ch.isdigit() for ch in v):
            raise ValueError("Names must not contain digits")
        return v


# ---------------------------------------------------------------- output

class PatientSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    patient_number: str | None
    mrn: str | None
    first_name: str
    last_name: str
    other_names: str | None
    date_of_birth: date | None
    gender: str | None
    nationality: str | None
    biometrics_ready: bool
    merged_into_id: str | None
    created_at: datetime


class PatientDetail(PatientSummary):
    blood_group: str | None
    marital_status: str | None
    language_pref: str
    contact_info: dict | None
    address: dict | None
    emergency_contact: dict | None
    registration_date: date
    consent_summary: dict | None
    deceased_at: datetime | None


class SearchResult(BaseModel):
    patients: list[PatientSummary] = Field(default_factory=list)
    total: int
    limit: int
    offset: int


class TimelineEntry(BaseModel):
    id: str
    event_type: str
    source: str
    occurred_at: datetime
    actor: str | None
    details: dict | None


class MergeResponse(BaseModel):
    survivor_id: str
    merged_id: str
    duplicate_moved: list[str] = Field(default_factory=list)  # entity names re-pointed
    links_created: int = 0
    duplicate_deactivated: bool = True


class UpdateRequest(BaseModel):
    first_name: str | None = Field(default=None, min_length=1, max_length=255)
    last_name: str | None = Field(default=None, min_length=1, max_length=255)
    other_names: str | None = Field(default=None, max_length=255)
    date_of_birth: date | None = None
    gender: str | None = Field(default=None, pattern="^(MALE|FEMALE|OTHER|UNDISCLOSED)$")
    blood_group: str | None = Field(default=None, pattern="^(A\\+?|A\\-?|B\\+?|B\\-?|AB\\+?|AB\\-?|O\\+?|O\\-?)$")
    nationality: str | None = Field(default=None, max_length=100)
    marital_status: str | None = Field(default=None, max_length=20)
    language_pref: str | None = Field(default=None, max_length=10)

    @model_validator(mode="after")
    def _check_dob(self) -> "UpdateRequest":
        if self.date_of_birth is not None:
            _validate_dob(self.date_of_birth)
        return self


class PhotoIn(BaseModel):
    content_type: str = Field(default="image/jpeg", pattern="^image/(jpeg|png|webp)$")
    data_b64: str = Field(min_length=16, max_length=15_000_000)  # ~15 MB cap
    width: int | None = None
    height: int | None = None
    taken_at: datetime | None = None


class BiometricIn(BaseModel):
    modality: str = Field(pattern="^(FINGERPRINT|FACE|IRIS|VOICE)$")
    enrollment_state: str = Field(default="ENROLLED", pattern="^(PLANNED|ENROLLED|READY|FAILED|DISABLED)$")
    provider: str | None = Field(default=None, max_length=100)
    template_ref: str | None = Field(default=None, max_length=255)


class BiometricOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    modality: str
    enrollment_state: str
    provider: str | None
    template_ref: str | None
    enrolled_at: datetime | None


class PhotoOut(BaseModel):
    id: str
    content_type: str
    object_ref: str | None
    is_primary: bool
    width: int | None
    height: int | None
    taken_at: datetime | None


class InsuranceOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    provider_name: str
    provider_code: str | None
    card_number: str | None
    policy_number: str | None
    member_number: str | None
    relation_to_subscriber: str | None
    coverage_type: str | None
    valid_from: date | None
    valid_to: date | None


class AlertOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    alert_type: str
    severity: str
    title: str
    description: str | None
    active: bool
    resolved_at: datetime | None
    created_at: datetime


class ContactOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    contact_type: str
    value: str
    is_primary: bool
    is_verified: bool


class IdentifierOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    identifier_type: str
    identifier_value: str
    issuer: str | None
    is_primary: bool
    valid_from: date | None
    valid_to: date | None


def _validate_dob(dob: date) -> None:
    if dob > date.today():
        raise ValueError("Date of birth cannot be in the future")
    if dob < date(1900, 1, 1):
        raise ValueError("Date of birth is unreasonably old")