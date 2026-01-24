import logging
from typing import List, Optional, Dict, Any
from datetime import date as date_module

from shared.llm_client import LLMClient
from shared.mcp_base import MCPAgent
from shared.metrics import metric_counter
from shared.models import ReasoningStep

logger = logging.getLogger("digest_agent")


def log_method(func):
    """Decorator for logging method calls"""

    async def wrapper(self, *args, **kwargs):
        logger.info(f"{func.__name__} called")
        try:
            result = await func(self, *args, **kwargs)
            logger.info(f"{func.__name__} completed successfully")
            return result
        except Exception as e:
            logger.error(f"{func.__name__} failed: {str(e)}")
            raise

    return wrapper


class DigestAgent(MCPAgent):
    """
    Daily Project Digest Agent

    Generates concise daily summaries of project activity including:
    - Key achievements
    - Blockers
    - Team mood

    Proper sequential reasoning, explicit fallbacks, validation steps
    """

    def __init__(self):
        super().__init__("Digest")
        self.llm = LLMClient()

        self.register_tool("daily_digest", self.daily_digest)

        logger.info("DigestAgent initialized")

    def _next_step(self, reasoning: List[ReasoningStep], description: str,
                   input_data: Optional[Dict] = None, output_data: Optional[Dict] = None):
        """Helper to add sequential reasoning steps"""
        reasoning.append(ReasoningStep(
            step_number=len(reasoning) + 1,
            description=description,
            input_data=input_data or {},
            output_data=output_data or {}
        ))

    def _is_invalid_response(self, response: str) -> bool:
        """Check if LLM response is stub or error"""
        text = response.lower()
        indicators = [
            "[stub]", "[llm error]", "unauthorized", "401", "client error",
            "for more information check", "status/401", "connection error", "timeout"
        ]
        return any(indicator in text for indicator in indicators)

    @log_method
    @metric_counter("digest")
    async def daily_digest(self, date: Optional[str] = None) -> Dict[str, Any]:
        """
        Generate daily project digest

        Proper sequential reasoning with validation and fallback handling
        """
        reasoning: List[ReasoningStep] = []

        # Handle date
        if date is None:
            date = date_module.today().isoformat()

        # Step 1: Request received
        self._next_step(reasoning, "Daily digest requested",
                        input_data={"date": date})

        # Prepare prompt
        prompt = (
            f"Generate a concise daily project digest for {date}.\n"
            f"Include key achievements, blockers, team mood.\n"
            f"Keep it positive and under 200 words."
        )

        # Step 2: LLM request initiated
        digest = None
        fallback_used = False

        try:
            digest = await self.llm.chat(prompt)

            # Explicit validation step
            if self._is_invalid_response(digest):
                fallback_used = True

                # Explicit fallback step
                self._next_step(reasoning, "LLM response invalid - using fallback digest",
                                output_data={"fallback_used": True})

                digest = f"Daily digest for {date}: The team is making steady progress. No major blockers reported."
            else:
                # Successful LLM response
                self._next_step(reasoning, "LLM digest generated successfully",
                                output_data={
                                    "digest_length": len(digest),
                                    "fallback_used": False
                                })

        except Exception as e:
            logger.error("Daily digest generation failed", extra={"error": str(e)})
            fallback_used = True

            # Explicit exception fallback step
            self._next_step(reasoning, "LLM request failed - using fallback digest",
                            output_data={
                                "error": str(e),
                                "fallback_used": True
                            })

            digest = f"Daily digest for {date}: The team is making steady progress. No major blockers reported."

        # Step 3 - Digest finalized (ALWAYS present)
        self._next_step(reasoning, "Daily digest completed",
                        output_data={
                            "final_length": len(digest),
                            "fallback_used": fallback_used
                        })

        logger.info("Daily digest completed",
                    extra={
                        "date": date,
                        "length": len(digest),
                        "fallback": fallback_used
                    })

        return {
            "date": date,
            "summary": digest,
            "fallback_used": fallback_used,
            "reasoning": reasoning
        }