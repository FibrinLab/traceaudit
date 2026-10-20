from __future__ import annotations

from .base import ClientError, GenerateRequest, RawResponse, http_json, split_reasoning, timed


class OllamaClient:
    name = "OllamaClient"

    def __init__(self, endpoint: str = "http://localhost:11434", model: str = "gpt-oss:120b", num_ctx: int = 16384,
                 keep_alive: str | None = None, effort_via_prompt: bool = False):
        self.endpoint = endpoint.rstrip("/")
        self.model = model
        self.num_ctx = num_ctx
        self.keep_alive = keep_alive
        self.effort_via_prompt = effort_via_prompt
        self._info: dict | None = None

    def describe(self) -> dict:
        info: dict = {"tag": self.model, "server": "ollama", "endpoint": self.endpoint, "client": self.name}
        try:
            v, _ = http_json(f"{self.endpoint}/api/version", timeout=10)
            info["server_version"] = v.get("version")
        except ClientError as e:
            info["server_version"] = None
            info["describe_error"] = str(e)
            return info
        try:
            show, _ = http_json(f"{self.endpoint}/api/show", {"model": self.model}, timeout=30)
            info["digest"] = (show.get("details") or {}).get("digest") or show.get("digest")
            info["parameters"] = show.get("parameters")
            from ..textutil import sha256_text
            info["template_sha256"] = sha256_text(show.get("template", "") or "")
            info["details"] = show.get("details")
        except ClientError as e:
            info["describe_error"] = str(e)
        major_minor = tuple(int(x) for x in str(info.get("server_version") or "0.0").split(".")[:2] if x.isdigit())
        info["supports_think_levels"] = major_minor >= (0, 11)
        info["effort_mechanism"] = "prompt" if (self.effort_via_prompt or not info["supports_think_levels"]) else "parameter"
        self._info = info
        return info

    def generate(self, req: GenerateRequest) -> RawResponse:
        if self._info is None:
            self.describe()
        warnings: list[str] = []
        system = req.system
        use_param = (self._info or {}).get("effort_mechanism") == "parameter"
        if not use_param:
            system = system.rstrip() + f"\n\nReasoning: {req.effort}"
            warnings.append("EFFORT_VIA_PROMPT")
        body = {
            "model": self.model, "stream": False,
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": req.user}],
            "options": {"seed": req.seed, "temperature": req.temperature, "top_p": req.top_p, "num_predict": req.max_tokens, "num_ctx": self.num_ctx},
        }
        if use_param:
            body["think"] = req.effort
        if self.keep_alive:
            body["keep_alive"] = self.keep_alive
        est_tokens = (len(system) + len(req.user)) / 3.5
        if est_tokens > 0.7 * self.num_ctx:
            warnings.append("CTX_TIGHT")
        t0 = timed()
        data, raw = http_json(f"{self.endpoint}/api/chat", body, timeout=req.timeout_s)
        latency = int((timed() - t0) * 1000)
        msg = data.get("message") or {}
        reasoning, answer = split_reasoning(msg.get("content", ""), msg.get("thinking"), warnings)
        if not reasoning and not answer:
            raise ClientError("empty", "no content returned", True)
        if not reasoning:
            warnings.append("NO_REASONING")
        usage = {"prompt_tokens": data.get("prompt_eval_count"), "completion_tokens": data.get("eval_count")}
        return RawResponse(reasoning=reasoning, answer=answer, retrieved=[], raw=raw, finish_reason=data.get("done_reason"),
                           usage=usage, latency_ms=latency, parse_warnings=warnings)
