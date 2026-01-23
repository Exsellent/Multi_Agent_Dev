import logging
import os
from typing import Optional

import httpx

from .base import VisionProvider

logger = logging.getLogger("vision.openrouter")


class OpenRouterVisionProvider(VisionProvider):
    """
    OpenRouter Vision Provider with production-ready features:
    - Proper base64 data URL handling
    - Comprehensive logging
    - Response validation
    - Configurable timeout
    """

    def __init__(self):
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        self.model = os.getenv("VISION_MODEL", "openai/gpt-4o-mini")

        # Configurable timeout
        self.timeout = float(os.getenv("VISION_TIMEOUT", "60"))

        if not self.api_key:
            raise RuntimeError("OPENROUTER_API_KEY is not set")

        self.url = "https://openrouter.ai/api/v1/chat/completions"

        logger.info(
            "OpenRouter Vision Provider initialized",
            extra={
                "model": self.model,
                "timeout": self.timeout
            }
        )

    async def analyze(
            self,
            prompt: str,
            image_url: Optional[str] = None,
            image_base64: Optional[str] = None,
    ) -> str:
        """
        Analyze image using OpenRouter Vision API

        Args:
            prompt: Analysis prompt
            image_url: Public URL to image (optional)
            image_base64: Base64 encoded image (optional)

        Returns:
            Analysis text from vision model

        Raises:
            RuntimeError: On API errors or invalid input
        """

        # Validate inputs
        if not image_url and not image_base64:
            raise RuntimeError(
                "Either image_url or image_base64 must be provided"
            )

        # Comprehensive logging
        logger.info(
            "Vision analysis started",
            extra={
                "provider": "openrouter",
                "model": self.model,
                "has_url": bool(image_url),
                "has_base64": bool(image_base64),
                "prompt_length": len(prompt)
            }
        )


        if image_base64:
            # Ensure it's a proper data URL
            if not image_base64.startswith("data:image"):
                # Assume PNG if not specified
                image_source = f"data:image/png;base64,{image_base64}"
                logger.debug("Converted base64 to data URL")
            else:
                image_source = image_base64
        else:
            image_source = image_url

        # Prepare request
        headers = {
            "Authorization": f"Bearer {self.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "http://localhost",
            "X-Title": "multi-agent-devops-assistant",
        }

        payload = {
            "model": self.model,
            "messages": [
                {
                    "role": "user",
                    "content": [
                        {"type": "text", "text": prompt},
                        {
                            "type": "image_url",
                            "image_url": {"url": image_source},
                        },
                    ],
                }
            ],
            "max_tokens": 800,
        }

        try:
            async with httpx.AsyncClient(timeout=self.timeout) as client:
                resp = await client.post(self.url, headers=headers, json=payload)

                # IMPROVED: Better error handling with status codes
                if resp.status_code == 401:
                    raise RuntimeError(
                        "OpenRouter authentication failed - check OPENROUTER_API_KEY"
                    )
                elif resp.status_code == 429:
                    raise RuntimeError(
                        "OpenRouter rate limit exceeded - please try again later"
                    )
                elif resp.status_code != 200:
                    error_text = resp.text
                    logger.error(
                        "OpenRouter API error",
                        extra={
                            "status_code": resp.status_code,
                            "error_text": error_text[:200]  # Limit error text length
                        }
                    )
                    raise RuntimeError(
                        f"OpenRouter API error {resp.status_code}: {error_text}"
                    )

                data = resp.json()

                # Response validation
                choices = data.get("choices", [])
                if not choices:
                    logger.error("Empty choices in OpenRouter response")
                    raise RuntimeError("Empty response from OpenRouter")

                message = choices[0].get("message", {})
                content = message.get("content", "")

                if not content:
                    logger.error("Empty content in OpenRouter response")
                    raise RuntimeError("Empty content in OpenRouter response")

                # Success logging with usage info
                usage = data.get("usage", {})
                logger.info(
                    "Vision analysis completed",
                    extra={
                        "response_length": len(content),
                        "usage_tokens": usage.get("total_tokens", "unknown"),
                        "usage_prompt_tokens": usage.get("prompt_tokens", "unknown"),
                        "usage_completion_tokens": usage.get("completion_tokens", "unknown")
                    }
                )

                return content

        except httpx.TimeoutException:
            logger.error(
                "Vision request timeout",
                extra={"timeout": self.timeout}
            )
            raise RuntimeError(
                f"OpenRouter request timeout after {self.timeout}s"
            )
        except httpx.HTTPError as e:
            logger.error(
                "Vision request HTTP error",
                extra={"error": str(e)}
            )
            raise RuntimeError(f"OpenRouter HTTP error: {e}")
        except Exception as e:
            logger.exception("Vision request unexpected error")
            raise RuntimeError(f"OpenRouter unexpected error: {e}")

    def get_config(self) -> dict:
        """
        Get current configuration

        Returns:
            Configuration dictionary
        """
        return {
            "provider": "openrouter",
            "model": self.model,
            "timeout": self.timeout,
            "has_api_key": bool(self.api_key)
        }