"""HospitalGPT engines.

- InferenceEngine: adapters (mock / ollama / llamacpp / openai-compatible).
- PromptManager: render versioned prompt templates (from prompt_templates).
- MemoryManager: conversation window assembly + long-term memory.
- ModelManager: registry + live load state for the Model Manager.

The mock inference is deterministic and grounded: it only answers from supplied
context passages (RAG) and follows the AI Behaviour response format.
"""

from __future__ import annotations

import hashlib
import math
import re
import urllib.parse

import httpx

from ai_service.configuration import AiSettings


class AiError(Exception):
    """Domain error surfaced as an EHOS error response."""

    def __init__(self, error_code: str, message: str, status_code: int = 400):
        super().__init__(message)
        self.error_code = error_code
        self.message = message
        self.status_code = status_code


class InferenceResult:
    """Structured result from an inference adapter."""

    def __init__(self, text: str, tokens_in: int, tokens_out: int, latency_ms: int):
        self.text = text
        self.tokens_in = tokens_in
        self.tokens_out = tokens_out
        self.latency_ms = latency_ms


# --- inference adapters ---------------------------------------------------------


class InferenceEngine:
    """Factory selecting the inference adapter from settings."""

    def __init__(self, settings: AiSettings):
        self.settings = settings
        if settings.inference_adapter == "ollama":
            self._impl: _BaseInference = _OllamaInference(settings)
        elif settings.inference_adapter == "llamacpp":
            self._impl = _LlamacppInference(settings)
        elif settings.inference_adapter == "openai":
            self._impl = _OpenAIInference(settings)
        else:
            self._impl = _MockInference(settings)

    @property
    def adapter(self) -> str:
        return self.settings.inference_adapter

    async def complete(self, model_key: str, prompt: str, max_tokens: int = 1024) -> InferenceResult:
        return await self._impl.complete(model_key, prompt, max_tokens)


class _BaseInference:
    def _tokens(self, text: str) -> int:
        return max(1, len(re.findall(r"\S+", text)))


class _MockInference(_BaseInference):
    """Deterministic local inference that only answers from provided context."""

    def __init__(self, settings: AiSettings):
        self.settings = settings

    async def complete(self, model_key: str, prompt: str, max_tokens: int = 1024) -> InferenceResult:
        context = _extract_context(prompt)
        if not context:
            text = (
                "Summary: I do not have enough verified information to answer this safely.\n\n"
                "Key Information: No approved local knowledge matched your request.\n\n"
                "Risks: Providing an unverified answer could cause clinical error.\n\n"
                "Recommended Next Steps: Refine your question or consult the approved guidelines.\n\n"
                "Human Approval Required: N/A - informational only."
            )
            return InferenceResult(text, self._tokens(prompt), self._tokens(text), 1)
        passage = context[0]
        text = (
            f"Summary: Based on the retrieved local guideline/policy, the answer addresses "
            f"{_truncate(passage, 120)}.\n\n"
            "Key Information: " + _truncate(passage, 600) + "\n\n"
            "Risks: This summary is informational; clinical decisions require clinician judgment.\n\n"
            "Recommended Next Steps: Review the full referenced document before acting.\n\n"
            "Human Approval Required: N/A - informational only.\n"
        )
        return InferenceResult(text, self._tokens(prompt), self._tokens(text), 1)


