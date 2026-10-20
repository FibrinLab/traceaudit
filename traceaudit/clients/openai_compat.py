from __future__ import annotations

import os

from .base import ClientError, GenerateRequest, RawResponse, Retrieved, http_json, split_reasoning, timed


class OpenAICompatClient:
    name = "OpenAICompatClient"

    def __init__(self, endpoint: str, model: str, api_key_env: str = "TRACEAUDIT_API_KEY", headers: dict | None = None,
                 extra_body: dict | None = None, effort_via_prompt: bool = False, api_key: str | None = None):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.headers = dict(headers or {})
        key = api_key or os.environ.get(api_key_env)
        if key:
            self.headers.setdefault("Authorization", f"Bearer {key}")
        self.extra_body = dict(extra_body or {})
        self.effort_via_prompt = effort_via_prompt
        self._reject_effort = effort_via_prompt

    def describe(self) -> dict:
        info = {"tag": self.model, "server": "openai-compatible", "endpoint": self.endpoint, "client": self.name,
                "effort_mechanism": "prompt" if self._reject_effort else "parameter"}
        try:
            data, _ = http_json(f"{self.endpoint}/v1/models", headers=self.headers, timeout=15)
            for m in data.get("data", []):
                if m.get("id") == self.model:
                    info["model_entry"] = m
            info["server_version"] = data.get("server_version")
        except ClientError as e:
            info["describe_error"] = str(e)
        return info

    def _body(self, req: GenerateRequest, system: str, with_effort: bool) -> dict:
        body = {"model": self.model, "messages": [{"role": "system", "content": system}, {"role": "user", "content": req.user}],
                "seed": req.seed, "temperature": req.temperature, "top_p": req.top_p, "max_tokens": req.max_tokens}
        if with_effort:
            body["reasoning_effort"] = req.effort
        body.update(self.extra_body)
        return body

    def generate(self, req: GenerateRequest) -> RawResponse:
        warnings: list[str] = []
        system = req.system
        with_effort = not self._reject_effort
        if not with_effort:
            system = system.rstrip() + f"\n\nReasoning: {req.effort}"
            warnings.append("EFFORT_VIA_PROMPT")
        t0 = timed()
        try:
            data, raw = http_json(f"{self.endpoint}/v1/chat/completions", self._body(req, system, with_effort), self.headers, req.timeout_s)
        except ClientError as e:
            if with_effort and e.kind == "http" and "reasoning_effort" in e.message:
                self._reject_effort = True
                system = req.system.rstrip() + f"\n\nReasoning: {req.effort}"
                warnings.append("EFFORT_VIA_PROMPT")
                data, raw = http_json(f"{self.endpoint}/v1/chat/completions", self._body(req, system, False), self.headers, req.timeout_s)
            else:
                raise
        latency = int((timed() - t0) * 1000)
        choices = data.get("choices") or []
        if not choices:
            raise ClientError("empty", "no choices", True)
        msg = choices[0].get("message") or {}
        reasoning_field = msg.get("reasoning_content") or msg.get("reasoning")
        if isinstance(reasoning_field, list):
            reasoning_field = "\n\n".join(str(x.get("text", x)) if isinstance(x, dict) else str(x) for x in reasoning_field)
        if msg.get("reasoning_summary") and not reasoning_field:
            raise ClientError("parse", "reasoning summary only; raw trace required", False)
        reasoning, answer = split_reasoning(msg.get("content") or "", reasoning_field, warnings)
        if not reasoning:
            warnings.append("NO_REASONING")
        retrieved: list[Retrieved] = []
        for key in ("retrieved", "context", "citations", "documents"):
            arr = data.get(key) or msg.get(key)
            if isinstance(arr, list) and arr:
                for i, item in enumerate(arr):
                    if isinstance(item, dict):
                        retrieved.append(Retrieved(item.get("doc_id") or item.get("id") or item.get("source"), item.get("chunk_id", i),
                                                   item.get("text") or item.get("content") or "", item.get("score")))
                    else:
                        retrieved.append(Retrieved(None, i, str(item), None))
                warnings.append(f"RETRIEVAL_MAPPED:{key}")
                break
        usage = data.get("usage") or {}
        if isinstance(usage.get("completion_tokens_details"), dict):
            usage["reasoning_tokens"] = usage["completion_tokens_details"].get("reasoning_tokens")
        return RawResponse(reasoning=reasoning, answer=answer, retrieved=retrieved, raw=raw, finish_reason=choices[0].get("finish_reason"),
                           usage=usage, latency_ms=latency, parse_warnings=warnings)
