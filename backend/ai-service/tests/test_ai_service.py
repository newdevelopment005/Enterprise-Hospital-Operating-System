"""Tests for the ai-service (HospitalGPT) using mock adapters."""

import uuid

import pytest
from sqlalchemy import select

from ai_service.dto import schemas as dto
from ai_service.entity import models as ent
from ai_service.service import ai_service as svc


@pytest.mark.asyncio
async def test_chat_creates_conversation_and_requests(service, session):
    await service.ensure_default_prompt(session)
    await session.flush()
    payload = dto.ChatIn(message="Summarize what the STEMI guideline says.", user_id=str(uuid.uuid4()), use_rag=False)
    result = await service.chat(session, payload)
    assert result.conversation_id
    assert result.request_id
    assert result.retrieved is False
    messages = await service.list_messages(session, uuid.UUID(result.conversation_id))
    assert len(messages) == 2
    assert messages[0].role == "USER"
    assert messages[1].role == "ASSISTANT"


@pytest.mark.asyncio
async def test_chat_refuses_without_context(service, session):
    await service.ensure_default_prompt(session)
    await session.flush()
    result = await service.chat(session, dto.ChatIn(message="purely hypothetical question", use_rag=False))
    assert "do not have enough verified information" in result.answer or "Summary:" in result.answer
    # approval is level 1 for CHAT -> no approval row
    request = await service.get_request(session, uuid.UUID(result.request_id))
    assert request.approval_level == 1
    assert request.approval_status == "NO_APPROVAL_REQUIRED"


@pytest.mark.asyncio
async def test_request_audit_logged(service, session):
    await service.ensure_default_prompt(session)
    await session.flush()
    user_id = uuid.uuid4()
    await service.chat(session, dto.ChatIn(message="hello", user_id=str(user_id), use_rag=False))
    rows = (await session.execute(select(ent.AiRequest))).scalars().all()
    assert len(rows) == 1
    assert rows[0].user_id == user_id
    assert rows[0].input_ref == "hello"
    assert rows[0].response_hash is not None


@pytest.mark.asyncio
async def test_models_default_registry_and_load(service, session):
    models = await service.list_models(session)
    keys = {m["model_key"] for m in models}
    assert {
        "llama-3.1-8b",
        "qwen-2.5-7b",
        "mistral-7b",
        "gemma-2-9b",
    } <= keys
    loaded = await service.load_model(session, "llama-3.1-8b")
    assert loaded["load_status"] == "LOADED"
    unloaded = await service.unload_model(session, "llama-3.1-8b")
    assert unloaded["load_status"] == "UNLOADED"


@pytest.mark.asyncio
async def test_load_missing_model_404(service, session):
    with pytest.raises(svc.AiError) as exc:
        await service.load_model(session, "does-not-exist")
    assert exc.value.status_code == 404


@pytest.mark.asyncio
async def test_prompt_default_and_create_conflict(service, session):
    default = await service.ensure_default_prompt(session)
    assert default.code == "hospitalgpt_system"
    payload = dto.PromptIn(code="triage_prompt", name="Triage", template="You triage locally: {{query}}")
    row = await service.create_prompt(session, payload)
    assert row.code == "triage_prompt"
    with pytest.raises(svc.AiError) as exc:
        await service.create_prompt(session, payload)
    assert exc.value.error_code == "PROMPT_EXISTS"


@pytest.mark.asyncio
async def test_memory_lifecycle(service, session):
    user_id = uuid.uuid4()
    row = await service.add_memory(
        session,
        dto.MemoryIn(user_id=str(user_id), memory_type="FACT", content="ED policy: two identifiers"),
    )
    assert row.importance == 1
    rows = await service.list_memories(session, user_id=str(user_id), memory_type=None)
    assert len(rows) == 1
    await service.remove_memory(session, row.id)
    rows = await service.list_memories(session, user_id=str(user_id), memory_type=None)
    assert len(rows) == 0


@pytest.mark.asyncio
async def test_feedback_linked_to_request(service, session):
    await service.ensure_default_prompt(session)
    await session.flush()
    result = await service.chat(session, dto.ChatIn(message="hi", use_rag=False))
    feedback = await service.add_feedback(
        session, dto.FeedbackIn(ai_request_id=result.request_id, user_id=str(uuid.uuid4()), rating=4, comment="good")
    )
    assert feedback.rating == 4


@pytest.mark.asyncio
async def test_approval_flow_level3(service, session):
    user_id = uuid.uuid4()
    request = await service.record_request(session, user_id, "AGENT", "propose restock", None, approval_level=3)
    assert request.approval_status == "PENDING"
    from sqlalchemy import select

    approvals = (
        await session.execute(
            select(ent.AiRequestApproval).where(ent.AiRequestApproval.ai_request_id == request.id)
        )
    ).scalars().all()
    assert len(approvals) == 1
    await service.approve_request(
        session, request.id, dto.ApprovalDecisionIn(approver_id=str(uuid.uuid4()), approved=True)
    )
    assert request.approval_status == "APPROVED"


@pytest.mark.asyncio
async def test_tts_returns_wav(service, session):
    audio_b64, mime = await service.tts_synthesize("good morning")
    assert mime == "audio/wav"
    import base64
    import wave  # noqa: F401

    header = base64.b64decode(audio_b64)[:4]
    assert header == b"RIFF"


@pytest.mark.asyncio
async def test_stt_returns_text(service, session):
    text, engine = await service.stt_transcribe(b"simple note: stable vital signs")
    assert engine == "mock"
    assert "vital signs" in text


@pytest.mark.asyncio
async def test_ocr_returns_text(service, session):
    text, engine = await service.ocr_extract(b"report shows creatinine 1.1", "report.txt")
    assert engine == "mock"
    assert "creatinine" in text


@pytest.mark.asyncio
async def test_request_type_chat_valid(service):
    import pydantic

    with pytest.raises(pydantic.ValidationError):
        dto.ChatIn(message="hi", request_type="BOGUS")


@pytest.mark.asyncio
async def test_context_window_build(service):
    msgs = [(("USER" if i % 2 == 0 else "ASSISTANT"), f"turn {i}") for i in range(30)]
    built = service.memory.build_conversation(msgs)
    assert built.count("turn 0") == 0  # pruned, only last 24 kept
    assert "turn 29" in built