"""Model clients (spec 07)."""
from .base import ClientError, GenerateRequest, ModelClient, RawResponse
from .callable_ import CallableClient
from .harmony import parse_harmony
from .anthropic_ import AnthropicClient
from .ollama import OllamaClient
from .openai_compat import OpenAICompatClient

__all__ = ["ClientError", "GenerateRequest", "ModelClient", "RawResponse", "CallableClient", "parse_harmony",
           "OllamaClient", "OpenAICompatClient", "AnthropicClient", "make_client"]


def make_client(kind: str, model: str, endpoint: str | None = None, **kw) -> ModelClient:
    if kind == "ollama":
        return OllamaClient(endpoint or "http://localhost:11434", model, **kw)
    if kind in ("openai", "openai-compat", "vllm"):
        return OpenAICompatClient(endpoint or "http://localhost:8000", model, **kw)
    if kind == "anthropic":
        return AnthropicClient(endpoint or "https://api.anthropic.com", model, **kw)
    if kind == "sim":
        from ..simulate import SimulatedModel
        return SimulatedModel.client(**kw)
    raise ValueError(f"unknown client kind {kind!r}")
