import asyncio
import logging
import os
from typing import Dict, Any

import httpx

logger = logging.getLogger("llm_client")


# Custom exceptions for better error handling
class LLMProviderError(Exception):
    """Base exception for LLM providers"""
    pass


class LLMRateLimitError(LLMProviderError):
    """Rate limit exceeded"""
    pass


class LLMAuthError(LLMProviderError):
    """Authentication failed"""
    pass


class LLMClient:
    """
    LLM Client with production-ready features:
    - Configurable model from environment
    - Retry logic with exponential backoff
    - Proper error handling
    - Comprehensive logging
    """

    def __init__(self):
        self.provider = os.getenv("LLM_PROVIDER", "stub").lower()

        if self.provider == "groq":
            self.api_key = os.getenv("GROQ_API_KEY")
            if not self.api_key:
                raise RuntimeError("GROQ_API_KEY is not set")

            self.base_url = "https://api.groq.com/openai/v1/chat/completions"

            # Model from environment
            self.model = os.getenv("LLM_MODEL", "llama-3.3-70b-versatile")

            # Configurable timeout and retries
            self.timeout = float(os.getenv("LLM_TIMEOUT", "30"))
            self.max_retries = int(os.getenv("LLM_MAX_RETRIES", "2"))

            logger.info(
                "LLM Client initialized",
                extra={
                    "provider": self.provider,
                    "model": self.model,
                    "timeout": self.timeout,
                    "max_retries": self.max_retries
                }
            )

    async def chat(self, prompt: str) -> str:
        """
        Send a chat request to LLM

        Args:
            prompt: User prompt

        Returns:
            LLM response text

        Raises:
            LLMProviderError: On provider errors
            LLMRateLimitError: On rate limit (after retries)
            LLMAuthError: On authentication failure
        """
        logger.info("LLM request started", extra={
            "provider": self.provider,
            "model": self.model if self.provider == "groq" else "stub",
            "prompt_length": len(prompt)
        })

        # Stub mode for development
        if self.provider == "stub":
            return f"[stub] {prompt}"

        if self.provider != "groq":
            raise LLMProviderError(f"Unsupported provider: {self.provider}")

        # Prepare request
        payload = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": 0.7,
            "max_tokens": 1024
        }

        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json"
        }

        # Retry logic with exponential backoff
        last_exception = None

        for attempt in range(self.max_retries + 1):
            try:
                async with httpx.AsyncClient(timeout=self.timeout) as client:
                    resp = await client.post(
                        self.base_url,
                        json=payload,
                        headers=headers
                    )

                    # Handle rate limiting
                    if resp.status_code == 429:
                        if attempt < self.max_retries:
                            wait_time = 2 ** attempt  # Exponential backoff
                            logger.warning(
                                f"Rate limited, retrying in {wait_time}s",
                                extra={
                                    "attempt": attempt + 1,
                                    "max_retries": self.max_retries
                                }
                            )
                            await asyncio.sleep(wait_time)
                            continue
                        else:
                            raise LLMRateLimitError(
                                f"Rate limit exceeded after {self.max_retries} retries"
                            )

                    # Handle authentication errors
                    if resp.status_code == 401:
                        raise LLMAuthError("Invalid API key")

                    # Raise for other HTTP errors
                    resp.raise_for_status()

                    # Parse response
                    data = resp.json()

                    # Validate response structure
                    choices = data.get("choices", [])
                    if not choices:
                        raise LLMProviderError("Empty response from LLM provider")

                    content = choices[0].get("message", {}).get("content", "")
                    if not content:
                        raise LLMProviderError("Empty content in LLM response")

                    # Log success
                    logger.info("LLM response received", extra={
                        "response_length": len(content),
                        "usage_tokens": data.get("usage", {}).get("total_tokens", "unknown"),
                        "usage_prompt_tokens": data.get("usage", {}).get("prompt_tokens", "unknown"),
                        "usage_completion_tokens": data.get("usage", {}).get("completion_tokens", "unknown"),
                        "attempts": attempt + 1
                    })

                    return content

            except (LLMRateLimitError, LLMAuthError):
                # Don't retry auth errors or final rate limit
                raise

            except httpx.HTTPStatusError as e:
                last_exception = e
                if attempt < self.max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"HTTP error {e.response.status_code}, retrying in {wait_time}s",
                        extra={"attempt": attempt + 1, "status_code": e.response.status_code}
                    )
                    await asyncio.sleep(wait_time)
                    continue

            except Exception as e:
                last_exception = e
                if attempt < self.max_retries:
                    wait_time = 2 ** attempt
                    logger.warning(
                        f"Request failed: {type(e).__name__}, retrying in {wait_time}s",
                        extra={"attempt": attempt + 1, "error": str(e)}
                    )
                    await asyncio.sleep(wait_time)
                    continue

        # Raise exception instead of returning error string
        logger.error(
            "LLM request failed after all retries",
            extra={
                "error_type": type(last_exception).__name__,
                "error": str(last_exception),
                "attempts": self.max_retries + 1
            }
        )
        raise LLMProviderError(
            f"LLM request failed after {self.max_retries + 1} attempts: {last_exception}"
        )

    async def chat_structured(self, prompt: str) -> Dict[str, Any]:
        """
        Send a chat request expecting structured output

        Currently returns raw text - can be extended to support
        JSON schema validation when Groq supports it

        Args:
            prompt: User prompt

        Returns:
            Dict with 'raw' key containing response text
        """
        text = await self.chat(prompt)
        return {"raw": text}

    def get_config(self) -> Dict[str, Any]:
        """
        Get current configuration

        Returns:
            Configuration dictionary
        """
        return {
            "provider": self.provider,
            "model": self.model if self.provider == "groq" else "stub",
            "timeout": getattr(self, "timeout", None),
            "max_retries": getattr(self, "max_retries", None)
        }