import os

from .fallback import FallbackVisionProvider
from .openrouter import OpenRouterVisionProvider


def get_vision_provider():
    provider = os.getenv("VISION_PROVIDER", "fallback")

    if provider == "openrouter":
        return OpenRouterVisionProvider()

    return FallbackVisionProvider()
