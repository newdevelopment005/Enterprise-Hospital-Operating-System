import uuid

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from clinical_documentation_service.dto.schemas import (
    ClinicalNoteCreate,
    ClinicalNoteUpdate,
    ClinicalNoteSign,
    TemplateCreate,
    TemplateUpdate,
)
from clinical_documentation_service.service.documentation_service import DocumentationService, DocumentationError


def _uid():
    return uuid.uuid4()


# ── Notes CRUD ────────────────────────────────────────────────────────────────


class TestClinicalNotes:
    async def test_create_note(self, db: AsyncSession, doc_service: DocumentationService):
        note = await doc_service.create_note(db, ClinicalNoteCreate(patient_id=_uid(), author_id=_uid(), note_type="SOAP", title="SOAP 1", content="S: ok"), _uid())
        assert note.id
        assert note.status == "DRAFT"
        assert note.note_type == "SOAP"

    async def test_create_all_note_types(self, db: AsyncSession, doc_service: DocumentationService):
        for nt in ["SOAP", "PROGRESS", "DISCHARGE", "PROCEDURE", "CONSULTATION", "H&P", "NURSING", "CONSENT"]:
            note = await doc_service.create_note(db, ClinicalNoteCreate(patient_id=_uid(), author_id=_uid(), note_type=nt), _uid())
            assert note.note_type == nt

    async def test_get_note(self, db: AsyncSession, doc_service: DocumentationService):
        created = await doc_service.create_note(db, ClinicalNoteCreate(patient_id=_uid(), author_id=_uid(), note_type="SOAP"), _uid())
        got = await doc_service.get_note(db, created.id)
        assert got is not None
        assert got.id == created.id

    async def test_list_notes(self, db: AsyncSession, doc_service: DocumentationService):
        pid = _uid()
        for _ in range(3):
            await doc_service.create_note(db, ClinicalNoteCreate(patient_id=pid, author_id=_uid(), note_type="SOAP"), _uid())
        notes = await doc_service.list_notes(db, patient_id=pid)
        assert len(notes) == 3

    async def test_list_notes_by_type(self, db: AsyncSession, doc_service: DocumentationService):
        pid = _uid()
        await doc_service.create_note(db, ClinicalNoteCreate(patient_id=pid, author_id=_uid(), note_type="SOAP"), _uid())
        await doc_service.create_note(db, ClinicalNoteCreate(patient_id=pid, author_id=_uid(), note_type="PROGRESS"), _uid())
        notes = await doc_service.list_notes(db, patient_id=pid, note_type="SOAP")
        assert len(notes) == 1
        assert notes[0].note_type == "SOAP"

    async def test_update_note(self, db: AsyncSession, doc_service: DocumentationService):
        created = await doc_service.create_note(db, ClinicalNoteCreate(patient_id=_uid(), author_id=_uid(), note_type="SOAP", content="old"), _uid())
        updated = await doc_service.update_note(db, created.id, ClinicalNoteUpdate(content="new"), _uid())
        assert updated.content == "new"
        assert updated.model_version == 2

    async def test_update_note_creates_version(self, db: AsyncSession, doc_service: DocumentationService):
        note = await doc_service.create_note(db, ClinicalNoteCreate(patient_id=_uid(), author_id=_uid(), note_type="SOAP", content="v1"), _uid())
        await doc_service.update_note(db, note.id, ClinicalNoteUpdate(content="v2", change_summary="Updated"), _uid())
        versions = await doc_service.list_versions(db, note.id)
        assert len(versions) == 1
        assert versions[0].version_number == 2
        assert versions[0].content == "v2"

    async def test_sign_note(self, db: AsyncSession, doc_service: DocumentationService):
        note = await doc_service.create_note(db, ClinicalNoteCreate(patient_id=_uid(), author_id=_uid(), note_type="SOAP"), _uid())
        signer = _uid()
        signed = await doc_service.sign_note(db, note.id, ClinicalNoteSign(signed_by=signer), _uid())
        assert signed.status == "FINAL"
        assert signed.signed_by == signer
        assert signed.signed_at is not None

    async def test_update_final_note_raises(self, db: AsyncSession, doc_service: DocumentationService):
        note = await doc_service.create_note(db, ClinicalNoteCreate(patient_id=_uid(), author_id=_uid(), note_type="SOAP"), _uid())
        await doc_service.sign_note(db, note.id, ClinicalNoteSign(signed_by=_uid()), _uid())
        with pytest.raises(DocumentationError, match="Cannot update signed note"):
            await doc_service.update_note(db, note.id, ClinicalNoteUpdate(content="bad"), _uid())

    async def test_cancel_note(self, db: AsyncSession, doc_service: DocumentationService):
        note = await doc_service.create_note(db, ClinicalNoteCreate(patient_id=_uid(), author_id=_uid(), note_type="SOAP"), _uid())
        cancelled = await doc_service.cancel_note(db, note.id, _uid())
        assert cancelled.status == "CANCELLED"

    async def test_sign_cancelled_note_raises(self, db: AsyncSession, doc_service: DocumentationService):
        note = await doc_service.create_note(db, ClinicalNoteCreate(patient_id=_uid(), author_id=_uid(), note_type="SOAP"), _uid())
        await doc_service.cancel_note(db, note.id, _uid())
        with pytest.raises(DocumentationError, match="Cannot sign cancelled note"):
            await doc_service.sign_note(db, note.id, ClinicalNoteSign(signed_by=_uid()), _uid())


