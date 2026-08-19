"""Tests for the knowledge-service (RAG) using the mock embedding adapter."""

from uuid import uuid4

import pytest

from knowledge_service.dto import schemas as dto
from knowledge_service.service import knowledge_service as svc
from knowledge_service.service.vector import cosine

SHORT_DOC = (
    "Acute myocardial infarction must be triaged as an emergency. "
    "Aspirin 300 mg is given immediately unless contraindicated. "
    "STEMI requires primary PCI within 90 minutes."
)


@pytest.mark.asyncio
async def test_upsert_document_chunks_and_embeds(service, session):
    doc = await service.upsert_document(
        session,
        dto.DocumentIn(doc_type="GUIDELINE", title="AMI Guideline", content=SHORT_DOC),
    )
    assert doc.status == "INDEXED"
    assert doc.chunk_count == 1
    chunks = await service.list_chunks(session, doc.id)
    assert len(chunks) == 1
    assert chunks[0].embedding is not None
    assert chunks[0].embedding_model == "mock-embed-v1"


@pytest.mark.asyncio
async def test_duplicate_document_conflict(service, session):
    payload = dto.DocumentIn(doc_type="GUIDELINE", title="AMI Guideline", content=SHORT_DOC)
    await service.upsert_document(session, payload)
    with pytest.raises(svc.KnowledgeError) as exc:
        await service.upsert_document(session, payload)
    assert exc.value.status_code == 409


@pytest.mark.asyncio
async def test_search_returns_relevant_hits(service, session):
    await service.upsert_document(
        session, dto.DocumentIn(doc_type="GUIDELINE", title="AMI", content=SHORT_DOC)
    )
    await service.upsert_document(
        session,
        dto.DocumentIn(
            doc_type="LAB_REFERENCE",
            title="Potassium",
            content="Serum potassium 3.5-5.1 mmol/L. Values below 3.0 are critical.",
        ),
    )
    result = await service.search(
        session,
        dto.SearchIn(query="STEMI primary PCI aspirin", top_k=5),
    )
    assert result.count >= 1
    assert all(hit.score >= 0.0 for hit in result.hits)
    assert any("AMI" in hit.document_title for hit in result.hits)


@pytest.mark.asyncio
async def test_search_doc_type_filter(service, session):
    await service.upsert_document(
        session, dto.DocumentIn(doc_type="GUIDELINE", title="AMI", content=SHORT_DOC)
    )
    result = await service.search(
        session, dto.SearchIn(query="STEMI aspirin", doc_type="POLICY", top_k=5)
    )
    assert result.count == 0


@pytest.mark.asyncio
async def test_access_log_written(service, session):
    await service.upsert_document(
        session, dto.DocumentIn(doc_type="GUIDELINE", title="AMI", content=SHORT_DOC)
    )
    await service.search(session, dto.SearchIn(query="STEMI", user_id=str(uuid4()), top_k=5))
    from sqlalchemy import select

    from knowledge_service.entity.models import KnowledgeAccessLog

    logs = (await session.execute(select(KnowledgeAccessLog))).scalars().all()
    assert len(logs) == 1
    assert logs[0].query == "STEMI"
    assert logs[0].permitted is True


@pytest.mark.asyncio
async def test_seed_defaults_idempotent(service, session):
    first = await service.seed_defaults(session)
    assert first >= 4
    second = await service.seed_defaults(session)
    assert second == 0
    corpora = await service.list_corpora(session)
    keys = {c.key for c in corpora}
    assert {"clinical_guidelines", "hospital_policies", "medication_database", "laboratory_reference"} <= keys


@pytest.mark.asyncio
async def test_set_document_status_and_remove(service, session):
    doc = await service.upsert_document(
        session, dto.DocumentIn(doc_type="POLICY", title="ID Policy", content="Two identifier check required.")
    )
    doc = await service.set_document_status(session, doc.id, "APPROVED")
    assert doc.status == "APPROVED"
    assert doc.published_at is not None
    await service.remove_document(session, doc.id, "superseded")
    from sqlalchemy import select

    from knowledge_service.entity.models import KnowledgeDocument

    row = (
        await session.execute(
            select(KnowledgeDocument).where(KnowledgeDocument.id == doc.id)
        )
    ).scalar_one()
    assert row.status == "RETIRED"
    assert row.deleted_at is not None


@pytest.mark.asyncio
async def test_embed_returns_normalized_vector(service):
    v = await service.embed_text("hello world")
    assert len(v) == 256
    norm = sum(x * x for x in v) ** 0.5
    assert abs(norm - 1.0) < 0.01


@pytest.mark.asyncio
async def test_cosine_similarity(service):
    a = await service.embed_text("STEMI aspirin guideline")
    b = await service.embed_text("STEMI aspirin guideline")
    c = await service.embed_text("potassium laboratory reference range")
    assert cosine(a, b) > 0.99
    assert cosine(a, c) < cosine(a, b)


@pytest.mark.asyncio
async def test_empty_content_rejected(service, session):
    with pytest.raises(svc.KnowledgeError) as exc:
        await service.upsert_document(
            session, dto.DocumentIn(doc_type="POLICY", title="Empty", content="   ")
        )
    assert exc.value.error_code == "EMPTY_CONTENT"