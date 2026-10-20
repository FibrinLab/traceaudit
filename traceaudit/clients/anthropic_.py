"""Direct Anthropic Messages API client (pilot-only pipeline exercise; see docs/deviations.md).

Standard library only (urllib): the package must stay stdlib at runtime, which is why this
speaks raw HTTP rather than using the anthropic SDK.

The model returns *summarised* thinking, never the raw chain of thought, so every trace
carries the parse warning SUMMARISED_THINKING and describe() records reasoning_kind.
"""
from __future__ import annotations

import json
import os
import time
import urllib.error
import urllib.request
from typing import Callable

from ..textutil import sha256_text
from .base import ClientError, GenerateRequest, RawResponse, ssl_context, timed

API_VERSION = "2023-06-01"
OAUTH_BETA = "oauth-2025-04-20"
RETRYABLE_STATUS = {408, 409, 425, 429, 500, 502, 503, 504, 529}
EFFORTS = ("low", "medium", "high", "xhigh", "max")


class AnthropicClient:
    name = "AnthropicClient"

    def __init__(self, endpoint: str = "https://api.anthropic.com", model: str = "claude-opus-5-5",
                 api_key_env: str = "ANTHROPIC_API_KEY", auth_token_env: str = "ANTHROPIC_AUTH_TOKEN",
                 thinking_display: str = "summarized", retry_after_max_s: float = 120.0, inner_retries: int = 2,
                 sleep: Callable[[float], None] = time.sleep, api_key: str | None = None):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.thinking_display = thinking_display
        self.retry_after_max_s = retry_after_max_s
        self.inner_retries = inner_retries
        self._sleep = sleep
        self._info: dict | None = None
        token = None if api_key else os.environ.get(auth_token_env)
        key = api_key or os.environ.get(api_key_env)
        self.headers = {"anthropic-version": API_VERSION, "content-type": "application/json"}
        if token:
            self.headers["Authorization"] = f"Bearer {token}"
            self.headers["anthropic-beta"] = OAUTH_BETA
            self.auth_kind = "oauth"
        elif key:
            self.headers["x-api-key"] = key
            self.auth_kind = "api_key"
        else:
            self.auth_kind = "none"

    # -- HTTP -----------------------------------------------------------------------------
    def _request(self, path: str, body: dict | None, timeout: float) -> tuple[dict, str, dict]:
        """Return (json, raw_text, headers). Raises ClientError; retryable carries retry_after seconds."""
        data = json.dumps(body).encode("utf-8") if body is not None else None
        req = urllib.request.Request(self.endpoint + path, data=data, method="POST" if data else "GET")
        for k, v in self.headers.items():
            req.add_header(k, v)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=ssl_context()) as resp:
                text = resp.read().decode("utf-8")
                headers = {k.lower(): v for k, v in resp.headers.items()}
        except urllib.error.HTTPError as e:
            payload = e.read().decode("utf-8", "replace") if e.fp else ""
            err = ClientError("http", f"HTTP {e.code}: {payload[:500]}", e.code in RETRYABLE_STATUS)
            err.status = e.code
            ra = e.headers.get("retry-after") if e.headers else None
            err.retry_after = _parse_retry_after(ra)
            err.request_id = e.headers.get("request-id") if e.headers else None
            raise err from e
        except urllib.error.URLError as e:
            raise ClientError("http", f"unreachable: {e.reason}", True) from e
        except TimeoutError as e:
            raise ClientError("timeout", str(e), True) from e
        except OSError as e:
            raise ClientError("timeout" if "timed out" in str(e) else "http", str(e), True) from e
        try:
            return json.loads(text), text, headers
        except json.JSONDecodeError as e:
            raise ClientError("parse", f"non-JSON response: {text[:200]}", False) from e

    def _request_with_retry_after(self, path: str, body: dict, timeout: float) -> tuple[dict, str, dict]:
        """Honour retry-after on retryable statuses a couple of times before handing back to experiment's backoff."""
        for attempt in range(self.inner_retries + 1):
            try:
                return self._request(path, body, timeout)
            except ClientError as e:
                ra = getattr(e, "retry_after", None)
                if e.retryable and ra is not None and attempt < self.inner_retries:
                    self._sleep(min(ra, self.retry_after_max_s))
                    continue
                raise
        raise AssertionError("unreachable")  # pragma: no cover

    # -- protocol -------------------------------------------------------------------------
    def describe(self) -> dict:
        info: dict = {"tag": self.model, "server": "anthropic", "endpoint": self.endpoint, "client": self.name,
                      "api_version": API_VERSION, "auth": self.auth_kind, "effort_mechanism": "parameter",
                      "reasoning_kind": "summarized" if self.thinking_display == "summarized" else self.thinking_display,
                      "thinking": {"type": "adaptive", "display": self.thinking_display},
                      "sampling": "model-default (temperature/top_p/seed not sent; seeds recorded per trace but not applied)",
                      "server_version": API_VERSION}
        try:
            entry, _, _ = self._request(f"/v1/models/{self.model}", None, 30)
            info["model_entry"] = {k: entry.get(k) for k in ("id", "display_name", "created_at", "type") if k in entry}
            info["digest"] = "models-api:" + sha256_text(json.dumps(info["model_entry"], sort_keys=True))[:32]
        except ClientError as e:
            info["describe_error"] = str(e)
            info["digest"] = None
        self._info = info
        return info

    def _body(self, req: GenerateRequest) -> dict:
        effort = req.effort if req.effort in EFFORTS else "medium"
        return {"model": self.model, "max_tokens": req.max_tokens, "system": req.system,
                "messages": [{"role": "user", "content": req.user}],
                "thinking": {"type": "adaptive", "display": self.thinking_display},
                "output_config": {"effort": effort}}

    def generate(self, req: GenerateRequest) -> RawResponse:
        warnings: list[str] = []
        if req.effort not in EFFORTS:
            warnings.append(f"EFFORT_UNKNOWN:{req.effort}")
        t0 = timed()
        data, raw, _headers = self._request_with_retry_after("/v1/messages", self._body(req), req.timeout_s)
        latency = int((timed() - t0) * 1000)
        return parse_message(data, raw, latency, warnings, self.thinking_display)


