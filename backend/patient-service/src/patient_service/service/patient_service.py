"""Business logic for patient registration, search, merge and timeline.

Publishes ``PatientRegistered`` / ``PatientUpdated`` / ``PatientMerged`` /
``PatientDeactivated`` events on their registry-catalog topics
(``clinical.patient.*``) so scheduling, ehr and insurance services keep
projections fresh (EVENT_BUS.md).
"""

from __future__ import annotations

import base64
import logging
import uuid
from datetime import UTC, date, datetime

from ehos_common.events import DomainEvent
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from patient_service.configuration import PatientSettings
from patient_service.dto.schemas import (
    BiometricIn,
    IdentifierIn,
    InsuranceIn,
    MedicalAlertIn,
    PatientDetail,
    PhotoIn,
    RegisterRequest,
    UpdateRequest,
)
from patient_service.entity.models import (
    MedicalAlert,
    Patient,
    PatientAddress,
    PatientBiometric,
    PatientConsent,
    PatientContact,
    PatientIdentifier,
    PatientInsurance,
    PatientLink,
    PatientPhoto,
    PatientTimelineEvent,
)

log = logging.getLogger("patient-service")

PATIENT_TOPIC = "clinical.patient.registered"
PATIENT_UPDATED_TOPIC = "clinical.patient.updated"
PATIENT_MERGED_TOPIC = "clinical.patient.merged"
PATIENT_DEACTIVATED_TOPIC = "clinical.patient.deactivated"
PATIENT_NUMBER_COUNTER = "patient_registration_counter"

# eventType → canonical registry topic (mirrors the shared EventRegistry catalog)
_PATIENT_TOPICS = {
    "PatientRegistered": PATIENT_TOPIC,
    "PatientUpdated": PATIENT_UPDATED_TOPIC,
    "PatientMerged": PATIENT_MERGED_TOPIC,
    "PatientDeactivated": PATIENT_DEACTIVATED_TOPIC,
}