class _OllamaInference(_BaseInference):
    """Offline inference via local Ollama endpoint."""

    def __init__(self, settings: AiSettings):
        self.settings = settings
        self.base_url = settings.ollama_base_url

    async def complete(self, model_key: str, prompt: str, max_tokens: int = 1024) -> InferenceResult:
        url = urllib.parse.urljoin(self.base_url.rstrip("/") + "/", "api/generate")
        model = model_key or self.settings.ollama_model
        start = __import__("time").perf_counter()
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    url,
                    json={
                        "model": model,
                        "prompt": prompt,
                        "stream": False,
                        "options": {"num_predict": max_tokens},
                        # Unload the model from RAM shortly after each answer:
                        # the dev machine is memory-constrained.
                        "keep_alive": "1m",
                    },
                )
                if response.status_code == httpx.codes.NOT_FOUND and model_key:
                    # App model keys (e.g. "llama-3.1-8b") are registry aliases, not
                    # Ollama tags; fall back to the configured local model.
                    model = self.settings.ollama_model
                    response = await client.post(
                        url,
                        json={
                            "model": model,
                            "prompt": prompt,
                            "stream": False,
                            "options": {"num_predict": max_tokens},
                            "keep_alive": "1m",
                        },
                    )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as err:
            raise AiError("RUNTIME_UNAVAILABLE", f"local Ollama runtime unavailable: {err}", 503) from err
        text = payload.get("response", "")
        elapsed = int((__import__("time").perf_counter() - start) * 1000)
        return InferenceResult(text, self._tokens(prompt), self._tokens(text), elapsed)


class _LlamacppInference(_BaseInference):
    """Offline inference via a llama.cpp server."""

    def __init__(self, settings: AiSettings):
        self.settings = settings
        self.base_url = settings.llamacpp_base_url

    async def complete(self, model_key: str, prompt: str, max_tokens: int = 1024) -> InferenceResult:
        url = urllib.parse.urljoin(self.base_url.rstrip("/") + "/", "completion")
        start = __import__("time").perf_counter()
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    url, json={"prompt": prompt, "n_predict": max_tokens, "stream": False}
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as err:
            raise AiError("RUNTIME_UNAVAILABLE", f"local llama.cpp runtime unavailable: {err}", 503) from err
        text = payload.get("content", "")
        elapsed = int((__import__("time").perf_counter() - start) * 1000)
        return InferenceResult(text, self._tokens(prompt), self._tokens(text), elapsed)


class _OpenAIInference(_BaseInference):
    """Inference via any OpenAI-compatible endpoint (vLLM, LM Studio, OpenAI).

    ``Authorization: Bearer <key>`` is only sent when a key is configured so
    keyless self-hosted servers work out of the box.
    """

    def __init__(self, settings: AiSettings):
        self.settings = settings
        self.base_url = settings.openai_base_url

    async def complete(self, model_key: str, prompt: str, max_tokens: int = 1024) -> InferenceResult:
        url = urllib.parse.urljoin(self.base_url.rstrip("/") + "/", "chat/completions")
        model = model_key or self.settings.openai_model
        headers = {}
        if self.settings.openai_api_key:
            headers["Authorization"] = f"Bearer {self.settings.openai_api_key}"
        start = __import__("time").perf_counter()
        try:
            async with httpx.AsyncClient(timeout=120.0) as client:
                response = await client.post(
                    url,
                    json={
                        "model": model,
                        "messages": [{"role": "user", "content": prompt}],
                        "max_tokens": max_tokens,
                        "stream": False,
                    },
                    headers=headers,
                )
                response.raise_for_status()
                payload = response.json()
        except httpx.HTTPError as err:
            raise AiError("RUNTIME_UNAVAILABLE", f"OpenAI-compatible runtime unavailable: {err}", 503) from err
        except ValueError as err:
            # Non-JSON body (proxy error page, html) — surface, don't 500.
            raise AiError(
                "RUNTIME_BAD_RESPONSE", "OpenAI-compatible runtime returned a non-JSON response", 502
            ) from err
        choices = payload.get("choices") or []
        first = choices[0].get("message", {}) if choices else {}
        text = first.get("content") or ""
        elapsed = int((__import__("time").perf_counter() - start) * 1000)
        return InferenceResult(text, self._tokens(prompt), self._tokens(text), elapsed)


def _extract_context(prompt: str) -> list[str]:
    """Pull RAG context blocks from the prompt between markers."""
    blocks = re.findall(r"\[CONTEXT\]\s*(.*?)\s*(?:\[/CONTEXT\]|$)", prompt, re.DOTALL)
    return [b.strip() for b in blocks if b.strip()]


def _truncate(text: str, limit: int) -> str:
    return text if len(text) <= limit else text[:limit].rsplit(" ", 1)[0] + " ..."


# --- embedding (bridge; reuses a tiny local hashing embedder for tests) ---------


