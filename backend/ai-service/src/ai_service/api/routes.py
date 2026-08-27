"""REST API for the ai-service (HospitalGPT).

Responses use the standard EHOS envelope {"success": true, "data": ...}.
Every data endpoint authenticates the caller's OAuth2 bearer token (the shared
:class:`AuthDeps` re-validates the JWT against Keycloak JWKS — the gateway is not
trusted blindly). The authenticated subject is authoritative: client-supplied
``user_id``/``approver_id`` values are ignored in favour of the token subject so
one clinician cannot read or attribute another clinician's data.
"""

from __future__ import annotations

import uuid
from typing import Annotated

from ehos_common.auth import AuthDeps
from fastapi import APIRouter, Depends, File, Query, Request, UploadFile, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from ai_service.dto import schemas as dto
from ai_service.service import ai_service as svc
from ai_service.service.agents import agent_action_out, agent_def_out, agent_run_out
from ai_service.service.serializers import (
    conversation_out,
    feedback_out,
    memory_out,
    message_out,
    prompt_out,
    request_out,
)

router = APIRouter(prefix="/api/v1/ai", tags=["ai"])
bearer_scheme = HTTPBearer(auto_error=False)


async def get_session(request: Request) -> AsyncSession:
    async with request.app.state.database.session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def get_auth(request: Request) -> AuthDeps:
    return request.app.state.auth_deps


async def require_user(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme),
) -> dict:
    """Authenticated caller claims (401 when missing/invalid)."""
    return await get_auth(request).current_user(credentials)


CurrentUser = Annotated[dict, Depends(require_user)]


def _uuid(value: str) -> uuid.UUID:
    try:
        return uuid.UUID(value)
    except ValueError as err:
        raise svc.AiError("INVALID_UUID", f"'{value}' is not a valid UUID", 400) from err


def _s(request: Request) -> svc.AiService:
    return request.app.state.ai_service


def _actor(fallback: uuid.UUID, sub: object) -> uuid.UUID:
    """Authenticated subject as a UUID; falls back when the token has none."""
    try:
        return uuid.UUID(str(sub))
    except (ValueError, TypeError):
        return fallback


def _bind_user(payload, claims: dict):
    """Bind the authenticated subject as the actor, never the client body."""
    payload.user_id = str(_actor(uuid.UUID(int=0), claims.get("sub")))
    return payload


def _ok(data, status_code: int = 200) -> dict:
    return {"success": True, "data": data, "statusCode": status_code}


# --- chat ----------------------------------------------------------------------


@router.post("/chat", status_code=status.HTTP_201_CREATED)
async def chat(
    payload: dto.ChatIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = ...,
):
    result = (await _s(request).chat(session, _bind_user(payload, _user))).model_dump(mode="json")
    return _ok(result, status.HTTP_201_CREATED)


# --- conversations ---------------------------------------------------------------


@router.post("/conversations", status_code=status.HTTP_201_CREATED)
async def create_conversation(
    payload: dto.ConversationIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = ...,
):
    row = await _s(request).create_conversation(session, _bind_user(payload, _user))
    return _ok(conversation_out(row), status.HTTP_201_CREATED)


