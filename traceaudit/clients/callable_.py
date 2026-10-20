from __future__ import annotations

from typing import Callable

from .base import ClientError, GenerateRequest, RawResponse, Retrieved, timed


class CallableClient:
    """Wraps fn(system, user, effort, seed, **kw) -> dict | RawResponse. Used by SimulatedModel and in-process pipelines."""

    name = "CallableClient"

    def __init__(self, fn: Callable, name: str = "callable", describe: dict | None = None, **kw):
        self.fn = fn
        self.label = name
        self._describe = describe or {}
        self.kw = kw

    def describe(self) -> dict:
        d = {"tag": self.label, "server": "in-process", "endpoint": None, "client": self.name, "effort_mechanism": "parameter"}
        d.update(self._describe)
        return d

    def generate(self, req: GenerateRequest) -> RawResponse:
        t0 = timed()
        try:
            out = self.fn(req.system, req.user, req.effort, req.seed, **self.kw)
        except ClientError:
            raise
        except Exception as e:  # noqa: BLE001
            raise ClientError("http", f"callable raised {type(e).__name__}: {e}", False) from e
        latency = int((timed() - t0) * 1000)
        if isinstance(out, RawResponse):
            out.latency_ms = out.latency_ms or latency
            return out
        if not isinstance(out, dict) or "reasoning" not in out or "answer" not in out:
            raise ClientError("parse", "callable must return dict with reasoning and answer", False)
        retrieved = [Retrieved(**r) if isinstance(r, dict) else Retrieved(text=str(r)) for r in out.get("retrieved", [])]
        return RawResponse(reasoning=out["reasoning"], answer=out["answer"], retrieved=retrieved, raw=out.get("raw", ""),
                           finish_reason=out.get("finish_reason", "stop"), usage=out.get("usage", {}), latency_ms=latency,
                           parse_warnings=list(out.get("parse_warnings", [])))
