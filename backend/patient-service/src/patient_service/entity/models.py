"""SQLAlchemy models for the patient-service.

Maps V001__init.sql (patients, identifiers, contacts, consents, links) and
V002__registration_features.sql (addresses, insurance, alerts, photos,
biometrics, timeline). Common row block per DATABASE_DESIGN.md section 2.5.
"""

from __future__ import annotations

import uuid
from datetime import date, datetime

from sqlalchemy import (
    JSON,
    Boolean,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    Uuid,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Declarative base for the patient-service."""


def _uuid() -> uuid.UUID:
    return uuid.uuid4()


class CommonMixin:
    """Common row block (id uuid, audit fields, version, status, soft delete)."""

    id: Mapped[uuid.UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=_uuid)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False
    )
    created_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    updated_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    status: Mapped[str] = mapped_column(String(50), nullable=False, default="ACTIVE")
    audit_reference: Mapped[str | None] = mapped_column(String(255), nullable=True)
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    deleted_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    deletion_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Patient(Base, CommonMixin):
    """The master patient entity (MPI)."""

    __tablename__ = "patients"

    patient_number: Mapped[str | None] = mapped_column(String(50), nullable=True)
    mrn: Mapped[str | None] = mapped_column(String(50), index=True, nullable=True)
    first_name: Mapped[str] = mapped_column(String(255), nullable=False)
    last_name: Mapped[str] = mapped_column(String(255), nullable=False)
    other_names: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date_of_birth: Mapped[date | None] = mapped_column(Date, nullable=True)
    gender: Mapped[str | None] = mapped_column(String(20), nullable=True)
    blood_group: Mapped[str | None] = mapped_column(String(5), nullable=True)
    nationality: Mapped[str | None] = mapped_column(String(100), nullable=True)
    marital_status: Mapped[str | None] = mapped_column(String(20), nullable=True)
    language_pref: Mapped[str] = mapped_column(String(10), nullable=False, default="en")
    national_identifier: Mapped[str | None] = mapped_column(String(100), nullable=True)
    contact_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    address: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    emergency_contact: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    registration_date: Mapped[date] = mapped_column(Date, nullable=False, default=func.current_date())
    consent_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    deceased_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    merged_into_id: Mapped[uuid.UUID | None] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id"), nullable=True
    )
    biometrics_ready: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PatientIdentifier(Base, CommonMixin):
    """Multi-issuer identifiers (NATIONAL_ID, PASSPORT, INSURANCE, HOSPITAL)."""

    __tablename__ = "patient_identifiers"
    __table_args__ = (
        UniqueConstraint("identifier_type", "issuer", "identifier_value", name="uq_pid_type_issuer_value"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id"), index=True, nullable=False
    )
    identifier_type: Mapped[str] = mapped_column(String(50), nullable=False)
    identifier_value: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(100), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PatientContact(Base, CommonMixin):
    """Phone / email / whatsapp / emergency contact."""

    __tablename__ = "patient_contacts"
    __table_args__ = (
        UniqueConstraint("patient_id", "contact_type", "value", name="uq_patient_contacts_patient_type_value"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id"), index=True, nullable=False
    )
    contact_type: Mapped[str] = mapped_column(String(20), nullable=False)  # PHONE/EMAIL/WHATSAPP/EMERGENCY
    value: Mapped[str] = mapped_column(String(320), nullable=False)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    is_verified: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PatientAddress(Base, CommonMixin):
    """Structured address (HOME, WORK, BILLING, CONTACT)."""

    __tablename__ = "patient_addresses"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id"), index=True, nullable=False
    )
    address_type: Mapped[str] = mapped_column(String(20), nullable=False)
    line1: Mapped[str | None] = mapped_column(String(255), nullable=True)
    line2: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(100), nullable=True)
    state_province: Mapped[str | None] = mapped_column(String(100), nullable=True)
    postal_code: Mapped[str | None] = mapped_column(String(20), nullable=True)
    country: Mapped[str | None] = mapped_column(String(100), nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)


class PatientConsent(Base, CommonMixin):
    """Consents source of truth."""

    __tablename__ = "patient_consents"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id"), index=True, nullable=False
    )
    consent_type: Mapped[str] = mapped_column(String(50), nullable=False)
    granted: Mapped[bool] = mapped_column(Boolean, nullable=False)
    date_given: Mapped[date] = mapped_column(Date, nullable=False, default=func.current_date())
    expiry_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    documentation_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    withdrawn_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    withdrawn_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    revoked_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class PatientLink(Base, CommonMixin):
    """Record linkage: SAME_PERSON / DUPLICATE / RELATED."""

    __tablename__ = "patient_links"

    left_patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id"), index=True, nullable=False
    )
    right_patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id"), index=True, nullable=False
    )
    match_score: Mapped[float | None] = mapped_column(Numeric(5, 4), nullable=True)
    match_method: Mapped[str | None] = mapped_column(String(50), nullable=True)
    link_type: Mapped[str] = mapped_column(String(20), nullable=False)  # SAME_PERSON/DUPLICATE/RELATED
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PatientInsurance(Base, CommonMixin):
    """Insurance-card snapshot captured at registration (read-side card data)."""

    __tablename__ = "patient_insurance"
    __table_args__ = (
        UniqueConstraint("patient_id", "card_number", name="uq_patient_insurance_card"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id"), index=True, nullable=False
    )
    provider_name: Mapped[str] = mapped_column(String(255), nullable=False)
    provider_code: Mapped[str | None] = mapped_column(String(50), nullable=True)
    card_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    policy_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    member_number: Mapped[str | None] = mapped_column(String(100), nullable=True)
    relation_to_subscriber: Mapped[str | None] = mapped_column(String(20), nullable=True)
    coverage_type: Mapped[str | None] = mapped_column(String(30), nullable=True)
    valid_from: Mapped[date | None] = mapped_column(Date, nullable=True)
    valid_to: Mapped[date | None] = mapped_column(Date, nullable=True)
    remarks: Mapped[str | None] = mapped_column(String(500), nullable=True)


class MedicalAlert(Base, CommonMixin):
    """Allergies, conditions, fall-risk and other clinical alerts."""

    __tablename__ = "medical_alerts"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id"), index=True, nullable=False
    )
    alert_type: Mapped[str] = mapped_column(String(30), nullable=False)  # ALLERGY/CONDITION/...
    severity: Mapped[str] = mapped_column(String(10), nullable=False)    # LOW/MEDIUM/HIGH/CRITICAL
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    resolved_by: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    resolved_reason: Mapped[str | None] = mapped_column(String(500), nullable=True)


class PatientPhoto(Base, CommonMixin):
    """Patient photograph (passport/profile); bytea or object-store ref."""

    __tablename__ = "patient_photos"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id"), index=True, nullable=False
    )
    photo: Mapped[bytes | None] = mapped_column(nullable=True)  # BYTEA
    object_ref: Mapped[str | None] = mapped_column(String(500), nullable=True)
    content_type: Mapped[str] = mapped_column(String(50), nullable=False, default="image/jpeg")
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    taken_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PatientBiometric(Base, CommonMixin):
    """Biometric readiness registry; never stores raw templates."""

    __tablename__ = "patient_biometrics"
    __table_args__ = (
        UniqueConstraint("patient_id", "modality", name="uq_patient_biometrics_patient_modality"),
    )

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id"), index=True, nullable=False
    )
    modality: Mapped[str] = mapped_column(String(20), nullable=False)  # FINGERPRINT/FACE/IRIS/VOICE
    enrollment_state: Mapped[str] = mapped_column(String(20), nullable=False, default="ENROLLED")
    provider: Mapped[str | None] = mapped_column(String(100), nullable=True)
    template_ref: Mapped[str | None] = mapped_column(String(255), nullable=True)
    enrolled_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class PatientTimelineEvent(Base, CommonMixin):
    """Source-tagged timeline entry (registration, updates, merges, alerts)."""

    __tablename__ = "patient_timeline"

    patient_id: Mapped[uuid.UUID] = mapped_column(
        Uuid(as_uuid=True), ForeignKey("patients.id"), index=True, nullable=False
    )
    event_type: Mapped[str] = mapped_column(String(50), nullable=False)
    source: Mapped[str] = mapped_column(String(50), nullable=False, default="patient-service")
    reference_id: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=func.now()
    )
    actor: Mapped[uuid.UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True)
    details: Mapped[dict | None] = mapped_column(JSON, nullable=True)