"""OpenAI-compatible LLM client targeting the camel-hub gateway.

Two roles share this client but are configured with different models and,
crucially, different privilege envelopes enforced by the callers:

* P-LLM (planner)  — claude-sonnet-4-5, sees only its own code/plan, never raw data.
* Q-LLM (qparser)  — claude-haiku-4-5, quarantined: sees restricted data slices,
  output is never marked `trusted`.
"""
import asyncio
import json
import re
import time
from dataclasses import dataclass, field
from typing import Any

import httpx

from app.config import settings

# transient upstream states worth retrying (gateway busy / rate limited / 5xx)
_RETRYABLE_STATUS = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 4


@dataclass
class LLMResult:
    content: str
    model: str
    latency_ms: int
    usage: dict[str, Any] = field(default_factory=dict)
    raw: dict[str, Any] = field(default_factory=dict)


class LLMError(RuntimeError):
    pass


class LLMClient:
    def __init__(self, base_url: str | None = None, api_key: str | None = None):
        self.base_url = (base_url or settings.llm_base_url).rstrip("/")
        self.api_key = api_key or settings.llm_api_key
        self._client: httpx.AsyncClient | None = None
        # cap concurrent gateway calls (e.g. 10 sources exploring at once) to
        # smooth load and avoid self-inflicted 503s; created lazily on the loop
        self._sema: asyncio.Semaphore | None = None

    def _semaphore(self) -> asyncio.Semaphore:
        if self._sema is None:
            self._sema = asyncio.Semaphore(6)
        return self._sema

    def _http(self) -> httpx.AsyncClient:
        # one pooled client reused across calls (keep-alive); closed on shutdown
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                limits=httpx.Limits(max_connections=20, max_keepalive_connections=10)
            )
        return self._client

    async def aclose(self) -> None:
        if self._client is not None and not self._client.is_closed:
            await self._client.aclose()
        self._client = None

    async def chat(
        self,
        model: str,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.2,
        max_tokens: int | None = None,
        timeout: float = 120.0,
    ) -> LLMResult:
        if not self.api_key:
            raise LLMError("LLM_API_KEY is not configured")
        # never cap output by default — a max_tokens limit truncates the model
        # (especially reasoning models that spend tokens before answering).
        payload: dict[str, Any] = {
            "model": model, "messages": messages, "temperature": temperature,
        }
        if max_tokens is not None:
            payload["max_tokens"] = max_tokens
        started = time.monotonic()
        # retry transient gateway failures (503 busy / 429 / 5xx / network) with
        # exponential backoff + jitter — the gateway 503s under concurrent load
        # (e.g. 10 sources exploring at once), which must not fail adaptation.
        last_err: Exception | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                async with self._semaphore():
                    resp = await self._http().post(
                        f"{self.base_url}/chat/completions",
                        headers={
                            "Authorization": f"Bearer {self.api_key}",
                            "Content-Type": "application/json",
                        },
                        json=payload,
                        timeout=timeout,
                    )
            except httpx.HTTPError as exc:
                last_err = LLMError(f"LLM {model} network error: {type(exc).__name__}")
            else:
                if resp.status_code == 200:
                    break
                last_err = LLMError(f"LLM {model} HTTP {resp.status_code}: {resp.text[:300]}")
                if resp.status_code not in _RETRYABLE_STATUS:
                    raise last_err
            if attempt < _MAX_ATTEMPTS - 1:
                # 0.6, 1.2, 2.4s + jitter (jitter from monotonic fraction, no RNG dep)
                await asyncio.sleep(0.6 * (2 ** attempt) + (time.monotonic() % 0.3))
        else:
            raise last_err or LLMError(f"LLM {model}: exhausted retries")
        latency = int((time.monotonic() - started) * 1000)
        data = resp.json()
        if "error" in data:
            raise LLMError(f"LLM {model}: {data['error']}")
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError) as exc:
            raise LLMError(f"LLM {model}: malformed response {data}") from exc
        return LLMResult(
            content=content,
            model=model,
            latency_ms=latency,
            usage=data.get("usage", {}),
            raw=data,
        )

    async def structured(
        self,
        model: str,
        system: str,
        user: str,
        *,
        temperature: float = 0.1,
        max_tokens: int | None = None,
    ) -> tuple[dict[str, Any], LLMResult]:
        """Ask for strict JSON and parse it (tolerant of ```json fences)."""
        result = await self.chat(
            model,
            [
                {"role": "system", "content": system + "\n\nReply with ONLY valid JSON, no prose."},
                {"role": "user", "content": user},
            ],
            temperature=temperature,
            max_tokens=max_tokens,
        )
        return _parse_json(result.content), result


