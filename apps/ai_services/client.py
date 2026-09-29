"""A small, provider-neutral client for large language models.

Two request formats are supported, both over plain HTTPS with the standard
library (no SDK dependency):
  - "anthropic": the Anthropic Messages API (x-api-key + anthropic-version
    headers, system prompt as its own field, reply as content blocks);
  - "openai": the OpenAI-compatible chat-completions format that many
    providers offer (Authorization: Bearer, system message in the list).

Every failure (not configured, network error, timeout, bad status, odd
reply) becomes ``AIUnavailable``, is logged, and never reaches the user as a
stack trace. Callers fall back to non-AI behaviour.
"""
import json
import logging
import urllib.error
import urllib.request

from django.conf import settings

logger = logging.getLogger(__name__)

ANTHROPIC_URL = "https://api.anthropic.com/v1/messages"
ANTHROPIC_VERSION = "2023-06-01"


class AIUnavailable(Exception):
    """AI is switched off or the provider couldn't give a usable answer."""


def ai_setting(key):
    return getattr(settings, "AI", {}).get(key)


def is_enabled():
    return bool(ai_setting("PROVIDER") and ai_setting("API_KEY") and ai_setting("MODEL"))


class LLMClient:
    def complete(self, *, system, prompt, max_tokens=400):
        raise NotImplementedError


class HTTPClient(LLMClient):
    provider = None

    def __init__(self, *, api_key, model, base_url="", timeout=20, opener=urllib.request.urlopen):
        self.api_key, self.model, self.base_url, self.timeout = api_key, model, base_url, timeout
        self.opener = opener  # injectable for tests

    def _post(self, url, headers, body):
        request = urllib.request.Request(
            url, data=json.dumps(body).encode(), method="POST",
            headers={"content-type": "application/json", **headers},
        )
        try:
            with self.opener(request, timeout=self.timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            logger.warning("ai_request_failed provider=%s status=%s", self.provider, error.code)
        except (urllib.error.URLError, TimeoutError, OSError) as error:
            logger.warning("ai_request_failed provider=%s error=%s", self.provider, type(error).__name__)
        except ValueError:
            logger.warning("ai_request_failed provider=%s error=invalid_json", self.provider)
        raise AIUnavailable("The AI helper isn't available right now.")


class AnthropicClient(HTTPClient):
    provider = "anthropic"

    def complete(self, *, system, prompt, max_tokens=400):
        data = self._post(
            self.base_url or ANTHROPIC_URL,
            {"x-api-key": self.api_key, "anthropic-version": ANTHROPIC_VERSION},
            {"model": self.model, "max_tokens": max_tokens, "system": system,
             "messages": [{"role": "user", "content": prompt}]},
        )
        texts = [block.get("text", "") for block in data.get("content", []) if block.get("type") == "text"]
        text = "".join(texts).strip()
        if not text:
            logger.warning("ai_empty_reply provider=anthropic")
            raise AIUnavailable("The AI helper didn't return an answer.")
        return text


class OpenAICompatibleClient(HTTPClient):
    provider = "openai"

    def complete(self, *, system, prompt, max_tokens=400):
        base = (self.base_url or "https://api.openai.com/v1").rstrip("/")
        data = self._post(
            f"{base}/chat/completions", {"authorization": f"Bearer {self.api_key}"},
            {"model": self.model, "max_tokens": max_tokens,
             "messages": [{"role": "system", "content": system}, {"role": "user", "content": prompt}]},
        )
        try:
            text = (data["choices"][0]["message"]["content"] or "").strip()
        except (KeyError, IndexError, TypeError):
            text = ""
        if not text:
            logger.warning("ai_empty_reply provider=openai")
            raise AIUnavailable("The AI helper didn't return an answer.")
        return text


PROVIDERS = {"anthropic": AnthropicClient, "openai": OpenAICompatibleClient}


def get_client():
    """The configured client, or raise AIUnavailable when AI is switched off."""
    if not is_enabled():
        raise AIUnavailable("The AI helper is switched off.")
    provider = PROVIDERS.get(ai_setting("PROVIDER"))
    if provider is None:
        logger.error("ai_unknown_provider provider=%s", ai_setting("PROVIDER"))
        raise AIUnavailable("The AI helper isn't configured correctly.")
    return provider(api_key=ai_setting("API_KEY"), model=ai_setting("MODEL"),
                    base_url=ai_setting("BASE_URL") or "", timeout=ai_setting("TIMEOUT_SECONDS") or 20)
