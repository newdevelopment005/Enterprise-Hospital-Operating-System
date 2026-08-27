from datetime import UTC, datetime
from uuid import UUID

from ehos_common.events import DomainEvent
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from clinical_documentation_service.dto.schemas import (
    ClinicalNoteCreate,
    ClinicalNoteUpdate,
    ClinicalNoteSign,
    TemplateCreate,
    TemplateUpdate,
)
from clinical_documentation_service.entity.models import ClinicalNote, NoteVersion, Template

TOPICS = {
    "NoteCreated": "clinical.documentation.note.created",
    "NoteUpdated": "clinical.documentation.note.updated",
    "NoteSigned": "clinical.documentation.note.signed",
    "TemplateCreated": "clinical.documentation.template.created",
}


class DocumentationError(Exception):
    def __init__(self, code: str, message: str, status_code: int = 400):
        self.code = code
        self.message = message
        self.status_code = status_code
        super().__init__(message)


class DocumentationService:
    """Clinical documentation service: notes, versions, templates."""

    def __init__(self, producer: object | None = None):
        self.producer = producer

    async def _publish(self, session: AsyncSession, event_type: str, payload: dict) -> None:
        if self.producer is None:
            return
        try:
            topic = TOPICS.get(event_type)
            if topic is None:
                return
            event = DomainEvent(
                event_type=event_type,
                source="clinical-documentation-service",
                user_id=None,
                payload={"occurredAt": datetime.now(UTC).isoformat(), **payload},
            )
            outbox = session.info.get("outbox")
            if outbox is not None:
                outbox.add(topic, event)
            else:
                await self.producer.publish(topic, event)
        except Exception:
            pass

    # ------------------------ Notes ------------------------

    async def create_note(self, session: AsyncSession, payload: ClinicalNoteCreate, actor_id: UUID) -> ClinicalNote:
        note = ClinicalNote(
            patient_id=payload.patient_id,
            encounter_id=payload.encounter_id,
            author_id=payload.author_id,
            note_type=payload.note_type,
            title=payload.title,
            content=payload.content,
            structured_data=payload.structured_data,
            status="DRAFT",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(note)
        await session.flush()

        await self._publish(session, "NoteCreated", {"patient_id": str(note.patient_id), "note_type": note.note_type})
        return note

    async def get_note(self, session: AsyncSession, note_id: UUID) -> ClinicalNote | None:
        return await session.get(ClinicalNote, note_id)

    async def list_notes(
        self, session: AsyncSession, patient_id: UUID | None = None, encounter_id: UUID | None = None,
        author_id: UUID | None = None, note_type: str | None = None, status: str | None = None,
        limit: int = 50, offset: int = 0,
    ) -> list[ClinicalNote]:
        stmt = select(ClinicalNote).where(ClinicalNote.deleted_at.is_(None))
        if patient_id:
            stmt = stmt.where(ClinicalNote.patient_id == patient_id)
        if encounter_id:
            stmt = stmt.where(ClinicalNote.encounter_id == encounter_id)
        if author_id:
            stmt = stmt.where(ClinicalNote.author_id == author_id)
        if note_type:
            stmt = stmt.where(ClinicalNote.note_type == note_type)
        if status:
            stmt = stmt.where(ClinicalNote.status == status)
        stmt = stmt.order_by(ClinicalNote.created_at.desc()).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_note(self, session: AsyncSession, note_id: UUID, payload: ClinicalNoteUpdate, actor_id: UUID) -> ClinicalNote:
        note = await self.get_note(session, note_id)
        if not note:
            raise DocumentationError("NOTE_NOT_FOUND", "Note not found")
        if note.status == "FINAL":
            raise DocumentationError("INVALID_STATE", "Cannot update signed note")

        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(note, k, v)
        note.updated_by = actor_id
        note.model_version += 1

        # Create version snapshot
        ver = NoteVersion(
            note_id=note.id,
            version_number=note.model_version,
            content=note.content,
            structured_data=note.structured_data,
            changed_by=actor_id,
            status="DRAFT",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(ver)
        await session.flush()

        await self._publish(session, "NoteUpdated", {"note_id": str(note.id), "note_type": note.note_type})
        return note

    async def sign_note(self, session: AsyncSession, note_id: UUID, payload: ClinicalNoteSign, actor_id: UUID) -> ClinicalNote:
        note = await self.get_note(session, note_id)
        if not note:
            raise DocumentationError("NOTE_NOT_FOUND", "Note not found")
        if note.status == "CANCELLED":
            raise DocumentationError("INVALID_STATE", "Cannot sign cancelled note")

        note.status = "FINAL"
        note.signed_by = payload.signed_by
        note.signed_at = datetime.utcnow()
        note.updated_by = actor_id
        note.model_version += 1
        await session.flush()

        await self._publish(session, "NoteSigned", {"note_id": str(note.id), "signed_by": str(payload.signed_by)})
        return note

    async def cancel_note(self, session: AsyncSession, note_id: UUID, actor_id: UUID) -> ClinicalNote:
        note = await self.get_note(session, note_id)
        if not note:
            raise DocumentationError("NOTE_NOT_FOUND", "Note not found")
        note.status = "CANCELLED"
        note.updated_by = actor_id
        note.model_version += 1
        return note

    async def list_versions(self, session: AsyncSession, note_id: UUID) -> list[NoteVersion]:
        stmt = select(NoteVersion).where(NoteVersion.note_id == note_id, NoteVersion.deleted_at.is_(None)).order_by(NoteVersion.version_number)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    # ------------------------ Templates ------------------------

    async def create_template(self, session: AsyncSession, payload: TemplateCreate, actor_id: UUID) -> Template:
        tmpl = Template(
            name=payload.name,
            note_type=payload.note_type,
            content=payload.content,
            structured_schema=payload.structured_schema,
            is_active=payload.is_active,
            status="ACTIVE",
            created_by=actor_id,
            updated_by=actor_id,
        )
        session.add(tmpl)
        await session.flush()
        await self._publish(session, "TemplateCreated", {"name": tmpl.name, "note_type": tmpl.note_type})
        return tmpl

    async def get_template(self, session: AsyncSession, template_id: UUID) -> Template | None:
        return await session.get(Template, template_id)

    async def list_templates(self, session: AsyncSession, note_type: str | None = None, active_only: bool = True, limit: int = 50, offset: int = 0) -> list[Template]:
        stmt = select(Template).where(Template.deleted_at.is_(None))
        if active_only:
            stmt = stmt.where(Template.is_active.is_(True))
        if note_type:
            stmt = stmt.where(Template.note_type == note_type)
        stmt = stmt.order_by(Template.name).limit(limit).offset(offset)
        result = await session.execute(stmt)
        return list(result.scalars().all())

    async def update_template(self, session: AsyncSession, template_id: UUID, payload: TemplateUpdate, actor_id: UUID) -> Template:
        tmpl = await self.get_template(session, template_id)
        if not tmpl:
            raise DocumentationError("TEMPLATE_NOT_FOUND", "Template not found")
        data = payload.model_dump(exclude_unset=True)
        for k, v in data.items():
            setattr(tmpl, k, v)
        tmpl.updated_by = actor_id
        tmpl.model_version += 1
        return tmpl


service = DocumentationService()