def parse_message(data: dict, raw: str, latency_ms: int, warnings: list[str] | None = None, display: str = "summarized") -> RawResponse:
    warnings = list(warnings or [])
    if data.get("type") == "error":
        err = data.get("error") or {}
        raise ClientError("http", f"{err.get('type')}: {err.get('message')}", err.get("type") in ("overloaded_error", "api_error"))
    stop = data.get("stop_reason")
    if stop == "refusal":
        details = data.get("stop_details") or {}
        raise ClientError("refusal", f"{details.get('category') or 'unspecified'}", False)
    thinking: list[str] = []
    texts: list[str] = []
    for block in data.get("content") or []:
        t = block.get("type")
        if t == "thinking":
            if block.get("thinking"):
                thinking.append(block["thinking"])
        elif t == "redacted_thinking":
            warnings.append("REDACTED_THINKING")
        elif t == "text":
            texts.append(block.get("text", ""))
        else:
            warnings.append(f"UNEXPECTED_BLOCK:{t}")
    reasoning = "\n\n".join(thinking)
    answer = "".join(texts)
    if display == "summarized":
        warnings.append("SUMMARISED_THINKING")
    if not reasoning and not answer:
        raise ClientError("empty", f"no content returned (stop_reason={stop})", True)
    if not reasoning:
        warnings.append("NO_REASONING")
    if not answer:
        warnings.append("NO_FINAL")
    u = data.get("usage") or {}
    usage = {"input_tokens": u.get("input_tokens"), "output_tokens": u.get("output_tokens"),
             "prompt_tokens": u.get("input_tokens"), "completion_tokens": u.get("output_tokens")}
    for k in ("cache_creation_input_tokens", "cache_read_input_tokens"):
        if u.get(k) is not None:
            usage[k] = u[k]
    return RawResponse(reasoning=reasoning, answer=answer, retrieved=[], raw=raw, finish_reason=stop, usage=usage,
                       latency_ms=latency_ms, parse_warnings=warnings)


def _parse_retry_after(value: str | None) -> float | None:
    if not value:
        return None
    try:
        return max(0.0, float(value))
    except ValueError:
        pass
    try:
        from email.utils import parsedate_to_datetime
        import datetime as _dt
        return max(0.0, (parsedate_to_datetime(value) - _dt.datetime.now(_dt.timezone.utc)).total_seconds())
    except (TypeError, ValueError):
        return None