# ── Templates CRUD ─────────────────────────────────────────────────────────────


class TestTemplates:
    async def test_create_template(self, db: AsyncSession, doc_service: DocumentationService):
        tmpl = await doc_service.create_template(db, TemplateCreate(name="SOAP Template", note_type="SOAP", content="SOAP content"), _uid())
        assert tmpl.id
        assert tmpl.name == "SOAP Template"
        assert tmpl.status == "ACTIVE"

    async def test_get_template(self, db: AsyncSession, doc_service: DocumentationService):
        created = await doc_service.create_template(db, TemplateCreate(name="T1", note_type="SOAP"), _uid())
        got = await doc_service.get_template(db, created.id)
        assert got is not None
        assert got.id == created.id

    async def test_list_templates(self, db: AsyncSession, doc_service: DocumentationService):
        for i in range(3):
            await doc_service.create_template(db, TemplateCreate(name=f"Template {i}", note_type="SOAP"), _uid())
        tmpls = await doc_service.list_templates(db)
        assert len(tmpls) == 3

    async def test_list_templates_by_type(self, db: AsyncSession, doc_service: DocumentationService):
        await doc_service.create_template(db, TemplateCreate(name="SOAP T", note_type="SOAP"), _uid())
        await doc_service.create_template(db, TemplateCreate(name="PROGRESS T", note_type="PROGRESS"), _uid())
        tmpls = await doc_service.list_templates(db, note_type="SOAP")
        assert len(tmpls) == 1

    async def test_update_template(self, db: AsyncSession, doc_service: DocumentationService):
        tmpl = await doc_service.create_template(db, TemplateCreate(name="Old", note_type="SOAP"), _uid())
        updated = await doc_service.update_template(db, tmpl.id, TemplateUpdate(name="New"), _uid())
        assert updated.name == "New"
        assert updated.model_version == 2

    async def test_deactivate_template(self, db: AsyncSession, doc_service: DocumentationService):
        tmpl = await doc_service.create_template(db, TemplateCreate(name="Active", note_type="SOAP"), _uid())
        updated = await doc_service.update_template(db, tmpl.id, TemplateUpdate(is_active=False), _uid())
        assert updated.is_active is False
        # inactive templates excluded from default list
        tmpls = await doc_service.list_templates(db, active_only=True)
        assert len(tmpls) == 0

    async def test_get_nonexistent_note(self, db: AsyncSession, doc_service: DocumentationService):
        assert await doc_service.get_note(db, _uid()) is None

    async def test_get_nonexistent_template(self, db: AsyncSession, doc_service: DocumentationService):
        assert await doc_service.get_template(db, _uid()) is None
