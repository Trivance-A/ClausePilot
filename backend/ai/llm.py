"""Single OpenAI-compatible LLM client (vLLM / Ollama / commercial API), switched by LLM_BASE_URL only.

- JSON Schema is enforced through `response_format=json_schema` (vLLM guided decoding, Ollama, OpenAI all accept it).
- temperature 0, 120s timeout, 3 retries with exponential backoff (05_OCR_Pipeline §4).
- Response cache key: sha256(model + prompt_version + prompt) (03_데이터정의 §5.19 llm_cache).
"""

import hashlib
import json
import logging
import os
import time
import urllib.error
import urllib.request
from collections.abc import MutableMapping
from typing import Any

logger = logging.getLogger(__name__)

DEFAULT_MODEL = "qwen2.5:7b"


def env_model() -> str:
    return os.getenv("LLM_MODEL", DEFAULT_MODEL)


class LLMUnavailableError(RuntimeError):
    """LLM endpoint unreachable or kept returning invalid JSON (API: 503 LLM_UNAVAILABLE)."""


def prompt_hash(model: str, prompt_version: str, prompt: str) -> str:
    return hashlib.sha256((model + prompt_version + prompt).encode("utf-8")).hexdigest()


def parse_json(text: str) -> dict:
    """Commercial APIs that ignore response_format may wrap the JSON in a ```json fence."""
    text = text.strip()
    if text.startswith("```"):
        text = text.split("\n", 1)[1].rsplit("```", 1)[0] if "\n" in text else text.strip("`")
    return json.loads(text)


class LLMClient:
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str = "",
        *,
        timeout: float = 120.0,
        retries: int = 3,
        backoff: float = 1.0,
        cache: MutableMapping[str, Any] | None = None,
        guided_json: bool = False,
        max_tokens: int = 2048,
    ):
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.api_key = api_key
        self.timeout = timeout
        self.retries = retries
        self.backoff = backoff
        self.cache = cache  # backend may pass a DB-backed mapping over the llm_cache table
        self.max_tokens = max_tokens
        self.guided_json = guided_json  # vLLM: schema via `guided_json` (05_개발환경 §2), others: response_format

    @classmethod
    def from_env(cls, cache: MutableMapping[str, Any] | None = None) -> "LLMClient | None":
        """None when LLM_BASE_URL is unset (offline mode: the backend keeps its rule-based fallback)."""
        base_url = os.getenv("LLM_BASE_URL")
        if not base_url:
            return None
        return cls(base_url, env_model(), os.getenv("LLM_API_KEY", ""), cache=cache, guided_json=os.getenv("LLM_GUIDED_JSON") == "1")

    def chat_json(self, system: str, prompt: str, schema: dict, *, prompt_version: str, name: str = "output") -> dict:
        key = prompt_hash(self.model, prompt_version, system + "\n" + prompt)
        if self.cache is not None and key in self.cache:
            return self.cache[key]

        body = {
            "model": self.model,
            "temperature": 0,
            "max_tokens": self.max_tokens,  # a runaway (looping) generation ends here instead of at the 120s timeout
            "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}],
        }
        if self.guided_json:
            body["guided_json"] = schema
        else:
            body["response_format"] = {"type": "json_schema", "json_schema": {"name": name, "schema": schema}}
        last_error: Exception | None = None
        for attempt in range(self.retries):
            try:
                result = parse_json(self._post("/chat/completions", body)["choices"][0]["message"]["content"])
                if self.cache is not None:
                    self.cache[key] = result
                return result
            except (urllib.error.URLError, TimeoutError, OSError, KeyError, IndexError, json.JSONDecodeError) as exc:
                last_error = exc
                logger.warning("LLM call failed (attempt %d/%d): %s", attempt + 1, self.retries, exc)
                if attempt + 1 < self.retries:
                    time.sleep(self.backoff * 2**attempt)
        raise LLMUnavailableError(f"LLM call failed after {self.retries} attempts: {last_error}")

    def _post(self, path: str, body: dict) -> dict:
        headers = {"Content-Type": "application/json"}
        if self.api_key:
            headers["Authorization"] = f"Bearer {self.api_key}"
        req = urllib.request.Request(self.base_url + path, data=json.dumps(body).encode("utf-8"), headers=headers)
        with urllib.request.urlopen(req, timeout=self.timeout) as resp:  # noqa: S310 - URL comes from LLM_BASE_URL config
            return json.loads(resp.read())
