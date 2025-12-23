import logging
from typing import List, Dict, Any, Optional

from shared.jira import JiraClient
from shared.llm_client import LLMClient
from shared.mcp_base import MCPAgent
from shared.models import ReasoningStep

logger = logging.getLogger("progress_agent")


class ProgressAgent(MCPAgent):
    def __init__(self):
        super().__init__("Progress")
        self.llm = LLMClient()
        self.jira = JiraClient()

        self.register_tool("analyze_progress", self.analyze_progress)
        self.register_tool("jira_velocity", self.jira_velocity)

        logger.info("ProgressAgent initialized with Jira integration")

    async def analyze_progress(self, commits: List[str]):
        reasoning: List[ReasoningStep] = []

        reasoning.append(ReasoningStep(
            step_number=1,
            description="Received commits for progress analysis",
            input_data={"commits_count": len(commits)}
        ))

        prompt = (
                "You are a progress tracking agent.\n"
                "Analyze these commits and summarize achievements and velocity:\n" +
                "\n".join(f"- {c}" for c in commits) +
                "\n\nBe concise and positive."
        )

        reasoning.append(ReasoningStep(
            step_number=2,
            description="Generated prompt for progress summary"
        ))

        try:
            summary = await self.llm.chat(prompt)

            reasoning.append(ReasoningStep(
                step_number=3,
                description="Received progress summary from LLM",
                output_data={"summary_length": len(summary)}
            ))

            logger.info("Progress analysis completed", extra={"commits_count": len(commits)})

            return {
                "commits_count": len(commits),
                "commits": commits,
                "summary": summary,
                "reasoning": reasoning
            }
        except Exception as e:
            logger.error("Progress analysis failed", extra={"error": str(e)})
            reasoning.append(ReasoningStep(
                step_number=4,
                description="Progress analysis failed",
                output_data={"error": str(e)}
            ))
            return {
                "commits_count": len(commits),
                "error": str(e),
                "reasoning": reasoning,
                "fallback": "Manual review needed"
            }

    async def jira_velocity(self, project_key: Optional[str] = None) -> Dict[str, Any]:
        """Новый tool: Анализ velocity по задачам в Jira"""
        reasoning: List[ReasoningStep] = []

        reasoning.append(ReasoningStep(
            step_number=1,
            description="Jira velocity analysis requested",
            input_data={"project_key": project_key or self.jira.project_key}
        ))

        try:
            issues = await self.jira.get_project_issues(max_results=50)

            reasoning.append(ReasoningStep(
                step_number=2,
                description="Retrieved issues from Jira",
                output_data={"issues_count": len(issues)}
            ))

            if not issues:
                reasoning.append(ReasoningStep(
                    step_number=3,
                    description="No issues found — returning mock data"
                ))
                return {
                    "project": project_key or self.jira.project_key,
                    "total_issues": 0,
                    "status_breakdown": {},
                    "completion_rate": 0.0,
                    "velocity_status": "no_data",
                    "jira_mode": "mock" if self.jira.mock_mode else "real",
                    "reasoning": reasoning
                }

            # Counting by statuses
            status_counts: Dict[str, int] = {}
            for issue in issues:
                status = issue["fields"]["status"]["name"]
                status_counts[status] = status_counts.get(status, 0) + 1

            total = len(issues)
            done_count = sum(v for k, v in status_counts.items() if k.lower() in ["done", "closed", "resolved"])
            completion_rate = round((done_count / total) * 100, 1)

            velocity_status = (
                "excellent" if completion_rate >= 80 else
                "good" if completion_rate >= 60 else
                "at_risk" if completion_rate >= 30 else
                "critical"
            )

            reasoning.append(ReasoningStep(
                step_number=3,
                description="Calculated project velocity",
                output_data={
                    "total_issues": total,
                    "done_count": done_count,
                    "completion_rate": completion_rate,
                    "velocity_status": velocity_status
                }
            ))

            logger.info("Jira velocity calculated", extra={
                "project": project_key or self.jira.project_key,
                "completion_rate": completion_rate,
                "velocity_status": velocity_status
            })

            return {
                "project": project_key or self.jira.project_key,
                "total_issues": total,
                "done_issues": done_count,
                "completion_rate": completion_rate,
                "velocity_status": velocity_status,
                "status_breakdown": status_counts,
                "jira_mode": "mock" if self.jira.mock_mode else "real",
                "reasoning": reasoning
            }

        except Exception as e:
            logger.error("Jira velocity analysis failed", extra={"error": str(e)})
            reasoning.append(ReasoningStep(
                step_number=4,
                description="Jira velocity analysis failed",
                output_data={"error": str(e)}
            ))
            return {
                "error": str(e),
                "jira_mode": "error",
                "reasoning": reasoning,
                "fallback": "Velocity analysis unavailable"
            }
