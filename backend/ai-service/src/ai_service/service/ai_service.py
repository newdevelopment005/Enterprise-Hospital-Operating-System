"""AiService: HospitalGPT orchestration.

Coordinates the AI Gateway (audit log + approvals), Model Manager, Inference
Engine, Prompt Manager, Memory Manager, RAG bridge, and media facades.
"""

from __future__ import annotations

import base64
import hashlib
import re
import uuid
import wave
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from ai_service.configuration import AiSettings
from ai_service.dto import schemas as dto
from ai_service.entity import models as ent
from ai_service.service import engines as eng
from ai_service.service.agents import AgentRuntime
from ai_service.service.knowledge_client import KnowledgeClient

AiError = eng.AiError

DEFAULT_PROMPT_TEMPLATE = """You are the EHOS Local AI Intelligence Layer (HospitalGPT).
You assist healthcare professionals with approved, local knowledge only.
You never diagnose, never prescribe, and never access unauthorized data.
If you cannot answer from the provided context, say: 'I do not have enough verified information to answer this safely.'
Answer in the form: Summary / Key Information / Risks / Recommended Next Steps / Human Approval Required.
Use the conversation history to resolve follow-up questions: combine prior questions and answers
with the new user question into one coherent reply.

Conversation history:
{{conversation}}

Retrieved local knowledge:
{{context}}
User question: {{query}}

Answer:"""

APPROVAL_BY_REQUEST_TYPE: dict[str, int] = {
    "CHAT": 1,
    "SUMMARIZE": 1,
    "SEARCH": 1,
    "DOCUMENT": 1,
    "ANALYZE": 2,
    "PREDICT": 2,
    "AGENT": 3,
    "TRANSCRIBE": 1,
    "OCR": 1,
}