class EmbeddingEngine:
    """Lightweight deterministic embedder for the ai-service.

    Real deployments embed via the knowledge-service (-/embed) or an Ollama
    embeddings adapter; the fixture mock keeps unit tests hermetic.
    """

    def __init__(self, settings: AiSettings, dimensions: int = 256):
        self.settings = settings
        self.dimensions = dimensions
        self.model = settings.ollama_embedding_model if settings.embedding_adapter == "ollama" else "mock-embed-v1"

    async def embed(self, text: str) -> list[float]:
        tokens = re.findall(r"[a-z0-9]+", text.lower())
        vector = [0.0] * self.dimensions
        for token in tokens:
            digest = hashlib.sha256(token.encode("utf-8")).digest()
            index = int.from_bytes(digest[:2], "big") % self.dimensions
            vector[index] += 1.0
        norm = math.sqrt(sum(v * v for v in vector)) or 1.0
        return [v / norm for v in vector]


# --- prompt manager -------------------------------------------------------------


class PromptManager:
    """Renders versioned prompt templates (collected at call site from DB)."""

    def __init__(self, settings: AiSettings):
        self.settings = settings

    def render(
        self,
        template: str,
        *,
        conversation: str,
        context: str,
        query: str,
        model_key: str,
    ) -> str:
        """Fill the standard HospitalGPT template markers."""
        sources_block = f"[CONTEXT]\n{context}\n[/CONTEXT]\n\n" if context.strip() else ""
        return template.replace("{{conversation}}", conversation).replace(
            "{{context}}", sources_block
        ).replace("{{query}}", query).replace("{{model_key}}", model_key)

    def default_template(self) -> str:
        return (
            "You are the EHOS Local AI Intelligence Layer (HospitalGPT).\n"
            "You assist healthcare professionals with approved, local knowledge only.\n"
            "You never diagnose, never prescribe, and never access unauthorized data.\n"
            "If you cannot answer from the provided context, say: 'I do not have enough verified "
            "information to answer this safely.'\n"
            "Answer in the form: Summary / Key Information / Risks / Recommended Next Steps / "
            "Human Approval Required.\n"
            "\nConversation history:\n{{conversation}}\n\n"
            "Retrieved local knowledge:\n{{context}}\n"
            "User question: {{query}}\n\nAnswer:"
        )


# --- memory manager -------------------------------------------------------------


class MemoryManager:
    """Assembles short-term conversation context; prunes overflow."""

    def __init__(self, settings: AiSettings):
        self.settings = settings

    def build_conversation(self, messages: list[tuple[str, str]]) -> str:
        """messages: list of (role, content)."""
        lines = []
        for role, content in messages[-self.settings.max_context_windows :]:
            marker = "User" if role == "USER" else ("Assistant" if role == "ASSISTANT" else role.title())
            lines.append(f"{marker}: {content}")
        return "\n".join(lines) if lines else "No prior messages."


# --- model manager --------------------------------------------------------------


class ModelManager:
    """Acts on the model registry and live load rows (needs session for DB access)."""

    DEFAULT_MODELS: list[dict] = [
        {"model_key": "llama-3.1-8b", "family": "LLM", "base_name": "Llama", "version": "3.1-8b",
         "quantization": "Q4_K_M", "context_window": 128_000, "purpose": "general clinical assistance"},
        {"model_key": "qwen-2.5-7b", "family": "LLM", "base_name": "Qwen", "version": "2.5-7b",
         "quantization": "Q5_K_M", "context_window": 32_000, "purpose": "multilingual clinical assistance"},
        {"model_key": "mistral-7b", "family": "LLM", "base_name": "Mistral", "version": "7B v0.3",
         "quantization": "Q4_K_M", "context_window": 32_000, "purpose": "fast clinical Q&A"},
        {"model_key": "gemma-2-9b", "family": "LLM", "base_name": "Gemma", "version": "2-9b",
         "quantization": "Q4_K_M", "context_window": 8192, "purpose": "grounded clinical reasoning"},
    ]

    def __init__(self, settings: AiSettings):
        self.settings = settings