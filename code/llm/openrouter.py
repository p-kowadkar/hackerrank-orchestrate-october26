"""The `live` backend: OpenRouter's chat-completions API.

Nothing here runs unless a run explicitly enables live access (`allow_network=True`, which only the command line sets for
`--llm live` and `--llm record`), a real key is in the environment variable OPENROUTER_API_KEY (a placeholder is used when it
is unset, and the placeholder is refused), and a model is named. Every response that arrives, valid or not, is written to the
usage ledger straight away, with the tokens and cost the provider reported. Cost is never computed from a price list.
"""
from __future__ import annotations

import base64
import json
import os
import re
import time
import urllib.error
import urllib.request
from pathlib import Path
from typing import Callable, Optional

from .interface import LLMError, LLMRequest, LLMResult, LLMUnavailable, LLMValidationError, Usage
from .schemas import validate
from .usage import Ledger

API_URL = "https://openrouter.ai/api/v1/chat/completions"
PLACEHOLDER_KEY = "placeholder"
KEY_ENV = "OPENROUTER_API_KEY"
MODEL_ENV = "GHOSTAUDIT_MODEL"
OFFLINE_ENV = "GHOSTAUDIT_OFFLINE"          # set to 1 by the test suite: the default transport then refuses to open a socket


class LiveNotConfigured(LLMUnavailable):
    pass


class NetworkDisabled(LLMUnavailable):
    pass


def api_key() -> str:
    return os.environ.get(KEY_ENV, PLACEHOLDER_KEY)


def key_is_configured(key: str) -> bool:
    k = (key or "").strip().lower()
    return bool(k) and k != PLACEHOLDER_KEY and not k.startswith("your")


def urllib_transport(url: str, headers: dict, body: bytes, timeout: float = 120.0) -> tuple:
    if os.environ.get(OFFLINE_ENV) == "1":
        raise NetworkDisabled(f"{OFFLINE_ENV}=1: network access is disabled")
    req = urllib.request.Request(url, data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:          # noqa: S310 - fixed https URL
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read().decode("utf-8", errors="replace")


def _json_from_text(text: str):
    t = text.strip()
    fence = re.match(r"^```(?:json)?\s*(.*?)\s*```$", t, re.S)
    return json.loads(fence.group(1) if fence else t)


class OpenRouterBackend:
    name = "live"

    def __init__(self, model: Optional[str], ledger: Ledger, run_id: str, transport: Callable = urllib_transport,
                 allow_network: bool = False, sleep: Callable = time.sleep, max_retries: int = 2, max_repairs: int = 1,
                 base_url: str = API_URL):
        self.model = model or os.environ.get(MODEL_ENV, "")
        self.ledger, self.run_id, self.transport = ledger, run_id, transport
        self.allow_network, self.sleep = allow_network, sleep
        self.max_retries, self.max_repairs, self.base_url = max_retries, max_repairs, base_url

    # --------------------------------------------------------------------------------------------- guards
    def _check(self) -> str:
        if not self.allow_network:
            raise LLMUnavailable("live access was not enabled for this run")
        key = api_key()
        if not key_is_configured(key):
            raise LiveNotConfigured(f"{KEY_ENV} is not set to a real key (live mode needs one outside the sandbox)")
        if not self.model:
            raise LiveNotConfigured(f"no model named: pass --model or set {MODEL_ENV}")
        return key

    # -------------------------------------------------------------------------------------------- request
    def _messages(self, req: LLMRequest, extra_user: Optional[str] = None) -> list:
        text = req.user if not extra_user else req.user + "\n\n" + extra_user
        if req.image_path is not None:
            b64 = base64.b64encode(Path(req.image_path).read_bytes()).decode("ascii")
            user = [{"type": "text", "text": text}, {"type": "image_url", "image_url": {"url": f"data:image/png;base64,{b64}"}}]
        else:
            user = text
        return [{"role": "system", "content": req.system}, {"role": "user", "content": user}]

    def _call(self, key: str, req: LLMRequest, extra_user: Optional[str]) -> dict:
        body = json.dumps({"model": self.model, "messages": self._messages(req, extra_user), "temperature": 0,
                           "response_format": {"type": "json_object"}, "usage": {"include": True}}).encode("utf-8")
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json", "X-Title": "ghost-data-audit"}
        for attempt in range(self.max_retries + 1):
            status, text = self.transport(self.base_url, headers, body)
            if status in (429, 500, 502, 503, 504) and attempt < self.max_retries:
                self.sleep(2 ** (attempt + 1))
                continue
            if status != 200:
                raise LLMError(f"OpenRouter returned HTTP {status}: {text[:300]}")      # the key is never part of this text
            return json.loads(text)
        raise LLMError("unreachable")                                                    # pragma: no cover

    # ------------------------------------------------------------------------------------------------ run
    def run(self, req: LLMRequest) -> LLMResult:
        key = self._check()
        extra, last_problems = None, []
        for _attempt in range(self.max_repairs + 1):
            payload = self._call(key, req, extra)
            u = payload.get("usage")
            if not isinstance(u, dict) or "prompt_tokens" not in u or "completion_tokens" not in u:
                raise LLMError("the response carries no usage block; it cannot be ledgered, so the run stops")
            usage = Usage(int(u["prompt_tokens"]), int(u["completion_tokens"]),
                          int(u.get("total_tokens", u["prompt_tokens"] + u["completion_tokens"])),
                          float(u["cost"]) if isinstance(u.get("cost"), (int, float)) else None, "api")
            content = payload["choices"][0]["message"]["content"]
            raw = content if isinstance(content, str) else "".join(p.get("text", "") for p in content)
            base = dict(step=req.step, key=req.key, origin="live", model=payload.get("model", self.model),
                        provider="openrouter", request_id=str(payload.get("id", "")), usage=usage, raw_text=raw)
            try:
                data = validate(req.step, _json_from_text(raw))
            except (ValueError, LLMValidationError) as exc:
                last_problems = exc.problems if isinstance(exc, LLMValidationError) else [f"not valid JSON: {exc}"]
                self.ledger.record(LLMResult(data={}, **base), self.run_id, "invalid")
                extra = "Your previous answer was rejected: " + "; ".join(last_problems) + ". Return only the corrected JSON object."
                continue
            result = LLMResult(data=data, **base)
            self.ledger.record(result, self.run_id, "ok")
            return result
        raise LLMValidationError(last_problems)
