"""Integration tests: loaders -> ingestion -> vector search."""

import io
import json

import pytest

from knowledge_service.dto import schemas as dto
from knowledge_service.service import knowledge_service as svc


def _markdown(title: str, body: str) -> bytes:
    return f"# {title}\n\n{body}".encode()


def _journal_bytes() -> bytes:
    issue = {
        "journal_name": "Journal of Antimicrobial Stewardship",
        "volume": "5",
        "issue": "2",
        "articles": [
            {"title": "Antibiotic de-escalation", "authors": ["C. Researcher"],
             "abstract": "De-escalation reduces resistance.", "keywords": ["antibiotics"],
             "body": "Reassess antimicrobial therapy at 48-72 hours and de-escalate when possible."}
        ],
    }
    return json.dumps(issue).encode()


@pytest.mark.asyncio
async def test_ingest_markdown_guideline_is_searchable(service, session):
    result = await service.ingest_bytes(
        session,
        filename="sepsis.md",
        raw=_markdown("Sepsis Resuscitation Guideline", "Give 30 mL/kg crystalloid within 3 hours."),
        doc_type="GUIDELINE",
    )
    assert result.added == 1
    assert result.skipped == 0
    document = result.ingested[0]
    assert document.status == "APPROVED"
    assert document.source_format == "MARKDOWN"
    assert document.ingestion_ref == "sepsis.md"
    chunks = await service.list_chunks(session, document.id)
    assert len(chunks) >= 1
    assert chunks[0].embedding is not None

    hits = await service.search(session, dto.SearchIn(query="crystalloid fluid sepsis", top_k=5))
    assert any(hit.document_id == str(document.id) for hit in hits.hits)


@pytest.mark.asyncio
async def test_ingest_duplicate_is_skipped(service, session):
    raw = _markdown("Violence Prevention Policy", "Report escalating behavior immediately.")
    first = await service.ingest_bytes(session, filename="policy.md", raw=raw, doc_type="POLICY")
    second = await service.ingest_bytes(session, filename="policy.md", raw=raw, doc_type="POLICY")
    assert first.added == 1
    assert second.added == 0
    assert second.skipped == 1


@pytest.mark.asyncio
async def test_ingest_formulary_csv_all_searchable(service, session):
    csv_text = (
        "drug_name,generic_name,class,indications,interactions\n"
        "Paracetamol,acetaminophen,analgesic,fever,\n"
        "Amoxicillin,amoxicillin,beta-lactam,infections,\n"
    )
    result = await service.ingest_bytes(
        session, filename="formulary.csv", raw=csv_text.encode(), doc_type="MEDICATION"
    )
    assert result.added == 2
    febrile = await service.search(session, dto.SearchIn(query="paracetamol fever analgesic", top_k=5))
    assert any("Paracetamol" in h.document_title for h in febrile.hits)
    infectious = await service.search(session, dto.SearchIn(query="amoxicillin infection", top_k=5))
    assert any("Amoxicillin" in h.document_title for h in infectious.hits)


@pytest.mark.asyncio
async def test_ingest_journal_via_kind(service, session):
    result = await service.ingest_bytes(
        session,
        filename="issue.journal.json",
        raw=_journal_bytes(),
        doc_type="JOURNAL",
        kind="journal",
    )
    assert result.added == 1
    article = result.ingested[0]
    assert article.doc_type == "JOURNAL"
    assert article.source_format == "JOURNAL"
    hits = await service.search(session, dto.SearchIn(query="antimicrobial de-escalation resistance", top_k=5))
    assert any(hit.document_id == str(article.id) for hit in hits.hits)
    hit = next(h for h in hits.hits if h.document_id == str(article.id))
    assert hit.metadata is not None
    assert hit.metadata.get("journal") == "Journal of Antimicrobial Stewardship"


@pytest.mark.asyncio
async def test_ingest_pdf_roundtrip(service, session):
    from reportlab.pdfgen import canvas

    stream = io.BytesIO()
    c = canvas.Canvas(stream)
    c.drawString(72, 720, "Hypoglycemia: give 15 g fast-acting carbohydrate, recheck glucose in 15 minutes.")
    c.showPage()
    c.save()
    result = await service.ingest_bytes(
        session, filename="hypoglycemia.pdf", raw=stream.getvalue(), doc_type="GUIDELINE"
    )
    assert result.added == 1
    assert result.ingested[0].source_format == "PDF"
    hits = await service.search(session, dto.SearchIn(query="hypoglycemia carbohydrates glucose", top_k=5))
    assert hits.count >= 1


@pytest.mark.asyncio
async def test_ingest_title_override_single_document(service, session):
    raw = b"Wear PPE when handling chemotherapy waste."
    result = await service.ingest_bytes(
        session, filename="chemo.txt", raw=raw, doc_type="POLICY", title="Chemo Waste Policy"
    )
    assert result.ingested[0].title == "Chemo Waste Policy"


@pytest.mark.asyncio
async def test_ingest_payload_too_large(service, session):
    service.settings.max_upload_bytes = 100
    with pytest.raises(svc.KnowledgeError) as exc:
        await service.ingest_bytes(
            session, filename="big.txt", raw=b"x" * 200, doc_type="POLICY"
        )
    assert exc.value.error_code == "PAYLOAD_TOO_LARGE"
    assert exc.value.status_code == 413


@pytest.mark.asyncio
async def test_ingest_unsupported_json_rejected(service, session):
    with pytest.raises(svc.KnowledgeError) as exc:
        await service.ingest_bytes(
            session, filename="data.json", raw=b"{}", doc_type="POLICY"
        )
    assert exc.value.error_code == "UNSUPPORTED_FORMAT"


@pytest.mark.asyncio
async def test_ingest_http_multipart_endpoint(service, settings):
    import httpx
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

    from knowledge_service.entity.models import Base
    from knowledge_service.main import create_app

    engine = create_async_engine("sqlite+aiosqlite:///:memory:")
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    factory = async_sessionmaker(engine, expire_on_commit=False)

    class _StubDatabase:
        """Stand-in for app.state.database so get_session can open sessions."""

        def __init__(self, maker):
            self._maker = maker

        def session(self):
            return self._maker()

    app = create_app()
    app.state.database = _StubDatabase(factory)
    app.state.settings = settings
    app.state.knowledge_service = service

    async with factory() as initial:
        await service.seed_defaults(initial)

    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.post(
            "/api/v1/knowledge/ingest",
            data={"doc_type": "GUIDELINE", "auto_approve": "true"},
            files={"file": ("sepsis.md", _markdown("Sepsis Guideline", "Vasopressors after fluids."), "text/markdown")},
        )
    await engine.dispose()

    assert response.status_code == 201
    body = response.json()
    assert body["success"] is True
    assert body["data"]["added"] == 1
    assert body["data"]["ingested"][0]["source_format"] == "MARKDOWN"