import logging
from typing import List, Optional

from shared.mcp_base import MCPAgent
from shared.llm_client import LLMClient
from shared.jira import JiraClient
from shared.models import ReasoningStep

logger = logging.getLogger("planner_agent")


class PlannerAgent(MCPAgent):
    def __init__(self):
        super().__init__("Planner")
        self.llm = LLMClient()
        self.jira = JiraClient()

        self.register_tool("plan", self.plan)
        self.register_tool("plan_with_jira", self.plan_with_jira)

        logger.info("PlannerAgent initialized with Jira integration")

    def _is_invalid_response(self, subtasks: List[str]) -> bool:

        if not subtasks:
            return True

        text = " ".join(subtasks).lower()

        error_indicators = [
            "llm error",
            "unauthorized",
            "401",
            "client error",
            "for more information check",
            "status/401",
            "connection error",
            "timeout"
        ]

        stub_indicators = [
            "[stub]",
            "you are a senior project planner",
            "return only a numbered list",
            "break down this task",
            "each subtask should be"
        ]

        return any(indicator in text for indicator in error_indicators + stub_indicators)

    async def plan(self, description: str):
        """Normal task planning (without Jira)"""
        reasoning: List[ReasoningStep] = []

        reasoning.append(ReasoningStep(
            step_number=1,
            description="Received task for planning",
            input_data={"description": description}
        ))

        prompt = (
            f"You are a senior project planner.\n"
            f"Break down this task into 3-5 concrete, actionable subtasks:\n"
            f"{description}\n\n"
            f"Return ONLY a numbered list, one subtask per line.\n"
            f"Each subtask should be clear and specific."
        )

        reasoning.append(ReasoningStep(
            step_number=2,
            description="Generated prompt for LLM planning"
        ))

        try:
            response = await self.llm.chat(prompt)

            # Subtasks parsing
            subtasks = [
                line.strip().lstrip("0123456789.-) ")
                for line in response.split("\n")
                if line.strip() and line.strip()[0] in "0123456789.-"
            ]

            if not subtasks:
                subtasks = [line.strip() for line in response.split("\n") if line.strip()][:5]

            if self._is_invalid_response(subtasks):
                fallback_subtasks = [
                    "Research requirements and constraints",
                    "Design solution architecture",
                    "Implement core functionality",
                    "Add validation and error handling",
                    "Write tests and documentation"
                ]

                reasoning.append(ReasoningStep(
                    step_number=4,
                    description="Detected LLM stub/error response — using safe fallback subtasks",
                    output_data={
                        "fallback_used": True,
                        "original_response_preview": response[:200]
                    }
                ))

                subtasks = fallback_subtasks
            else:
                reasoning.append(ReasoningStep(
                    step_number=4,
                    description="Successfully parsed subtasks from LLM response",
                    output_data={
                        "subtasks_count": len(subtasks),
                        "subtasks": subtasks
                    }
                ))

            logger.info("Planning completed", extra={
                "task": description,
                "subtasks_count": len(subtasks),
                "llm_status": "real" if not self._is_invalid_response(subtasks) else "fallback"
            })

            return {
                "task": description,
                "subtasks": subtasks,
                "reasoning": reasoning
            }

        except Exception as e:
            logger.error("Planning failed critically", extra={"task": description, "error": str(e)})
            reasoning.append(ReasoningStep(
                step_number=5,
                description="Critical planning failure",
                output_data={"error": str(e)}
            ))
            return {
                "task": description,
                "error": str(e),
                "reasoning": reasoning,
                "fallback_subtasks": ["Manual planning required"]
            }

    async def plan_with_jira(self, description: str, project_key: Optional[str] = None):
        """Planning + creating tasks in Jira"""
        reasoning: List[ReasoningStep] = []

        reasoning.append(ReasoningStep(
            step_number=1,
            description="Received task for planning with Jira integration",
            input_data={"description": description, "project_key": project_key}
        ))

        # First, the usual planning
        plan_result = await self.plan(description)
        subtasks = plan_result.get("subtasks", [])

        reasoning.extend(plan_result.get("reasoning", []))

        if "error" in plan_result and "fallback_subtasks" not in plan_result:
            return plan_result

        reasoning.append(ReasoningStep(
            step_number=2,
            description="Planning phase completed, initiating Jira integration",
            output_data={"subtasks_count": len(subtasks)}
        ))

        jira_issues = []

        try:
            # Creating an Epic
            epic_result = await self.jira.create_task(
                summary=f"[Epic] {description}",
                description=f"Auto-generated by OrchestrAI\nSubtasks planned: {len(subtasks)}"
            )
            jira_issues.append(epic_result)

            reasoning.append(ReasoningStep(
                step_number=3,
                description="Created Epic in Jira",
                output_data={"epic": epic_result}
            ))

            # Creating subtasks
            for i, subtask in enumerate(subtasks, 1):
                issue_result = await self.jira.create_task(
                    summary=f"[Subtask {i}] {subtask}",
                    description=f"Part of epic: {description}"
                )
                jira_issues.append(issue_result)

            reasoning.append(ReasoningStep(
                step_number=4,
                description="Successfully created all Jira issues",
                output_data={"total_issues_created": len(jira_issues)}
            ))

            logger.info("Plan with Jira completed successfully", extra={
                "task": description,
                "issues_count": len(jira_issues)
            })

        except Exception as e:
            logger.error("Jira integration failed", extra={"error": str(e)})
            reasoning.append(ReasoningStep(
                step_number=5,
                description="Jira task creation failed",
                output_data={"error": str(e)}
            ))
            jira_issues.append({"status": "error", "details": str(e)})

        return {
            "task": description,
            "subtasks": subtasks,
            "jira_issues": jira_issues,
            "jira_mode": "mock" if self.jira.mock_mode else "real",
            "reasoning": reasoning
        }