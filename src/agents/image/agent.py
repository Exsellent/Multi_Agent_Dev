import logging
from typing import Optional, List

from shared.llm_client import LLMClient
from shared.mcp_base import MCPAgent
from shared.models import ReasoningStep

logger = logging.getLogger("image_agent")


class ImageAgent(MCPAgent):
    def __init__(self):
        super().__init__("Image")
        self.llm = LLMClient()
        self.register_tool("analyze_image", self.analyze_image)
        logger.info("ImageAgent initialized")

    async def analyze_image(
            self,
            image_url: Optional[str] = None,
            image_base64: Optional[str] = None,
            context: Optional[str] = None
    ):
        reasoning: List[ReasoningStep] = []

        reasoning.append(ReasoningStep(
            step_number=1,
            description="Image analysis requested",
            input_data={
                "image_url": image_url,
                "has_base64": image_base64 is not None,
                "context": context
            }
        ))

        if not image_url and not image_base64:
            return {
                "error": "No image provided",
                "reasoning": reasoning
            }

        prompt = (
            "You are a senior UX and system design reviewer.\n"
            "Analyze the provided image and give structured feedback.\n\n"
            f"Context: {context or 'Not provided'}\n\n"
            "Provide:\n"
            "1. Short summary\n"
            "2. Detected issues (type + severity)\n"
            "3. Improvement suggestions\n"
            "Keep it concise and structured."
        )

        reasoning.append(ReasoningStep(
            step_number=2,
            description="Generated image analysis prompt"
        ))

        analysis = await self.llm.chat(prompt)

        reasoning.append(ReasoningStep(
            step_number=3,
            description="Image analysis completed",
            output_data={"analysis_length": len(analysis)}
        ))

        return {
            "summary": analysis,
            "reasoning": reasoning
        }
