import logging
from datetime import datetime
from typing import List, Optional

from shared.llm_client import LLMClient
from shared.mcp_base import MCPAgent
from shared.models import ReasoningStep

logger = logging.getLogger("digest_agent")


class DigestAgent(MCPAgent):
    def __init__(self):
        super().__init__("Digest")
        self.llm = LLMClient()
        self.register_tool("daily_digest", self.daily_digest)
        logger.info("DigestAgent initialized")

    async def daily_digest(self, date: Optional[str] = None):
        reasoning: List[ReasoningStep] = []

        # Если дата не передана, используем текущую
        if not date:
            date = datetime.utcnow().strftime("%Y-%m-%d")
            logger.info(f"Date not provided, using current date: {date}")

        reasoning.append(ReasoningStep(
            step_number=1,
            description="Daily digest requested",
            input_data={"date": date, "auto_date": date is None}
        ))

        prompt = (
            f"Generate a concise daily project digest for {date}.\n\n"
            f"Structure:\n"
            f"📅 Date: {date}\n\n"
            f"✅ Key Achievements (2-3 items):\n"
            f"- [List main accomplishments]\n\n"
            f"🚧 Current Blockers (if any):\n"
            f"- [List or write 'None']\n\n"
            f"👥 Team Status:\n"
            f"- [Brief mood/productivity note]\n\n"
            f"📊 Progress Summary:\n"
            f"- [1-2 sentences on overall progress]\n\n"
            f"Keep it positive, actionable, and under 150 words total."
        )

        reasoning.append(ReasoningStep(
            step_number=2,
            description="Generated digest prompt"
        ))

        try:
            digest = await self.llm.chat(prompt)

            reasoning.append(ReasoningStep(
                step_number=3,
                description="Daily digest generated",
                output_data={
                    "digest_length": len(digest),
                    "date_used": date
                }
            ))

            logger.info("Daily digest completed", extra={
                "date": date,
                "length": len(digest)
            })

            return {
                "date": date,
                "summary": digest,
                "generated_at": datetime.utcnow().isoformat(),
                "reasoning": reasoning
            }
        except Exception as e:
            logger.error("Daily digest failed", extra={"error": str(e)})
            reasoning.append(ReasoningStep(
                step_number=4,
                description="Digest generation failed",
                output_data={"error": str(e)}
            ))
            return {
                "date": date,
                "error": str(e),
                "reasoning": reasoning,
                "fallback": "No updates today"
            }
