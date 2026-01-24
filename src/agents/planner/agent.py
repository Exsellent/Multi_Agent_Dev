import logging
from typing import List, Optional, Dict

from shared.jira import JiraClient
from shared.llm_client import LLMClient
from shared.mcp_base import MCPAgent
from shared.metrics import metric_counter
from shared.models import ReasoningStep

logger = logging.getLogger("planner_agent")


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


class PlannerAgent(MCPAgent):
    """
    Task Planning and Decomposition Agent

    Capabilities:
    1. Break down complex tasks into actionable subtasks
    2. Integration with Jira for task tracking
    3. LLM-powered planning with intelligent fallback

    Demonstrates: sequential reasoning, fallback transparency, Jira integration
    """

    # Baseline subtasks when LLM is unavailable
    BASELINE_SUBTASKS = [
        "Research requirements and constraints",
        "Design solution architecture",
        "Implement core functionality",
        "Add validation and error handling",
        "Write tests and documentation"
    ]

    def __init__(self):
        super().__init__("Planner")
        self.llm = LLMClient()
        self.jira = JiraClient()

        self.register_tool("plan", self.plan)
        self.register_tool("plan_with_jira", self.plan_with_jira)

        logger.info("PlannerAgent initialized with Jira integration and baseline planning")

    def _is_invalid_response(self, subtasks: List[str]) -> bool:
        """Check if LLM response is stub or error"""
        if not subtasks:
            return True

        text = " ".join(subtasks).lower()

        error_indicators = [
            "llm error", "unauthorized", "401", "client error",
            "for more information check", "status/401", "connection error", "timeout"
        ]

        stub_indicators = [
            "[stub]", "you are a senior project planner",
            "return only a numbered list", "break down this task",
            "each subtask should be"
        ]

        return any(indicator in text for indicator in error_indicators + stub_indicators)

    def _next_step(self, reasoning: List[ReasoningStep], description: str,
                   input_data: Optional[Dict] = None, output_data: Optional[Dict] = None):
        """Helper to add sequential reasoning steps"""
        reasoning.append(ReasoningStep(
            step_number=len(reasoning) + 1,
            description=description,
            input_data=input_data or {},
            output_data=output_data or {}
        ))

    @log_method
    @metric_counter("planner")
    async def plan(self, description: str):
        """
        Standard task planning with LLM-powered decomposition

        Uses baseline fallback when LLM is unavailable
        """
        reasoning: List[ReasoningStep] = []
        fallback_used = False

        # Step 1: Request received
        self._next_step(reasoning, "Received task for planning",
                        input_data={"description": description})

        # Step 2: Generate prompt
        prompt = (
            f"You are a senior project planner.\n"
            f"Break down this task into 3-5 concrete, actionable subtasks:\n"
            f"{description}\n\n"
            f"Return ONLY a numbered list, one subtask per line.\n"
            f"Each subtask should be clear and specific."
        )

        self._next_step(reasoning, "Generated prompt for LLM planning",
                        output_data={"prompt_length": len(prompt)})

        try:
            # Attempt LLM planning
            response = await self.llm.chat(prompt)

            # Parse subtasks from response
            subtasks = [
                line.strip().lstrip("0123456789.-) ")
                for line in response.split("\n")
                if line.strip() and line.strip()[0] in "0123456789.-"
            ]

            # Fallback if parsing failed
            if not subtasks:
                subtasks = [line.strip() for line in response.split("\n") if line.strip()][:5]

            # Check if LLM response is valid
            if self._is_invalid_response(subtasks):
                fallback_used = True
                subtasks = self.BASELINE_SUBTASKS
                logger.warning("Planner using baseline subtasks",
                               extra={"task": description})

            # Step 3: Planning completed
            self._next_step(reasoning, "Successfully parsed subtasks from LLM response",
                            output_data={
                                "subtasks_count": len(subtasks),
                                "fallback_used": fallback_used
                            })

            # Step 4 (optional): Fallback annotation
            if fallback_used:
                self._next_step(reasoning, "Baseline subtasks used due to LLM unavailability",
                                output_data={"baseline_subtasks_count": len(subtasks)})

            logger.info("Planning completed",
                        extra={
                            "task": description,
                            "subtasks_count": len(subtasks),
                            "llm_status": "fallback" if fallback_used else "real"
                        })

            return {
                "task": description,
                "subtasks": subtasks,
                "fallback_used": fallback_used,
                "reasoning": reasoning
            }

        except Exception as e:
            logger.error("Planning failed critically", extra={"task": description, "error": str(e)})

            # Use baseline even on exception
            self._next_step(reasoning, "Planning failed with exception — using baseline subtasks",
                            output_data={"error": str(e), "fallback_used": True})

            self._next_step(reasoning, "Baseline subtasks applied",
                            output_data={"subtasks_count": len(self.BASELINE_SUBTASKS)})

            return {
                "task": description,
                "subtasks": self.BASELINE_SUBTASKS,
                "fallback_used": True,
                "reasoning": reasoning,
                "error": str(e)
            }

    @log_method
    @metric_counter("planner")
    async def plan_with_jira(self, description: str, project_key: Optional[str] = None):
        """
        Planning + automatic task creation in Jira

        Two-phase approach:
        1. Planning phase (using plan method)
        2. Jira integration phase (task creation)
        """
        reasoning: List[ReasoningStep] = []

        # Step 1: Jira integration initiated
        self._next_step(reasoning, "Received task for planning with Jira integration",
                        input_data={
                            "description": description,
                            "project_key": project_key or self.jira.project_key
                        })

        # PHASE 1: Planning (embedded as sub-phase)
        plan_result = await self.plan(description)
        subtasks = plan_result.get("subtasks", [])

        # Step 2: Planning phase completed (reference, not extension)
        self._next_step(reasoning, "Planning phase completed",
                        output_data={
                            "subtasks_count": len(subtasks),
                            "fallback_used": plan_result.get("fallback_used", False),
                            "planning_reasoning_steps": len(plan_result.get("reasoning", []))
                        })

        # Early exit if planning failed catastrophically
        if "error" in plan_result and not subtasks:
            self._next_step(reasoning, "Planning failed — Jira integration skipped")
            return {
                **plan_result,
                "jira_issues": [],
                "jira_mode": self.jira.mode,
                "reasoning": reasoning
            }

        # PHASE 2: Jira Integration
        jira_issues = []

        try:
            # Step 3: Create Epic in Jira
            epic_result = await self.jira.create_task(
                summary=f"[Epic] {description}",
                description=f"Auto-generated by Multi-Agent DevOps Assistant\nSubtasks planned: {len(subtasks)}"
            )
            jira_issues.append(epic_result)

            self._next_step(reasoning, "Created Epic in Jira",
                            output_data={
                                "epic_key": epic_result.get("issue_key", "unknown"),
                                "jira_mode": epic_result.get("mode", "unknown")
                            })

            # Step 4: Create subtasks
            for i, subtask in enumerate(subtasks, 1):
                issue_result = await self.jira.create_task(
                    summary=f"[Subtask {i}] {subtask[:80]}",
                    description=f"Part of epic: {description}"
                )
                jira_issues.append(issue_result)

            self._next_step(reasoning, "Successfully created all Jira issues",
                            output_data={
                                "total_issues_created": len(jira_issues),
                                "subtasks_created": len(subtasks)
                            })

            logger.info("Plan with Jira completed successfully",
                        extra={
                            "task": description,
                            "issues_count": len(jira_issues)
                        })

        except Exception as e:
            logger.error("Jira integration failed", extra={"error": str(e)})

            self._next_step(reasoning, "Jira task creation failed",
                            output_data={"error": str(e)})

            jira_issues.append({"status": "error", "details": str(e)})

        return {
            "task": description,
            "subtasks": subtasks,
            "fallback_used": plan_result.get("fallback_used", False),
            "jira_issues": jira_issues,
            "jira_mode": self.jira.mode,
            "planning_reasoning": plan_result.get("reasoning", []),  # Separate for reference
            "reasoning": reasoning  # Main Jira integration reasoning
        }
