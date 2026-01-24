import logging
from typing import List

from shared.llm_client import LLMClient
from shared.mcp_base import MCPAgent
from shared.metrics import metric_counter
from shared.models import ReasoningStep

logger = logging.getLogger("risks_agent")


def log_method(func):
    """Decorator for logging method calls"""

    async def wrapper(self, *args, **kwargs):
        logger.info(f"{func.__name__} called with args: {args}, kwargs: {kwargs}")
        try:
            result = await func(self, *args, **kwargs)
            logger.info(f"{func.__name__} completed successfully")
            return result
        except Exception as e:
            logger.error(f"{func.__name__} failed: {str(e)}")
            raise

    return wrapper


class RisksAgent(MCPAgent):
    # Conservative baseline risks for OAuth2 + JWT when LLM is unavailable
    OAUTH2_BASELINE_RISKS = [
        "Token leakage due to improper JWT storage (localStorage vulnerable to XSS)",
        "Insufficient token expiration and rotation policies",
        "Misconfigured OAuth scopes leading to over-privileged access",
        "Lack of refresh token revocation strategy on logout/compromise",
        "Improper validation of JWT signature or issuer (iss claim)",
        "Missing rate limiting on token endpoints (brute force attacks)",
        "Inadequate secret key management for JWT signing",
        "CSRF vulnerabilities in OAuth callback handling",
        "Token replay attacks without proper nonce/jti validation",
        "Exposure of sensitive data in JWT payload (not encrypted)"
    ]

    def __init__(self):
        super().__init__("Risks")
        self.llm = LLMClient()

        self.register_tool("analyze_risks", self.analyze_risks)

        logger.info("RisksAgent initialized with fallback risk models")

    def _is_invalid_response(self, response: str) -> bool:
        """Check if LLM response is stub or error"""
        text = response.lower()
        indicators = [
            "[stub]", "[llm error]", "unauthorized", "401", "client error",
            "for more information check", "status/401", "connection error", "timeout"
        ]
        return any(indicator in text for indicator in indicators)

    def _get_baseline_risks(self, feature: str) -> List[str]:
        """
        Return conservative baseline risks based on feature keywords.
        This ensures Risk Agent ALWAYS provides value, even without LLM.
        """
        feature_lower = feature.lower()

        # OAuth2/JWT specific risks
        if any(kw in feature_lower for kw in ["oauth", "jwt", "token", "auth"]):
            return self.OAUTH2_BASELINE_RISKS

        # Generic security baseline for unknown features
        return [
            "Insufficient input validation and sanitization",
            "Inadequate error handling and information disclosure",
            "Missing security testing and code review",
            "Lack of logging and monitoring for security events",
            "Potential dependency vulnerabilities in third-party libraries"
        ]

    @log_method
    @metric_counter("risks")
    async def analyze_risks(self, feature: str):
        """Analyze risks for a feature with intelligent fallback"""
        reasoning: List[ReasoningStep] = []

        # Explicit fallback tracking flag
        fallback_used = False

        # Step counter for sequential reasoning
        step = 1

        def add_step(description: str, **kwargs):
            nonlocal step
            reasoning.append(ReasoningStep(
                step_number=step,
                description=description,
                **kwargs
            ))
            step += 1

        # Step 1: Request received
        add_step(
            "Risk analysis requested",
            input_data={"feature": feature}
        )

        # Step 2: Generate prompt
        prompt = (
            f"Analyze security and operational risks for implementing: {feature}\n\n"
            f"Consider:\n"
            f"- Security vulnerabilities\n"
            f"- Compliance and regulatory issues\n"
            f"- Performance and scalability risks\n"
            f"- Technical debt and maintainability\n"
            f"- Team capacity and skill gaps\n\n"
            f"Format: Return a bulleted list with '- ' prefix for each risk.\n"
            f"Include mitigation strategy for each risk."
        )

        add_step(
            "Generated risk analysis prompt",
            output_data={"prompt_length": len(prompt)}
        )

        try:
            # Step 3: Attempt LLM analysis
            analysis = await self.llm.chat(prompt)

            # Check if LLM response is valid
            if self._is_invalid_response(analysis):
                # Mark fallback as used
                fallback_used = True

                # Step 4: Fallback to baseline model
                add_step(
                    "LLM error detected — switching to baseline risk model",
                    output_data={"fallback_used": True, "error_type": "stub_or_auth_error"}
                )

                detected_risks = self._get_baseline_risks(feature)
                analysis = (
                        f"⚠️ LLM analysis unavailable. Applied conservative baseline risk model.\n\n"
                        f"Baseline risks for {feature}:\n" +
                        "\n".join(f"- {risk}" for risk in detected_risks)
                )

                logger.warning(
                    "Risk Agent using fallback model",
                    extra={"feature": feature, "risks_count": len(detected_risks)}
                )

            else:
                # LLM response is valid — extract risks
                detected_risks = [
                    line.strip().lstrip("-*• ")
                    for line in analysis.split("\n")
                    if line.strip() and line.strip().startswith(("- ", "* ", "• "))
                ]

                # If LLM didn't return proper bullet points, use baseline
                if not detected_risks:
                    fallback_used = True

                    add_step(
                        "LLM response parsing failed — using baseline model",
                        output_data={"fallback_used": True, "error_type": "parse_error"}
                    )
                    detected_risks = self._get_baseline_risks(feature)
                    analysis += f"\n\n⚠️ Supplemented with baseline risks:\n" + \
                                "\n".join(f"- {risk}" for risk in detected_risks)

            # Final step: Analysis completed
            add_step(
                "Risk analysis completed",
                output_data={
                    "risks_count": len(detected_risks),
                    "fallback_used": fallback_used
                }
            )

            logger.info(
                "Risk analysis completed",
                extra={
                    "feature": feature,
                    "risks_count": len(detected_risks),
                    "analysis_length": len(analysis),
                    "fallback_used": fallback_used
                }
            )

            return {
                "feature": feature,
                "risk_analysis": analysis,
                "detected_risks": detected_risks,
                "fallback_used": fallback_used,
                "reasoning": reasoning
            }

        except Exception as e:
            # Exception handling — still provide baseline risks
            fallback_used = True

            logger.error("Risk analysis failed", extra={"error": str(e), "feature": feature})

            add_step(
                "Risk analysis failed with exception — using baseline model",
                output_data={"error": str(e), "fallback_used": True}
            )

            baseline_risks = self._get_baseline_risks(feature)

            add_step(
                "Baseline risk model applied",
                output_data={"risks_count": len(baseline_risks), "fallback_used": True}
            )

            return {
                "feature": feature,
                "risk_analysis": f"⚠️ LLM analysis failed: {str(e)}\n\nBaseline risks applied:\n" +
                                 "\n".join(f"- {risk}" for risk in baseline_risks),
                "detected_risks": baseline_risks,
                "fallback_used": True,
                "reasoning": reasoning,
                "error": str(e)
            }