class PatientError(Exception):
    def __init__(self, error_code: str, message: str, status_code: int = 400):
        self.error_code = error_code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class PatientService:
    def __init__(self, settings: PatientSettings, producer=None):
        self.settings = settings
        self.producer = producer

    # ------------------------------------------------------------ helpers

    async def _next_number(self, session: AsyncSession, prefix: str) -> str:
        """Monotonic registry number (MRN / patient number)."""
        column = Patient.mrn if prefix == self.settings.mrn_prefix else Patient.patient_number
        result = await session.execute(
            select(func.max(column)).where(column.like(f"{prefix}%"))
        )
        max_val = result.scalar()
        seq = int(max_val[len(prefix):]) if max_val else 0
        return f"{prefix}{seq + 1:0{self.settings.number_width}d}"

    async def _timeline(self, session: AsyncSession, patient_id, event_type: str, actor=None, details=None) -> None:
        session.add(
            PatientTimelineEvent(
                patient_id=patient_id, event_type=event_type, source="patient-service",
                actor=actor, details=details,
            )
        )

    async def _publish(self, session: AsyncSession, event_type: str, patient_id, details: dict | None) -> None:
        if self.producer is None:
            return
        try:
            topic = _PATIENT_TOPICS.get(event_type, PATIENT_TOPIC)
            event = DomainEvent(
                event_type=event_type,
                source="patient-service",
                user_id=None,
                payload={
                    "patientId": str(patient_id),
                    "occurredAt": datetime.now(UTC).isoformat(),
                    **(details or {}),
                },
            )
            # Stage on the request outbox (published after commit) when the HTTP
            # dependency wired one; fall back to immediate publish (direct calls,
            # tests) so eventing still works without the request lifecycle.
            outbox = session.info.get("outbox")
            if outbox is not None:
                outbox.add(topic, event)
            else:
                await self.producer.publish(topic, event)
        except Exception:  # noqa: BLE001 - publishing must never break registration
            log.exception("failed to publish %s", event_type)

    async def _get_or_404(self, session: AsyncSession, patient_id) -> Patient:
        patient = await session.get(Patient, patient_id)
        if patient is None or patient.deleted_at is not None:
            raise PatientError("PATIENT_NOT_FOUND", "Patient not found", 404)
        return patient

    # ------------------------------------------------------------ registration

    async def register(self, session: AsyncSession, data: RegisterRequest, actor: uuid.UUID | None = None) -> Patient:
        # duplicate-fingerprint check on the national ID (if provided)
        if data.national_identifier:
            dup = await self._find_by_national_id(session, data.national_identifier)
            if dup is not None:
                # Do not echo the existing patient's MRN/identifier: that would
                # leak PHI to the caller (API_DESIGN_STANDARD.md — no sensitive
                # data in error responses).
                raise PatientError(
                    "DUPLICATE_PATIENT",
                    "A patient with this National ID is already registered.",
                    409,
                )

        mrn = await self._next_number(session, self.settings.mrn_prefix)
        pno = await self._next_number(session, self.settings.patient_number_prefix)

        patient = Patient(
            patient_number=pno,
            mrn=mrn,
            first_name=data.first_name,
            last_name=data.last_name,
            other_names=data.other_names,
            date_of_birth=data.date_of_birth,
            gender=data.gender,
            blood_group=data.blood_group,
            nationality=data.nationality,
            marital_status=data.marital_status,
            language_pref=data.language_pref,
            national_identifier=data.national_identifier,
            registration_date=date.today(),
            created_by=actor,
            status="ACTIVE",
        )

        # normalize emergency contact onto the patient row (JSONB quick view)
        if data.emergency_contact:
            patient.emergency_contact = data.emergency_contact.model_dump()
        if data.addresses:
            patient.address = data.addresses[0].model_dump() if data.addresses else None

        session.add(patient)
        await session.flush()

        # identifiers (NID/passport/insurance card)
        for ident in data.identifiers:
            session.add(
                PatientIdentifier(
                    patient_id=patient.id,
                    identifier_type=ident.identifier_type,
                    identifier_value=ident.identifier_value,
                    issuer=ident.issuer or self.settings.default_country,
                    valid_from=ident.valid_from,
                    valid_to=ident.valid_to,
                    is_primary=ident.is_primary,
                )
            )

        # contacts
        for contact in data.contacts:
            session.add(
                PatientContact(
                    patient_id=patient.id,
                    contact_type="EMERGENCY",
                    value=contact.phone,
                    is_primary=contact.alternate_phone is None,
                )
            )
            if contact.alternate_phone:
                session.add(
                    PatientContact(
                        patient_id=patient.id, contact_type="EMERGENCY", value=contact.alternate_phone
                    )
                )

        # addresses
        for addr in data.addresses:
            session.add(
                PatientAddress(
                    patient_id=patient.id,
                    address_type=addr.address_type,
                    line1=addr.line1,
                    line2=addr.line2,
                    city=addr.city,
                    state_province=addr.state_province,
                    postal_code=addr.postal_code,
                    country=addr.country or self.settings.default_country,
                    is_primary=addr.is_primary,
                )
            )

        # insurance snapshot
        if data.insurance:
            session.add(
                PatientInsurance(
                    patient_id=patient.id,
                    provider_name=data.insurance.provider_name,
                    provider_code=data.insurance.provider_code,
                    card_number=data.insurance.card_number,
                    policy_number=data.insurance.policy_number,
                    member_number=data.insurance.member_number,
                    relation_to_subscriber=data.insurance.relation_to_subscriber,
                    coverage_type=data.insurance.coverage_type,
                    valid_from=data.insurance.valid_from,
                    valid_to=data.insurance.valid_to,
                    remarks=data.insurance.remarks,
                )
            )

        # medical alerts captured at registration
        for alert in data.alerts:
            session.add(
                MedicalAlert(
                    patient_id=patient.id,
                    alert_type=alert.alert_type,
                    severity=alert.severity,
                    title=alert.title,
                    description=alert.description,
                    active=True,
                )
            )

        # consents
        for consent in data.consents:
            session.add(
                PatientConsent(
                    patient_id=patient.id,
                    consent_type=consent.consent_type,
                    granted=consent.granted,
                    documentation_ref=consent.documentation_ref,
                    expiry_date=consent.expiry_date,
                )
            )

        await self._timeline(session, patient.id, "REGISTERED", actor, {"mrn": mrn})
        await session.flush()
        registered_at = patient.created_at if patient.created_at is not None else datetime.now(UTC)
        await self._publish(
            session,
            "PatientRegistered",
            patient.id,
            {
                "mrn": mrn,
                "firstName": patient.first_name,
                "lastName": patient.last_name,
                "registeredAt": registered_at.isoformat(),
            },
        )
        return patient

    async def _find_by_national_id(self, session: AsyncSession, value: str) -> Patient | None:
        """Fingerprint lookup on the national ID across patients and identifiers."""
        cleaned = value.replace(" ", "")
        result = await session.execute(
            select(Patient).where(
                Patient.national_identifier == cleaned,
                Patient.deleted_at.is_(None),
                Patient.merged_into_id.is_(None),
            )
        )
        direct = result.scalar_one_or_none()
        if direct is not None:
            return direct
        result = await session.execute(
            select(PatientIdentifier.patient_id)
            .where(
                PatientIdentifier.identifier_type == "NATIONAL_ID",
                PatientIdentifier.identifier_value == cleaned,
                PatientIdentifier.deleted_at.is_(None),
            )
            .limit(1)
        )
        pid = result.scalar_one_or_none()
        if pid is None:
            return None
        return await session.get(Patient, pid)

    # ------------------------------------------------------------ search & read

    async def search(
        self,
        session: AsyncSession,
        q: str | None = None,
        limit: int = 50,
        offset: int = 0,
        include_inactive: bool = False,
    ) -> tuple[list[Patient], int]:
        limit = min(max(1, limit), self.settings.search_max_limit)
        stmt = select(Patient).where(
            Patient.deleted_at.is_(None),
            Patient.merged_into_id.is_(None),
        )
        if not include_inactive:
            stmt = stmt.where(Patient.status != "DISABLED")

        if q:
            term = q.strip().lower()
            like = f"%{term}%"
            stmt = stmt.where(
                or_(
                    Patient.first_name.ilike(like),
                    Patient.last_name.ilike(like),
                    Patient.mrn.ilike(like),
                    Patient.patient_number.ilike(like),
                    Patient.national_identifier.ilike(like),
                )
            )

        count_stmt = select(func.count()).select_from(stmt.subquery())
        total = (await session.execute(count_stmt)).scalar_one()

        rows = (
            (await session.execute(stmt.order_by(Patient.last_name, Patient.first_name).limit(limit).offset(offset)))
            .scalars()
            .all()
        )
        return list(rows), total

    async def get_detail(self, session: AsyncSession, patient_id) -> PatientDetail:
        patient = await self._get_or_404(session, patient_id)
        return PatientDetail(
            id=str(patient.id),
            patient_number=patient.patient_number,
            mrn=patient.mrn,
            first_name=patient.first_name,
            last_name=patient.last_name,
            other_names=patient.other_names,
            date_of_birth=patient.date_of_birth,
            gender=patient.gender,
            nationality=patient.nationality,
            biometrics_ready=patient.biometrics_ready,
            merged_into_id=str(patient.merged_into_id) if patient.merged_into_id else None,
            created_at=patient.created_at,
            blood_group=patient.blood_group,
            marital_status=patient.marital_status,
            language_pref=patient.language_pref,
            contact_info=patient.contact_info,
            address=patient.address,
            emergency_contact=patient.emergency_contact,
            registration_date=patient.registration_date,
            consent_summary=patient.consent_summary,
            deceased_at=patient.deceased_at,
        )

    async def update(self, session: AsyncSession, patient_id, data: UpdateRequest, actor=None) -> Patient:
        patient = await self._get_or_404(session, patient_id)
        updates = data.model_dump(exclude_unset=True)
        for field_name, value in updates.items():
            setattr(patient, field_name, value)
        patient.updated_by = actor
        patient.version += 1
        await self._timeline(session, patient.id, "UPDATED", actor, {"fields": list(updates)})
        await self._publish(session, "PatientUpdated", patient.id, {"fields": list(updates)})
        return patient

    # ------------------------------------------------------------ merge

    async def merge(self, session: AsyncSession, survivor_id, duplicate_id, actor=None) -> dict:
        """Merge ``duplicate_id`` into ``survivor_id``:
        - create a SAME_PERSON link,
        - re-point that patient's dependent records onto the survivor,
        - push a timeline event, deactivate (soft-delete) the duplicate record,
        - dedupe identifiers/contacts that would violate unique constraints.
        """
        survivor = await self._get_or_404(session, survivor_id)
        duplicate = await self._get_or_404(session, duplicate_id)
        if survivor_id == duplicate_id:
            raise PatientError("MERGE_SELF", "Cannot merge a patient into itself", 400)

        moved: list[str] = []
        child_tables = [
            (PatientIdentifier, "identifier"),
            (PatientContact, "contact"),
            (PatientAddress, "address"),
            (PatientInsurance, "insurance"),
            (MedicalAlert, "alert"),
            (PatientPhoto, "photo"),
            (PatientBiometric, "biometric"),
            (PatientConsent, "consent"),
        ]
        for model, label in child_tables:
            rows = (
                (
                    await session.execute(
                        select(model).where(model.patient_id == duplicate.id, model.deleted_at.is_(None))
                    )
                )
                .scalars()
                .all()
            )
            for row in rows:
                # re-home the child onto the survivor inside a savepoint so a
                # unique-constraint conflict only discards that one row.
                async with session.begin_nested():
                    try:
                        row.patient_id = survivor.id
                        await session.flush()
                    except Exception:  # noqa: BLE001 - unique conflict on survivor
                        row.deleted_at = datetime.now(UTC)
                        row.deletion_reason = f"merged duplication conflict (survivor {survivor.id})"
                    else:
                        if label not in moved:
                            moved.append(label)

        # record linkage
        link = PatientLink(
            left_patient_id=survivor.id,
            right_patient_id=duplicate.id,
            match_method="MANUAL",
            link_type="SAME_PERSON",
            resolved_by=actor,
            resolved_at=datetime.now(UTC),
        )
        session.add(link)

        # deactivate duplicate
        duplicate.merged_into_id = survivor.id
        duplicate.status = "MERGED"
        duplicate.deleted_at = datetime.now(UTC)
        duplicate.updated_by = actor
        duplicate.deletion_reason = f"merged into {survivor.mrn}"

        await self._timeline(session, survivor.id, "MERGED_INTO", actor, {"duplicateId": str(duplicate.id)})
        await session.flush()
        await self._publish(
            session,
            "PatientMerged",
            survivor.id,
            {"mergedId": str(duplicate.id), "duplicateMrn": duplicate.mrn},
        )
        await self._publish(session, "PatientDeactivated", duplicate.id, {"mergedInto": str(survivor.id)})

        return {
            "survivor_id": str(survivor.id),
            "merged_id": str(duplicate.id),
            "duplicate_moved": moved,
            "links_created": 1,
            "duplicate_deactivated": True,
        }

    # ------------------------------------------------------------ timeline

    async def timeline(self, session: AsyncSession, patient_id) -> list[PatientTimelineEvent]:
        await self._get_or_404(session, patient_id)
        result = await session.execute(
            select(PatientTimelineEvent)
            .where(PatientTimelineEvent.patient_id == patient_id)
            .order_by(PatientTimelineEvent.occurred_at.desc())
        )
        return list(result.scalars().all())

    # ------------------------------------------------------------ alerts / biometrics / photos / insurance

    async def add_alert(self, session: AsyncSession, patient_id, data: MedicalAlertIn, actor=None) -> MedicalAlert:
        patient = await self._get_or_404(session, patient_id)
        alert = MedicalAlert(
            patient_id=patient.id, alert_type=data.alert_type, severity=data.severity,
            title=data.title, description=data.description, active=True,
        )
        session.add(alert)
        await self._timeline(session, patient.id, "ALERT_ADDED", actor, {"alert": data.title})
        return alert

    async def resolve_alert(
        self, session: AsyncSession, patient_id, alert_id, reason: str | None, actor=None
    ) -> MedicalAlert | None:
        await self._get_or_404(session, patient_id)
        alert = await session.get(MedicalAlert, alert_id)
        if alert is None or alert.patient_id != patient_id:
            return None
        alert.active = False
        alert.resolved_at = datetime.now(UTC)
        alert.resolved_by = actor
        alert.resolved_reason = reason
        await self._timeline(session, patient_id, "ALERT_RESOLVED", actor, {"alert": alert.title})
        return alert

    async def enroll_biometric(
        self, session: AsyncSession, patient_id, data: BiometricIn, actor=None
    ) -> PatientBiometric:
        patient = await self._get_or_404(session, patient_id)
        existing = (
            await session.execute(
                select(PatientBiometric).where(
                    PatientBiometric.patient_id == patient.id,
                    PatientBiometric.modality == data.modality,
                    PatientBiometric.deleted_at.is_(None),
                )
            )
        ).scalar_one_or_none()
        if existing is not None:
            existing.enrollment_state = data.enrollment_state
            existing.provider = data.provider
            existing.template_ref = data.template_ref
            if data.enrollment_state in ("ENROLLED", "READY"):
                existing.enrolled_at = datetime.now(UTC)
            row = existing
        else:
            row = PatientBiometric(
                patient_id=patient.id, modality=data.modality, enrollment_state=data.enrollment_state,
                provider=data.provider, template_ref=data.template_ref,
                enrolled_at=datetime.now(UTC) if data.enrollment_state in ("ENROLLED", "READY") else None,
            )
            session.add(row)

        if data.enrollment_state in ("ENROLLED", "READY"):
            patient.biometrics_ready = True
        await self._timeline(session, patient.id, "BIOMETRICS_ENROLLED", actor, {"modality": data.modality})
        return row

    async def add_photo(self, session: AsyncSession, patient_id, data: PhotoIn, actor=None) -> PatientPhoto:
        patient = await self._get_or_404(session, patient_id)
        try:
            raw = base64.b64decode(data.data_b64, validate=True)
        except Exception as exc:  # noqa: BLE001
            raise PatientError("INVALID_IMAGE", "Image payload is not valid base64", 422) from exc
        if len(raw) > 15_000_000:
            raise PatientError("IMAGE_TOO_LARGE", "Image exceeds the 15 MB limit", 413)
        photo = PatientPhoto(
            patient_id=patient.id, photo=raw, content_type=data.content_type,
            width=data.width, height=data.height, taken_at=data.taken_at, is_primary=True,
        )
        session.add(photo)
        await self._timeline(session, patient.id, "PHOTO_ADDED", actor, {"contentType": data.content_type})
        return photo

    async def add_insurance(self, session: AsyncSession, patient_id, data: InsuranceIn, actor=None) -> PatientInsurance:
        patient = await self._get_or_404(session, patient_id)
        row = PatientInsurance(
            patient_id=patient.id,
            provider_name=data.provider_name,
            provider_code=data.provider_code,
            card_number=data.card_number,
            policy_number=data.policy_number,
            member_number=data.member_number,
            relation_to_subscriber=data.relation_to_subscriber,
            coverage_type=data.coverage_type,
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            remarks=data.remarks,
        )
        session.add(row)
        await self._timeline(session, patient.id, "INSURANCE_ADDED", actor, {"provider": data.provider_name})
        return row

    async def add_identifier(
        self, session: AsyncSession, patient_id, data: IdentifierIn, actor=None
    ) -> PatientIdentifier:
        patient = await self._get_or_404(session, patient_id)
        row = PatientIdentifier(
            patient_id=patient.id,
            identifier_type=data.identifier_type,
            identifier_value=data.identifier_value,
            issuer=data.issuer or self.settings.default_country,
            valid_from=data.valid_from,
            valid_to=data.valid_to,
            is_primary=data.is_primary,
        )
        session.add(row)
        if data.identifier_type == "NATIONAL_ID":
            patient.national_identifier = data.identifier_value
        await self._timeline(session, patient.id, "IDENTIFIER_ADDED", actor, {"type": data.identifier_type})
        return row