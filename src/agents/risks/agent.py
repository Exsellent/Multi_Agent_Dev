import logging
from typing import List

from shared.llm_client import LLMClient
from shared.mcp_base import MCPAgent
from shared.models import ReasoningStep

logger = logging.getLogger("risks_agent")


class RisksAgent(MCPAgent):
    def __init__(self):
        super().__init__("Risks")
        self.llm = LLMClient()
        self.register_tool("analyze_risks", self.analyze_risks)
        logger.info("RisksAgent initialized")

    async def analyze_risks(self, feature: str):
        reasoning: List[ReasoningStep] = []

        reasoning.append(ReasoningStep(
            step_number=1,
            description="Risk analysis requested",
            input_data={"feature": feature}
        ))

        prompt = (
            f"Analyze risks for implementing: {feature}\n\n"
            f"Provide a concise risk analysis covering:\n"
            f"1. Security risks (top 2-3)\n"
            f"2. Performance risks (top 2)\n"
            f"3. Technical debt risks (top 2)\n"
            f"4. Compliance risks (if applicable)\n\n"
            f"For each risk, provide:\n"
            f"- Risk name (brief)\n"
            f"- Impact (High/Medium/Low)\n"
            f"- Quick mitigation strategy (1 sentence)\n\n"
            f"Keep total response under 500 words. Use bullet points."
        )

        reasoning.append(ReasoningStep(
            step_number=2,
            description="Generated risk analysis prompt"
        ))

        try:
            analysis = await self.llm.chat(prompt)

            # Improved risk extraction - risk rows only
            detected_risks = []
            for line in analysis.split("\n"):
                line = line.strip()
                # We are looking for lines that look like risks (start with markers or contain "Risk:")
                if line and (
                        line.startswith(("- ", "* ", "• ", "1.", "2.", "3.", "4.", "5.")) or
                        "Risk:" in line or
                        "risk" in line.lower()
                ):
                    # Removing markers and extra characters
                    clean_line = line.lstrip("-*•0123456789. ").strip()
                    if len(clean_line) > 20:  # Meaningful lines only
                        detected_risks.append(clean_line)

            # We limit it to the top 10 risks
            detected_risks = detected_risks[:10]

            reasoning.append(ReasoningStep(
                step_number=3,
                description="Risk analysis completed",
                output_data={
                    "risks_count": len(detected_risks),
                    "analysis_length": len(analysis)
                }
            ))

            logger.info("Risk analysis completed", extra={
                "feature": feature,
                "risks_found": len(detected_risks)
            })

            return {
                "feature": feature,
                "risk_analysis": analysis,
                "detected_risks": detected_risks,
                "total_risks": len(detected_risks),
                "reasoning": reasoning
            }
        except Exception as e:
            logger.error("Risk analysis failed", extra={"error": str(e)})
            reasoning.append(ReasoningStep(
                step_number=4,
                description="Risk analysis failed",
                output_data={"error": str(e)}
            ))
            return {
                "feature": feature,
                "error": str(e),
                "reasoning": reasoning,
                "fallback": "Manual risk assessment required"
            }
