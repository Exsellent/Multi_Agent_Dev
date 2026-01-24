import logging
from dataclasses import dataclass
from typing import List, Optional, Dict, Any

from shared.llm_client import LLMClient
from shared.mcp_base import MCPAgent
from shared.metrics import metric_counter
from shared.models import ReasoningStep
from shared.vision import get_vision_provider
from shared.vision.local_file import LocalFileVisionService

logger = logging.getLogger("image_agent")


@dataclass
class AnalysisConfidence:
    """Confidence scoring for analysis results"""
    overall_score: float  # 0.0 - 1.0
    vision_quality: float
    context_completeness: float
    reasoning_depth: float
    uncertainty_areas: List[str]


@dataclass
class ArchitecturalInsight:
    """Structured architectural insight"""
    component: str
    insight_type: str  # "strength", "weakness", "risk", "opportunity"
    description: str
    confidence: float
    evidence: str


class ImageAgent(MCPAgent):
    """
    Educational Image Analysis Agent

    Purpose: Demonstrate vision integration with basic reasoning
    Focus: Reliability, error handling, clear structure
    """

    def __init__(self):
        super().__init__("Image")

        self.llm = LLMClient()
        provider = get_vision_provider()
        self.vision_service = LocalFileVisionService(provider)

        # Internal decision state (not exposed to LLM)
        self._analysis_cache: Dict[str, Any] = {}

        logger.info(
            "ImageAgent initialized with vision provider: %s",
            provider.__class__.__name__,
        )

        self.register_tool("analyze_image", self.analyze_image)
        self.register_tool("analyze_architecture", self.analyze_architecture)
        self.register_tool("analyze_local_file", self.analyze_local_file)

    def _invalid_response(self, text: str) -> bool:
        """Internal decision logic - validates response quality"""
        if not text:
            return True
        t = text.lower()
        return any(x in t for x in [
            "unauthorized",
            "invalid api key",
            "vision unavailable",
            "error",
        ])

    def _calculate_confidence(
            self,
            analysis: str,
            context: Optional[str],
            image_source: str
    ) -> AnalysisConfidence:
        """
        INTERNAL DECISION MODEL
        Agent decides confidence, LLM only explains
        """
        # Vision quality score
        vision_score = 0.9 if len(analysis) > 500 else 0.6

        # Context completeness
        context_score = 0.8 if context else 0.5

        # Reasoning depth (heuristic: presence of structured sections)
        depth_indicators = ["summary", "components", "risks", "recommendations"]
        depth_score = sum(
            1 for indicator in depth_indicators
            if indicator in analysis.lower()
        ) / len(depth_indicators)

        # Overall confidence
        overall = (vision_score + context_score + depth_score) / 3

        # Identify uncertainty areas
        uncertainty = []
        if not context:
            uncertainty.append("No context provided - general analysis only")
        if len(analysis) < 300:
            uncertainty.append("Vision response shorter than expected")
        if image_source == "fallback":
            uncertainty.append("Fallback mode - no actual image analysis")

        return AnalysisConfidence(
            overall_score=overall,
            vision_quality=vision_score,
            context_completeness=context_score,
            reasoning_depth=depth_score,
            uncertainty_areas=uncertainty
        )

    @metric_counter("image")
    async def analyze_image(
            self,
            image_url: Optional[str] = None,
            context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Analyze image with confidence scoring and structured insights

        Key improvement: Agent decides quality, LLM explains content
        """
        reasoning: List[ReasoningStep] = []

        reasoning.append(ReasoningStep(
            step_number=1,
            description="Image analysis requested",
            input_data={
                "image_url": image_url,
                "context": context,
            },
        ))

        if not image_url:
            return {
                "error": "image_url is required",
                "reasoning": reasoning,
            }

        prompt = f"""
Analyze the image carefully and provide structured output.

Context: {context or "General architecture / system design"}

Required structure:
1. SUMMARY (2-3 sentences)
2. KEY COMPONENTS (list main elements)
3. IDENTIFIED ISSUES OR RISKS (if any)
4. RECOMMENDATIONS (actionable)

Be specific and concrete.
"""

        try:
            # Vision analysis
            analysis = await self.vision_service.provider.analyze(
                prompt=prompt,
                image_url=image_url,
            )

            if self._invalid_response(analysis):
                raise RuntimeError("Invalid response from vision provider")

            # INTERNAL DECISION: Calculate confidence (not LLM's job)
            confidence = self._calculate_confidence(
                analysis=analysis,
                context=context,
                image_source="vision"
            )

            reasoning.append(ReasoningStep(
                step_number=2,
                description="Vision analysis completed",
                output_data={
                    "provider": self.vision_service.provider.__class__.__name__,
                    "length": len(analysis),
                    "confidence_score": confidence.overall_score,
                },
            ))

            # Extract structured insights (LLM's job: structure content)
            insights_prompt = f"""
From this analysis:
{analysis}

Extract top 3 architectural insights in JSON format:
[
  {{
    "component": "component name",
    "insight_type": "strength|weakness|risk|opportunity",
    "description": "clear description",
    "evidence": "what in the image supports this"
  }}
]

Return ONLY valid JSON.
"""

            insights_json = await self.llm.chat(insights_prompt)

            reasoning.append(ReasoningStep(
                step_number=3,
                description="Structured insights extracted",
                output_data={"insights_ready": True},
            ))

            return {
                "image_source": "url",
                "analysis": analysis,
                "structured_insights": insights_json,
                "confidence": {
                    "overall": confidence.overall_score,
                    "vision_quality": confidence.vision_quality,
                    "context_completeness": confidence.context_completeness,
                    "reasoning_depth": confidence.reasoning_depth,
                    "uncertainty_areas": confidence.uncertainty_areas,
                },
                "vision_provider": self.vision_service.provider.__class__.__name__,
                "reasoning": reasoning,
            }

        except Exception as e:
            logger.exception("Vision analysis failed, fallback to text LLM")

            # INTERNAL DECISION: Low confidence for fallback
            fallback_confidence = AnalysisConfidence(
                overall_score=0.3,
                vision_quality=0.0,
                context_completeness=0.5 if context else 0.2,
                reasoning_depth=0.4,
                uncertainty_areas=[
                    "No vision analysis - text-only fallback",
                    "Cannot verify actual image content",
                    "High uncertainty"
                ]
            )

            fallback_prompt = f"""
You are a senior software architect.

IMPORTANT: Vision analysis failed. You cannot see the image.

Image URL: {image_url}
Context: {context}

Provide a best-effort architectural analysis based ONLY on the context.
Clearly state assumptions and limitations.
"""

            text = await self.llm.chat(fallback_prompt)

            reasoning.append(ReasoningStep(
                step_number=3,
                description="Fallback text-only analysis (low confidence)",
                output_data={
                    "error": str(e),
                    "confidence_score": fallback_confidence.overall_score,
                },
            ))

            return {
                "analysis": text,
                "fallback": True,
                "error": str(e),
                "confidence": {
                    "overall": fallback_confidence.overall_score,
                    "vision_quality": fallback_confidence.vision_quality,
                    "context_completeness": fallback_confidence.context_completeness,
                    "reasoning_depth": fallback_confidence.reasoning_depth,
                    "uncertainty_areas": fallback_confidence.uncertainty_areas,
                },
                "reasoning": reasoning,
            }

    @metric_counter("image")
    async def analyze_local_file(
            self,
            file_path: str,
            context: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Analyze local image file with confidence tracking
        """
        reasoning: List[ReasoningStep] = []

        reasoning.append(ReasoningStep(
            step_number=1,
            description="Local file analysis requested",
            input_data={
                "file_path": file_path,
                "context": context,
            },
        ))

        try:
            analysis = await self.vision_service.analyze_file(
                file_path=file_path,
                prompt=context or "Architecture analysis"
            )

            # INTERNAL DECISION: Calculate confidence
            confidence = self._calculate_confidence(
                analysis=analysis,
                context=context,
                image_source="local_file"
            )

            reasoning.append(ReasoningStep(
                step_number=2,
                description="Local file analyzed via vision provider",
                output_data={
                    "confidence_score": confidence.overall_score,
                },
            ))

            return {
                "analysis": analysis,
                "confidence": {
                    "overall": confidence.overall_score,
                    "vision_quality": confidence.vision_quality,
                    "context_completeness": confidence.context_completeness,
                    "reasoning_depth": confidence.reasoning_depth,
                    "uncertainty_areas": confidence.uncertainty_areas,
                },
                "vision_provider": self.vision_service.provider.__class__.__name__,
                "reasoning": reasoning,
            }

        except Exception as e:
            logger.exception("Local file analysis failed")

            fallback_confidence = AnalysisConfidence(
                overall_score=0.2,
                vision_quality=0.0,
                context_completeness=0.3 if context else 0.1,
                reasoning_depth=0.3,
                uncertainty_areas=[
                    "File analysis failed",
                    "No image content available",
                    "Very high uncertainty"
                ]
            )

            reasoning.append(ReasoningStep(
                step_number=3,
                description="Local file analysis failed",
                output_data={
                    "error": str(e),
                    "confidence_score": fallback_confidence.overall_score,
                },
            ))

            fallback_prompt = f"""
You are a senior architect.

CRITICAL: Image file could not be processed. You cannot see any image.

File: {file_path}
Context: {context}

Provide a minimal analysis with clear disclaimers about limitations.
"""

            text = await self.llm.chat(fallback_prompt)

            return {
                "analysis": text,
                "fallback": True,
                "error": str(e),
                "confidence": {
                    "overall": fallback_confidence.overall_score,
                    "vision_quality": fallback_confidence.vision_quality,
                    "context_completeness": fallback_confidence.context_completeness,
                    "reasoning_depth": fallback_confidence.reasoning_depth,
                    "uncertainty_areas": fallback_confidence.uncertainty_areas,
                },
                "reasoning": reasoning,
            }

    async def analyze_architecture(
            self,
            image_url: str,
            project_context: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Convenience method for architecture-specific analysis"""
        return await self.analyze_image(
            image_url=image_url,
            context=project_context or "Software architecture diagram",
        )