class AiService:
    """Owns all HospitalGPT operations."""

    def __init__(self, settings: AiSettings):
        self.settings = settings
        self.inference = eng.InferenceEngine(settings)
        self.embeddings = eng.EmbeddingEngine(settings)
        self.prompts = eng.PromptManager(settings)
        self.memory = eng.MemoryManager(settings)
        self.models = eng.ModelManager(settings)
        self.rag = KnowledgeClient(settings)
        self.agents = AgentRuntime(settings)

    # --- audit: AI Gateway ----------------------------------------------------

    async def _apply_approval_level(
        self, session: AsyncSession, request_type: str, action_level: int | None
    ) -> tuple[int, str]:
        """Determine approval_level and initial approval_status for a request."""
        level = action_level or APPROVAL_BY_REQUEST_TYPE.get(request_type, 1)
        status = "PENDING" if level in (2, 3) else "NO_APPROVAL_REQUIRED"
        return level, status

    async def record_request(
        self,
        session: AsyncSession,
        user_id: uuid.UUID,
        request_type: str,
        payload_in: str,
        response_out: str | None,
        model_family: str = "LLM",
        context_type: str | None = None,
        context_ref: uuid.UUID | None = None,
        latency_ms: int | None = None,
        tokens_in: int | None = None,
        tokens_out: int | None = None,
        approval_level: int | None = None,
    ) -> ent.AiRequest:
        """Append-only audit log entry (AI Gateway)."""
        model_row = (
            await session.execute(
                select(ent.AiModel).where(
                    ent.AiModel.family == model_family,
                    ent.AiModel.status == "ACTIVE",
                )
            )
        ).scalars().first()
        level, status = await self._apply_approval_level(session, request_type, approval_level)
        request = ent.AiRequest(
            request_id=str(uuid.uuid4()),
            user_id=user_id,
            model_id=model_row.id if model_row else None,
            request_type=request_type,
            context_type=context_type,
            context_ref=context_ref,
            input_ref=payload_in[:4000],
            input_hash=hashlib.sha256(payload_in.encode("utf-8")).hexdigest(),
            response_ref=response_out,
            response_hash=hashlib.sha256(response_out.encode("utf-8")).hexdigest() if response_out else None,
            approval_level=level,
            approval_status=status,
            latency_ms=latency_ms,
            tokens_in=tokens_in,
            tokens_out=tokens_out,
            completed_at=datetime.now(UTC),
        )
        session.add(request)
        await session.flush()
        if level >= 2:
            session.add(
                ent.AiRequestApproval(
                    ai_request_id=request.id,
                    level=level,
                    required_role=_role_for_level(level),
                    status="PENDING",
                )
            )
        return request

    async def approve_request(
        self, session: AsyncSession, request_id: uuid.UUID, decision: dto.ApprovalDecisionIn
    ) -> ent.AiRequest:
        request = await self.get_request(session, request_id)
        if request.approval_status not in ("PENDING",):
            raise eng.AiError("ALREADY_DECIDED", "request already decided", 409)
        request.approval_status = "APPROVED" if decision.approved else "REJECTED"
        approval = (
            await session.execute(
                select(ent.AiRequestApproval).where(ent.AiRequestApproval.ai_request_id == request.id)
            )
        ).scalar_one_or_none()
        if approval is not None:
            approval.status = "APPROVED" if decision.approved else "REJECTED"
            approval.approver_id = uuid.UUID(decision.approver_id)
            approval.decided_at = datetime.now(UTC)
            approval.comments = decision.comments
        return request

    async def get_request(self, session: AsyncSession, request_id: uuid.UUID) -> ent.AiRequest:
        row = (await session.execute(select(ent.AiRequest).where(ent.AiRequest.id == request_id))).scalar_one_or_none()
        if row is None:
            raise eng.AiError("NOT_FOUND", "ai request not found", 404)
        return row

    # --- chat -----------------------------------------------------------------

    async def chat(self, session: AsyncSession, payload: dto.ChatIn) -> dto.ChatOut:
        user_id = uuid.UUID(payload.user_id) if payload.user_id else uuid.UUID(int=0)
        conversation = await self.ensure_conversation_id(session, payload, user_id)

        turns = await self._conversation_turns(session, conversation.id)
        rendered_conversation = self.memory.build_conversation(turns)

        sources: list[dto.SourceRef] = []
        context_text = ""
        retrieved = False
        if payload.use_rag:
            sources = await self.rag.search(payload.message, user_id=str(user_id))
            retrieved = bool(sources)
            context_text = "\n".join(
                f"[{s.doc_type}] {s.document_title}\n{s.score:.3f}" for s in sources
            )

        template = await self._system_template(session, conversation.system_prompt_code)
        prompt = self.prompts.render(
            template,
            conversation=rendered_conversation,
            context=context_text,
            query=payload.message,
            model_key=payload.model_key or self.settings.default_model_key,
        )

        model_key = payload.model_key or self.settings.default_model_key
        try:
            result = await self.inference.complete(model_key, prompt)
        except eng.AiError as err:
            await self._log_failed(session, user_id, payload, str(err))
            raise

        request = await self.record_request(
            session,
            user_id,
            payload.request_type,
            payload.message,
            result.text,
            context_type="CONVERSATION",
            context_ref=conversation.id,
            latency_ms=result.latency_ms,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
        )

        # Explicit microsecond-precise timestamps keep USER/ASSISTANT turns in
        # insertion order (server_default now() has second precision, and the
        # UUID id tiebreaker is random).
        user_turn_at = datetime.now(UTC)
        assistant_turn_at = user_turn_at + timedelta(microseconds=1)
        session.add(
            ent.AiMessage(
                conversation_id=conversation.id,
                role="USER",
                content=payload.message,
                request_id=request.id,
                created_at=user_turn_at,
            )
        )
        session.add(
            ent.AiMessage(
                conversation_id=conversation.id,
                role="ASSISTANT",
                content=result.text,
                tokens_in=result.tokens_in,
                tokens_out=result.tokens_out,
                latency_ms=result.latency_ms,
                request_id=request.id,
                sources={"items": [s.model_dump() for s in sources]} if sources else None,
                created_at=assistant_turn_at,
            )
        )
        conversation.last_message_at = datetime.now(UTC)
        if not conversation.title:
            conversation.title = payload.message[:60]
        await session.flush()

        return dto.ChatOut(
            answer=result.text,
            request_id=str(request.id),
            conversation_id=str(conversation.id),
            model_key=model_key,
            sources=sources,
            retrieved=retrieved,
            tokens_in=result.tokens_in,
            tokens_out=result.tokens_out,
            latency_ms=result.latency_ms,
        )

    async def _log_failed(
        self, session: AsyncSession, user_id: uuid.UUID, payload: dto.ChatIn, error: str
    ) -> None:
        request = await self.record_request(session, user_id, payload.request_type, payload.message, None)
        request.error = error[:2000]
        request.completed_at = datetime.now(UTC)

    async def ensure_conversation_id(
        self, session: AsyncSession, payload: dto.ChatIn, user_id: uuid.UUID
    ) -> ent.AiConversation:
        if payload.conversation_id:
            conversation = (
                await session.execute(
                    select(ent.AiConversation).where(
                        ent.AiConversation.id == uuid.UUID(payload.conversation_id),
                        ent.AiConversation.deleted_at.is_(None),
                    )
                )
            ).scalar_one_or_none()
            if conversation is None:
                raise eng.AiError("NOT_FOUND", "conversation not found", 404)
            return conversation
        conversation = ent.AiConversation(
            user_id=user_id,
            model_key=payload.model_key or self.settings.default_model_key,
            system_prompt_code=self.settings.default_system_prompt_code,
        )
        session.add(conversation)
        await session.flush()
        return conversation

    async def _system_template(self, session: AsyncSession, code: str | None) -> str:
        code = code or self.settings.default_system_prompt_code
        row = (
            await session.execute(
                select(ent.PromptTemplate).where(
                    ent.PromptTemplate.code == code, ent.PromptTemplate.is_active.is_(True)
                )
            )
        ).scalar_one_or_none()
        if row is not None:
            return row.template
        return DEFAULT_PROMPT_TEMPLATE

    async def _conversation_turns(self, session: AsyncSession, conversation_id: uuid.UUID) -> list[tuple[str, str]]:
        rows = (
            await session.execute(
                select(ent.AiMessage)
                .where(
                    ent.AiMessage.conversation_id == conversation_id,
                    ent.AiMessage.deleted_at.is_(None),
                )
                .order_by(ent.AiMessage.created_at, ent.AiMessage.id)
            )
        ).scalars().all()
        return [(row.role, row.content) for row in rows]

    # --- conversations --------------------------------------------------------

    async def create_conversation(self, session: AsyncSession, payload: dto.ConversationIn) -> ent.AiConversation:
        conversation = ent.AiConversation(
            user_id=uuid.UUID(payload.user_id),
            agent_key=payload.agent_key,
            title=payload.title,
            model_key=payload.model_key,
            system_prompt_code=payload.system_prompt_code or self.settings.default_system_prompt_code,
        )
        session.add(conversation)
        await session.flush()
        return conversation

    async def list_conversations(
        self, session: AsyncSession, user_id: str | None, limit: int, offset: int
    ) -> tuple[list[ent.AiConversation], int]:
        stmt = select(ent.AiConversation).where(ent.AiConversation.deleted_at.is_(None))
        count_stmt = select(func.count()).select_from(stmt.subquery())
        if user_id:
            stmt = stmt.where(ent.AiConversation.user_id == uuid.UUID(user_id))
            count_stmt = select(func.count()).select_from(
                select(ent.AiConversation)
                .where(ent.AiConversation.deleted_at.is_(None), ent.AiConversation.user_id == uuid.UUID(user_id))
                .subquery()
            )
        total = (await session.execute(count_stmt)).scalar_one()
        stmt = stmt.order_by(ent.AiConversation.created_at.desc()).limit(limit).offset(offset)
        rows = (await session.execute(stmt)).scalars().all()
        return list(rows), total

    async def list_messages(
        self, session: AsyncSession, conversation_id: uuid.UUID
    ) -> list[ent.AiMessage]:
        rows = (
            await session.execute(
                select(ent.AiMessage)
                .where(ent.AiMessage.conversation_id == conversation_id, ent.AiMessage.deleted_at.is_(None))
                .order_by(ent.AiMessage.created_at, ent.AiMessage.id)
            )
        ).scalars().all()
        return list(rows)

    # --- models ---------------------------------------------------------------

    async def list_models(self, session: AsyncSession) -> list[dict]:
        rows = (
            await session.execute(
                select(ent.AiModel).where(ent.AiModel.deleted_at.is_(None)).order_by(ent.AiModel.created_at)
            )
        ).scalars().all()
        if not rows:
            for spec in self.models.DEFAULT_MODELS:
                rows.append(
                    await self._register_model(
                        session, parent_id=None, spec=spec, approved=True
                    )
                )
            rows = (
                await session.execute(
                    select(ent.AiModel).where(ent.AiModel.deleted_at.is_(None)).order_by(ent.AiModel.created_at)
                )
            ).scalars().all()
        return [await self._model_with_load(session, m) for m in rows]

    async def register_model(self, session: AsyncSession, payload: dto.ModelRegisterIn) -> ent.AiModel:
        return await self._register_model(
            session, parent_id=None, spec=payload.model_dump(), approved=payload.approved
        )

    async def _register_model(
        self, session: AsyncSession, parent_id: uuid.UUID | None, spec: dict, approved: bool = False
    ) -> ent.AiModel:
        existing = (
            await session.execute(select(ent.AiModel).where(ent.AiModel.model_key == spec["model_key"]))
        ).scalar_one_or_none()
        if existing is not None:
            return existing
        model = ent.AiModel(
            model_key=spec["model_key"],
            family=spec["family"],
            base_name=spec["base_name"],
            model_version=spec["version"],
            quantization=spec.get("quantization"),
            context_window=spec.get("context_window"),
            purpose=spec.get("purpose"),
            artifact_ref=spec.get("artifact_ref"),
            approval_status="APPROVED" if approved else "PENDING",
            approved_at=datetime.now(UTC) if approved else None,
        )
        session.add(model)
        await session.flush()
        session.add(ent.AiModelLoad(model_id=model.id, runtime=self.settings.inference_adapter, load_status="UNLOADED"))
        return model

    async def load_model(self, session: AsyncSession, model_key: str) -> dict:
        model = (
            await session.execute(select(ent.AiModel).where(ent.AiModel.model_key == model_key))
        ).scalar_one_or_none()
        if model is None:
            raise eng.AiError("MODEL_NOT_FOUND", f"model '{model_key}' not found", 404)
        if self.settings.inference_adapter == "mock":
            # Mock adapter always "loads" without a runtime process.
            load = await self._upsert_load(session, model.id, "LOADED", None)
        elif self.settings.inference_adapter in ("ollama", "llamacpp", "openai"):
            await self._ping_runtime()
            base_url = {
                "ollama": self.settings.ollama_base_url,
                "llamacpp": self.settings.llamacpp_base_url,
                "openai": self.settings.openai_base_url,
            }[self.settings.inference_adapter]
            load = await self._upsert_load(session, model.id, "LOADED", base_url)
        else:
            raise eng.AiError("RUNTIME_UNKNOWN", f"unknown adapter {self.settings.inference_adapter}", 400)
        model.approval_status = "APPROVED"
        await session.flush()
        return await self._model_with_load(session, model, load)

    async def unload_model(self, session: AsyncSession, model_key: str) -> dict:
        model = (
            await session.execute(select(ent.AiModel).where(ent.AiModel.model_key == model_key))
        ).scalar_one_or_none()
        if model is None:
            raise eng.AiError("MODEL_NOT_FOUND", f"model '{model_key}' not found", 404)
        load = await self._upsert_load(session, model.id, "UNLOADED", None, error=None)
        await session.flush()
        return await self._model_with_load(session, model, load)

    async def _ping_runtime(self) -> None:
        import urllib.parse

        base = {
            "ollama": self.settings.ollama_base_url,
            "llamacpp": self.settings.llamacpp_base_url,
            "openai": self.settings.openai_base_url,
        }[self.settings.inference_adapter]
        tags_or_health = {
            "ollama": "api/tags",
            "llamacpp": "health",
            "openai": "models",
        }[self.settings.inference_adapter]
        url = urllib.parse.urljoin(base.rstrip("/") + "/", tags_or_health)
        headers = {}
        if self.settings.inference_adapter == "openai" and self.settings.openai_api_key:
            headers["Authorization"] = f"Bearer {self.settings.openai_api_key}"
        try:
            import httpx

            async with httpx.AsyncClient(timeout=5.0) as client:
                await client.get(url, headers=headers)
        except httpx.HTTPError as err:
            raise eng.AiError("RUNTIME_UNAVAILABLE", f"local runtime unavailable: {err}", 503) from err

    async def _upsert_load(
        self,
        session: AsyncSession,
        model_id: uuid.UUID,
        load_status: str,
        base_url: str | None,
        error: str | None = None,
    ) -> ent.AiModelLoad:
        load = (
            await session.execute(
                select(ent.AiModelLoad).where(
                    ent.AiModelLoad.model_id == model_id, ent.AiModelLoad.deleted_at.is_(None)
                )
            )
        ).scalar_one_or_none()
        if load is None:
            load = ent.AiModelLoad(model_id=model_id, runtime=self.settings.inference_adapter)
            session.add(load)
            await session.flush()
        load.load_status = load_status
        if base_url:
            load.base_url = base_url
        load.load_error = error
        if load_status == "LOADED":
            load.loaded_at = datetime.now(UTC)
            load.last_used_at = datetime.now(UTC)
        return load

    async def _model_with_load(
        self, session: AsyncSession, model: ent.AiModel, load: ent.AiModelLoad | None = None
    ) -> dict:
        if load is None:
            load = (
                await session.execute(
                    select(ent.AiModelLoad).where(ent.AiModelLoad.model_id == model.id)
                )
            ).scalars().first()
        return {
            "id": str(model.id),
            "model_key": model.model_key,
            "family": model.family,
            "base_name": model.base_name,
            "version": model.model_version,
            "quantization": model.quantization,
            "context_window": model.context_window,
            "purpose": model.purpose,
            "approval_status": model.approval_status,
            "approved_at": model.approved_at,
            "created_at": model.created_at,
            "load_status": load.load_status if load else None,
        }

    # --- prompts --------------------------------------------------------------

    async def ensure_default_prompt(self, session: AsyncSession) -> ent.PromptTemplate:
        row = (
            await session.execute(
                select(ent.PromptTemplate).where(ent.PromptTemplate.code == "hospitalgpt_system")
            )
        ).scalar_one_or_none()
        if row is not None:
            return row
        row = ent.PromptTemplate(
            code="hospitalgpt_system",
            name="HospitalGPT system prompt",
            purpose="Local-only clinical assistant behaviour",
            template=DEFAULT_PROMPT_TEMPLATE,
            is_active=True,
            safety_rules={
                "refuse_unauthorized": True,
                "no_diagnosis": True,
                "no_prescribing": True,
                "answer_local_only": True,
            },
        )
        session.add(row)
        await session.flush()
        return row

    async def create_prompt(self, session: AsyncSession, payload: dto.PromptIn) -> ent.PromptTemplate:
        existing = (
            await session.execute(select(ent.PromptTemplate).where(ent.PromptTemplate.code == payload.code))
        ).scalar_one_or_none()
        if existing is not None:
            raise eng.AiError("PROMPT_EXISTS", f"prompt code '{payload.code}' exists", 409)
        row = ent.PromptTemplate(
            code=payload.code,
            name=payload.name,
            purpose=payload.purpose,
            template=payload.template,
            vars_schema=payload.vars_schema,
            safety_rules=payload.safety_rules,
            is_active=payload.is_active,
        )
        session.add(row)
        await session.flush()
        return row

    async def list_prompts(self, session: AsyncSession) -> list[ent.PromptTemplate]:
        return list(
            (await session.execute(select(ent.PromptTemplate).order_by(ent.PromptTemplate.created_at))).scalars().all()
        )

    # --- memory ---------------------------------------------------------------

    async def add_memory(self, session: AsyncSession, payload: dto.MemoryIn) -> ent.AiMemory:
        row = ent.AiMemory(
            user_id=uuid.UUID(payload.user_id),
            memory_type=payload.memory_type,
            content=payload.content,
            importance=payload.importance,
        )
        session.add(row)
        await session.flush()
        return row

    async def list_memories(
        self, session: AsyncSession, user_id: str | None, memory_type: str | None
    ) -> list[ent.AiMemory]:
        stmt = select(ent.AiMemory).where(ent.AiMemory.deleted_at.is_(None))
        if user_id:
            stmt = stmt.where(ent.AiMemory.user_id == uuid.UUID(user_id))
        if memory_type:
            stmt = stmt.where(ent.AiMemory.memory_type == memory_type)
        stmt = stmt.order_by(ent.AiMemory.created_at.desc())
        return list((await session.execute(stmt)).scalars().all())

    async def remove_memory(self, session: AsyncSession, memory_id: uuid.UUID) -> None:
        row = (
            await session.execute(
                select(ent.AiMemory).where(ent.AiMemory.id == memory_id, ent.AiMemory.deleted_at.is_(None))
            )
        ).scalar_one_or_none()
        if row is None:
            raise eng.AiError("NOT_FOUND", "memory not found", 404)
        row.status = "INACTIVE"
        row.deleted_at = func.now()

    # --- feedback -------------------------------------------------------------

    async def add_feedback(
        self, session: AsyncSession, payload: dto.FeedbackIn
    ) -> ent.AiFeedback:
        request_id = uuid.UUID(payload.ai_request_id)
        await self.get_request(session, request_id)
        row = ent.AiFeedback(
            ai_request_id=request_id,
            user_id=uuid.UUID(payload.user_id),
            rating=payload.rating,
            category=payload.category,
            comment=payload.comment,
            accepted=payload.accepted,
        )
        session.add(row)
        return row

    # --- media facades --------------------------------------------------------

    async def stt_transcribe(self, audio_bytes: bytes) -> tuple[str, str]:
        """Speech-to-Text facade (mock or HTTP backend)."""
        await self._ensure_component("stt")
        if self.settings.stt_adapter == "mock":
            text = self._decode_embedded_text(audio_bytes)
            return text or "Mock STT: no speech detected. Configure a local Whisper/Ollama for transcription.", "mock"
        text = await self._media_request("stt", audio_bytes)
        return text or "Transcription empty.", "http"

    async def tts_synthesize(self, text: str) -> tuple[str, str]:
        """Text-to-Speech facade: returns base64 WAV (mock or HTTP backend)."""
        await self._ensure_component("tts")
        if self.settings.tts_adapter == "mock":
            wav = _silence_wav()
            return base64.b64encode(wav).decode("ascii"), "audio/wav"
        b64, media_type = await self._media_media_request("tts", text)
        return b64, media_type

    async def ocr_extract(self, image_bytes: bytes, filename: str | None) -> tuple[str, str]:
        """OCR facade (mock or HTTP backend)."""
        await self._ensure_component("ocr")
        if self.settings.ocr_adapter == "mock":
            text = self._decode_embedded_text(image_bytes)
            return text or "Mock OCR: no text detected. Configure a local OCR backend.", "mock"
        text = await self._media_request("ocr", image_bytes)
        return text or "No text extracted.", "http"

    async def _ensure_component(self, component: str) -> None:
        adapter = getattr(self.settings, f"{component}_adapter", "mock")
        if adapter not in ("mock", "http"):
            raise eng.AiError("RUNTIME_UNKNOWN", f"unknown {component} adapter", 400)

    async def _media_http_client(self, component: str):
        import httpx

        url = getattr(self.settings, f"{component}_http_url")
        token = getattr(self.settings, f"{component}_http_token")
        if not url:
            raise eng.AiError("RUNTIME_UNAVAILABLE", f"{component.upper()} HTTP endpoint not configured", 503)
        headers = {"Authorization": f"Bearer {token}"} if token else {}
        return httpx.AsyncClient(timeout=self.settings.media_timeout), url, headers

    async def _media_request(self, component: str, data: bytes) -> str:
        """POST raw bytes to the configured STT/OCR endpoint; expect JSON text."""
        import httpx

        try:
            client, url, headers = await self._media_http_client(component)
            async with client:
                response = await client.post(url, content=data, headers=headers)
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as err:
            raise eng.AiError("RUNTIME_UNAVAILABLE", f"{component.upper()} backend unavailable: {err}", 503) from err
        except ValueError as err:
            raise eng.AiError(
                "RUNTIME_BAD_RESPONSE", f"{component.upper()} backend returned a non-JSON response", 502
            ) from err
        return str(payload.get("text", "") or "")

    async def _media_media_request(self, component: str, payload_body: str) -> tuple[str, str]:
        """POST text to the configured TTS endpoint; expect media bytes back."""
        import httpx

        try:
            client, url, headers = await self._media_http_client(component)
            async with client:
                response = await client.post(url, content=payload_body.encode("utf-8"), headers=headers)
                response.raise_for_status()
                media_type = response.headers.get("content-type", "audio/wav")
        except httpx.HTTPError as err:
            raise eng.AiError("RUNTIME_UNAVAILABLE", f"{component.upper()} backend unavailable: {err}", 503) from err
        return base64.b64encode(response.content).decode("ascii"), media_type

    @staticmethod
    def _decode_embedded_text(data: bytes) -> str:
        """Best-effort decoding of ASCII text hidden in media (mock engine)."""
        try:
            clean = bytes(b for b in data if b == 10 or b == 13 or 32 <= b < 127)
            text = clean.decode("ascii")
        except Exception:  # noqa: BLE001 - fall back to empty
            return ""
        return re.sub(r"[^\s\w.,?;:!-]+", " ", text).strip()


def _role_for_level(level: int) -> str:
    return {1: "NURSE/CLINICIAN", 2: "CLINICIAN", 3: "MANAGER", 4: "ATTENDING_PHYSICIAN"}.get(level, "CLINICIAN")


def _silence_wav() -> bytes:
    """Tiny valid silent WAV (0.1s of silence at 8kHz)."""
    import io

    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(8000)
        w.writeframes(b"\x00\x00" * 800)
    return buffer.getvalue()