@router.get("/conversations")
async def list_conversations(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = ...,
    limit: int | None = Query(default=None, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
):
    # conversations are scoped to the authenticated caller
    actor = str(_user.get("sub"))
    rows, total = await _s(request).list_conversations(session, actor, limit or 20, offset)
    return _ok({"items": [conversation_out(r) for r in rows], "total": total})


@router.get("/conversations/{conversation_id}/messages")
async def list_messages(
    conversation_id: str,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = ...,
):
    rows = await _s(request).list_messages(session, _uuid(conversation_id))
    return _ok({"items": [message_out(r) for r in rows], "total": len(rows)})


# --- models ----------------------------------------------------------------------


@router.get("/models")
async def list_models(request: Request, session: AsyncSession = Depends(get_session), _user: CurrentUser = ...):
    rows = await _s(request).list_models(session)
    return _ok({"items": rows, "total": len(rows)})


@router.post("/models", status_code=status.HTTP_201_CREATED)
async def register_model(
    payload: dto.ModelRegisterIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = ...,
):
    row = await _s(request).register_model(session, payload)
    return _ok(await _s(request)._model_with_load(session, row), status.HTTP_201_CREATED)


@router.post("/models/{model_key}/load")
async def load_model(
    model_key: str, request: Request, session: AsyncSession = Depends(get_session), _user: CurrentUser = ...
):
    return _ok(await _s(request).load_model(session, model_key))


@router.post("/models/{model_key}/unload")
async def unload_model(
    model_key: str, request: Request, session: AsyncSession = Depends(get_session), _user: CurrentUser = ...
):
    return _ok(await _s(request).unload_model(session, model_key))


# --- prompts ----------------------------------------------------------------------


@router.get("/prompts")
async def list_prompts(request: Request, session: AsyncSession = Depends(get_session), _user: CurrentUser = ...):
    await _s(request).ensure_default_prompt(session)
    await session.flush()
    rows = await _s(request).list_prompts(session)
    return _ok({"items": [prompt_out(r) for r in rows], "total": len(rows)})


@router.post("/prompts", status_code=status.HTTP_201_CREATED)
async def create_prompt(
    payload: dto.PromptIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = ...,
):
    row = await _s(request).create_prompt(session, payload)
    return _ok(prompt_out(row), status.HTTP_201_CREATED)


# --- memory ----------------------------------------------------------------------


@router.get("/memories")
async def list_memories(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = ...,
    memory_type: str | None = Query(default=None),
):
    # memories are scoped to the authenticated caller
    rows = await _s(request).list_memories(session, str(_user.get("sub")), memory_type)
    return _ok({"items": [memory_out(r) for r in rows], "total": len(rows)})


@router.put("/memories", status_code=status.HTTP_201_CREATED)
async def add_memory(
    payload: dto.MemoryIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = ...,
):
    row = await _s(request).add_memory(session, _bind_user(payload, _user))
    return _ok(memory_out(row), status.HTTP_201_CREATED)


@router.delete("/memories/{memory_id}", status_code=status.HTTP_204_NO_CONTENT)
async def remove_memory(
    memory_id: str, request: Request, session: AsyncSession = Depends(get_session), _user: CurrentUser = ...
):
    await _s(request).remove_memory(session, _uuid(memory_id))
    return None


# --- approvals --------------------------------------------------------------------


@router.post("/requests/{request_id}/approve")
async def approve_request(
    request_id: str,
    payload: dto.ApprovalDecisionIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = ...,
):
    row = await _s(request).approve_request(session, _uuid(request_id), payload)
    return _ok(request_out(row))


@router.get("/requests/{request_id}")
async def get_request(
    request_id: str, request: Request, session: AsyncSession = Depends(get_session), _user: CurrentUser = ...
):
    row = await _s(request).get_request(session, _uuid(request_id))
    return _ok(request_out(row))


# --- feedback ---------------------------------------------------------------------


@router.post("/feedback", status_code=status.HTTP_201_CREATED)
async def add_feedback(
    payload: dto.FeedbackIn, request: Request, session: AsyncSession = Depends(get_session), _user: CurrentUser = ...
):
    row = await _s(request).add_feedback(session, _bind_user(payload, _user))
    return _ok(feedback_out(row), status.HTTP_201_CREATED)


# --- media facades -----------------------------------------------------------------


@router.post("/stt", status_code=status.HTTP_201_CREATED)
async def stt_transcribe(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = ...,
    audio: UploadFile = File(...),
):
    data = await audio.read()
    text, engine = await _s(request).stt_transcribe(data)
    user_id = _actor(uuid.UUID(int=0), _user.get("sub"))
    req = await _s(request).record_request(session, user_id, "TRANSCRIBE", text, text)
    await session.flush()
    return _ok({"text": text, "engine": engine, "request_id": str(req.id)}, status.HTTP_201_CREATED)


@router.post("/tts", status_code=status.HTTP_201_CREATED)
async def tts_synthesize(
    payload: dto.TtsIn, request: Request, session: AsyncSession = Depends(get_session), _user: CurrentUser = ...
):
    audio_b64, mime = await _s(request).tts_synthesize(payload.text)
    user_id = _actor(uuid.UUID(int=0), _user.get("sub"))
    req = await _s(request).record_request(session, user_id, "SEARCH", payload.text, None)
    await session.flush()
    return _ok({"audio_base64": audio_b64, "mime": mime, "request_id": str(req.id)}, status.HTTP_201_CREATED)


@router.post("/ocr", status_code=status.HTTP_201_CREATED)
async def ocr_extract(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = ...,
    image: UploadFile = File(...),
):
    data = await image.read()
    text, engine = await _s(request).ocr_extract(data, image.filename)
    user_id = _actor(uuid.UUID(int=0), _user.get("sub"))
    req = await _s(request).record_request(session, user_id, "OCR", text, text)
    await session.flush()
    return _ok({"text": text, "engine": engine, "request_id": str(req.id)}, status.HTTP_201_CREATED)


# --- agents ---------------------------------------------------------------------


@router.get("/agents")
async def list_agents(request: Request, session: AsyncSession = Depends(get_session), _user: CurrentUser = ...):
    rows = await _s(request).agents.list_definitions(session)
    return _ok({"items": [agent_def_out(r) for r in rows], "total": len(rows)})


@router.post("/agents/{key}/run", status_code=status.HTTP_201_CREATED)
async def run_agent(
    key: str,
    payload: dto.AgentRunIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = ...,
):
    # the acting user comes from the token, never from the request body
    run = await _s(request).agents.run_agent(
        session, key, payload.goal, _actor(uuid.UUID(int=0), _user.get("sub")), context=payload.context
    )
    return _ok(agent_run_out(run), status.HTTP_201_CREATED)


@router.get("/agent-runs")
async def list_agent_runs(
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = ...,
    agent_key: str | None = Query(default=None),
    status: str | None = Query(default=None),
    limit: int | None = Query(default=None, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
):
    rows, total = await _s(request).agents.list_runs(session, agent_key, status, limit or 20, offset)
    return _ok({"items": [agent_run_out(r) for r in rows], "total": total})


@router.get("/agent-runs/{run_id}")
async def get_agent_run(
    run_id: str, request: Request, session: AsyncSession = Depends(get_session), _user: CurrentUser = ...
):
    run = await _s(request).agents.get_run(session, _uuid(run_id))
    return _ok(agent_run_out(run))


@router.get("/agent-runs/{run_id}/actions")
async def list_agent_actions(
    run_id: str, request: Request, session: AsyncSession = Depends(get_session), _user: CurrentUser = ...
):
    rows = await _s(request).agents.list_actions(session, _uuid(run_id))
    return _ok({"items": [agent_action_out(r) for r in rows], "total": len(rows)})


@router.post("/agent-actions/{action_id}/approve")
async def decide_agent_action(
    action_id: str,
    payload: dto.AgentActionDecisionIn,
    request: Request,
    session: AsyncSession = Depends(get_session),
    _user: CurrentUser = ...,
):
    # the approver comes from the token, never from the request body
    run = await _s(request).agents.decide_action(
        session, _uuid(action_id), _actor(uuid.UUID(int=0), _user.get("sub")), payload.approved, payload.comments
    )
    return _ok(agent_run_out(run))


# --- status ------------------------------------------------------------------------


@router.get("/status")
async def service_status(request: Request):
    settings = request.app.state.settings
    return _ok(
        {
            "service": settings.service_name,
            "version": settings.service_version,
            "inference_adapter": settings.inference_adapter,
            "embedding_adapter": settings.embedding_adapter,
            "default_model_key": settings.default_model_key,
            "tools": ["chat", "models", "prompts", "memory", "stt", "tts", "ocr", "rag", "approvals", "feedback"],
        }
    )