def _parse_json(text: str) -> dict[str, Any]:
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    else:
        brace = text.find("{")
        if brace > 0:
            text = text[brace:]
        # trim trailing prose after the last closing brace
        last = text.rfind("}")
        if last != -1:
            text = text[: last + 1]
    # LLMs routinely emit raw newlines/tabs inside JSON string values, which
    # strict json.loads rejects. strict=False tolerates control chars in strings;
    # a second pass escapes any that remain. This keeps auto-adaptation robust —
    # a single stray control char must not fail a whole discovery.
    escaped = _escape_control_chars(text)
    err_pos: int | None = None
    for attempt in (text, escaped, _repair_truncated(escaped)):
        if attempt is None:
            continue
        try:
            return json.loads(attempt, strict=False)
        except json.JSONDecodeError as exc:
            if err_pos is None:
                err_pos = exc.pos
    # last resort: a structural error mid-array (e.g. an unescaped quote or a
    # missing comma the model emitted) — salvage every complete element BEFORE
    # the first error position by truncating there and closing open brackets.
    if err_pos:
        salvaged = _repair_truncated(escaped[:err_pos])
        if salvaged:
            try:
                return json.loads(salvaged, strict=False)
            except json.JSONDecodeError:
                pass
    raise LLMError(f"LLM did not return valid JSON: {text[:300]}")


def _repair_truncated(text: str) -> str | None:
    """Salvage a JSON object truncated mid-string/array (token-limit cutoff):
    cut back to the last complete element, then close open brackets. Lets a
    truncated discovery still yield the endpoints that DID come through."""
    depth = 0
    in_str = esc = False
    last_safe = -1          # index just after a top-of-array element boundary
    stack: list[str] = []
    for i, ch in enumerate(text):
        if esc:
            esc = False; continue
        if ch == "\\":
            esc = True; continue
        if ch == '"':
            in_str = not in_str; continue
        if in_str:
            continue
        if ch in "{[":
            stack.append(ch); depth += 1
        elif ch in "}]":
            if stack:
                stack.pop(); depth -= 1
            if ch == "}" and depth >= 1:  # closed an element inside an array/object
                last_safe = i + 1
    if last_safe == -1:
        return None
    head = text[:last_safe]
    # reconstruct closers for whatever remained open at last_safe
    depth2 = 0; in_str = esc = False; open_stack: list[str] = []
    for ch in head:
        if esc:
            esc = False; continue
        if ch == "\\":
            esc = True; continue
        if ch == '"':
            in_str = not in_str; continue
        if in_str:
            continue
        if ch in "{[":
            open_stack.append(ch)
        elif ch in "}]" and open_stack:
            open_stack.pop()
    closers = "".join("]" if c == "[" else "}" for c in reversed(open_stack))
    return head + closers


def _escape_control_chars(text: str) -> str:
    """Escape raw control characters that appear inside JSON string literals."""
    out, in_str, esc = [], False, False
    for ch in text:
        if esc:
            out.append(ch); esc = False; continue
        if ch == "\\":
            out.append(ch); esc = True; continue
        if ch == '"':
            in_str = not in_str; out.append(ch); continue
        if in_str and ch in "\n\r\t\b\f":
            out.append({"\n": "\\n", "\r": "\\r", "\t": "\\t", "\b": "\\b", "\f": "\\f"}[ch])
            continue
        if in_str and ord(ch) < 0x20:
            out.append(f"\\u{ord(ch):04x}"); continue
        out.append(ch)
    return "".join(out)


# module-level singletons
llm = LLMClient()                                    # planning (P-LLM) + Q-LLM via camel-hub
# dedicated Explorer LLM (auto-adaptation) — separate provider/key/model
explorer_llm = LLMClient(settings.explorer_base_url, settings.explorer_api_key)


def explorer_model(default: str) -> str:
    """The model to use for exploration calls: the configured explorer model,
    else the caller's default (e.g. the tenant P-LLM profile)."""
    return settings.explorer_model or default
