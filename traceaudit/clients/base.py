from __future__ import annotations

import json
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from typing import Protocol

from .harmony import parse_harmony


class ClientError(Exception):
    def __init__(self, kind: str, message: str, retryable: bool = False):
        super().__init__(f"{kind}: {message}")
        self.kind = kind
        self.message = message
        self.retryable = retryable


@dataclass(frozen=True)
class GenerateRequest:
    system: str
    user: str
    effort: str
    seed: int
    temperature: float = 1.0
    top_p: float = 1.0
    max_tokens: int = 8192
    timeout_s: float = 600.0
    # Out-of-band metadata for in-process clients (the simulator): trace key and variant facts. Never sent to a model.
    meta: dict | None = field(default=None, compare=False, hash=False)


@dataclass
class Retrieved:
    doc_id: str | None = None
    chunk_id: int | str | None = None
    text: str = ""
    score: float | None = None


@dataclass
class RawResponse:
    reasoning: str
    answer: str
    retrieved: list[Retrieved] = field(default_factory=list)
    raw: str = ""
    finish_reason: str | None = None
    usage: dict = field(default_factory=dict)
    latency_ms: int = 0
    parse_warnings: list[str] = field(default_factory=list)


class ModelClient(Protocol):
    name: str

    def describe(self) -> dict: ...

    def generate(self, req: GenerateRequest) -> RawResponse: ...


_SSL_CONTEXT = None


def ssl_context():
    """TLS context for outbound calls. Some Python builds ship without root certificates (python.org macOS
    installers until "Install Certificates" is run); fall back to TRACEAUDIT_CA_BUNDLE or, if importable,
    certifi's bundle. certifi is optional and loaded dynamically so the runtime stays standard-library."""
    global _SSL_CONTEXT
    if _SSL_CONTEXT is not None:
        return _SSL_CONTEXT
    import importlib
    import os
    import ssl
    cafile = os.environ.get("TRACEAUDIT_CA_BUNDLE") or os.environ.get("SSL_CERT_FILE")
    ctx = ssl.create_default_context(cafile=cafile) if cafile else ssl.create_default_context()
    if not cafile and not ctx.get_ca_certs():
        try:
            certifi = importlib.import_module("certifi")
            ctx = ssl.create_default_context(cafile=certifi.where())
        except Exception:  # noqa: BLE001 - keep the default context
            pass
    _SSL_CONTEXT = ctx
    return ctx


def http_json(url: str, body: dict | None = None, headers: dict | None = None, timeout: float = 600.0, method: str | None = None) -> tuple[dict, str]:
    data = json.dumps(body).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, method=method or ("POST" if data else "GET"))
    req.add_header("Content-Type", "application/json")
    for k, v in (headers or {}).items():
        req.add_header(k, v)
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=ssl_context() if url.startswith("https") else None) as resp:
            text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        payload = e.read().decode("utf-8", "replace") if e.fp else ""
        retryable = e.code in (408, 409, 425, 429, 500, 502, 503, 504)
        raise ClientError("http", f"HTTP {e.code}: {payload[:500]}", retryable) from e
    except urllib.error.URLError as e:
        raise ClientError("http", f"unreachable: {e.reason}", True) from e
    except TimeoutError as e:
        raise ClientError("timeout", str(e), True) from e
    except OSError as e:  # includes socket.timeout
        raise ClientError("timeout" if "timed out" in str(e) else "http", str(e), True) from e
    try:
        return json.loads(text), text
    except json.JSONDecodeError as e:
        raise ClientError("parse", f"non-JSON response: {text[:200]}", False) from e


def split_reasoning(content: str, reasoning_field: str | None, warnings: list[str]) -> tuple[str, str]:
    """Use structured reasoning if present; otherwise parse harmony tokens out of content."""
    if reasoning_field:
        answer = content or ""
        if "<|channel|>" in answer:
            r2, a2, w2 = parse_harmony(answer)
            warnings.append("HARMONY_IN_CONTENT")
            warnings.extend(w2)
            return (reasoning_field + ("\n\n" + r2 if r2 else "")), a2
        return reasoning_field, answer
    if content and "<|channel|>" in content:
        r, a, w = parse_harmony(content)
        warnings.extend(w)
        return r, a
    return "", content or ""


def timed() -> float:
    return time.perf_counter()
