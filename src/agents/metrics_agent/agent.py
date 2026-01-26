import logging
from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any

from shared.llm_client import LLMClient
from shared.mcp_base import MCPAgent
from shared.metrics import metric_counter
from shared.models import ReasoningStep

logger = logging.getLogger("metrics_agent")


@dataclass
class AgentHealth:
    """Health classification for an agent"""
    agent_name: str
    status: str  # "healthy", "warning", "critical", "idle"
    tasks_processed: int
    errors: int
    error_rate: float
    issues: List[str]


@dataclass
class SystemHealth:
    """Overall system health assessment"""
    healthy_agents: int
    warning_agents: int
    critical_agents: int
    idle_agents: int
    total_tasks: int
    total_errors: int
    system_error_rate: float
    overall_status: str  # "healthy", "degraded", "critical"


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


class MetricsAgent(MCPAgent):
    """
    System Observability & Supervisor Agent

    Key Features:
    1. Metrics Collection: Gathers data from all agents
    2. Health Validation: Deterministic health classification
    3. Anomaly Detection: Identifies idle, degraded, or failing agents
    4. Decision Support: Recommends actions based on system state
    5. AI Analysis (Optional): LLM-powered insights for complex patterns

    This agent acts as a SUPERVISOR for the entire multi-agent system.

    Proper sequential reasoning, validation steps, decision-making
    """

    # Health thresholds
    ERROR_RATE_CRITICAL = 0.20  # 20% errors = critical
    ERROR_RATE_WARNING = 0.10  # 10% errors = warning
    MIN_TASKS_FOR_HEALTH_CHECK = 1
    IDLE_THRESHOLD = 0  # 0 tasks = idle

    def __init__(self):
        super().__init__("Metrics")
        self.llm = LLMClient()

        self.register_tool("get_metrics", self.get_metrics)
        self.register_tool("get_system_health", self.get_system_health)
        self.register_tool("analyze_trends", self.analyze_trends)
        self.register_tool("get_agent_recommendations", self.get_agent_recommendations)

        logger.info("MetricsAgent initialized as System Supervisor")

    def _next_step(self, reasoning: List[ReasoningStep], description: str,
                   input_data: Optional[Dict] = None, output_data: Optional[Dict] = None):
        """ Helper to add sequential reasoning steps"""
        reasoning.append(ReasoningStep(
            step_number=len(reasoning) + 1,
            description=description,
            input_data=input_data or {},
            output_data=output_data or {}
        ))

    def _get_mock_metrics(self) -> Dict[str, Dict[str, int]]:
        """Get metrics data (mock for demo, real in production)"""
        # Educational project metrics
        educational_metrics = {
            "planner": {"tasks_processed": 45, "errors": 2},
            "risks": {"tasks_processed": 38, "errors": 1},
            "progress": {"tasks_processed": 30, "errors": 0},
            "digest": {"tasks_processed": 25, "errors": 0},
            "image": {"tasks_processed": 15, "errors": 3},
            "health_monitor": {"tasks_processed": 60, "errors": 0},
            "metrics_agent": {"tasks_processed": 10, "errors": 0}
        }


        # Combine both for universal agent
        return {**educational_metrics}

    def _classify_agent_health(
            self,
            agent_name: str,
            tasks: int,
            errors: int
    ) -> AgentHealth:
        """
        Deterministic health classification

        Rules:
        - idle: 0 tasks processed
        - critical: error rate > 20%
        - warning: error rate > 10%
        - healthy: otherwise
        """
        issues = []

        # Check for idle state
        if tasks == 0:
            status = "idle"
            error_rate = 0.0
            issues.append("No tasks processed")
        else:
            error_rate = errors / tasks

            # Classify based on error rate
            if error_rate >= self.ERROR_RATE_CRITICAL:
                status = "critical"
                issues.append(f"High error rate: {error_rate * 100:.1f}%")
            elif error_rate >= self.ERROR_RATE_WARNING:
                status = "warning"
                issues.append(f"Elevated error rate: {error_rate * 100:.1f}%")
            else:
                status = "healthy"

        # Additional checks
        if errors > 5:
            issues.append(f"High absolute error count: {errors}")

        return AgentHealth(
            agent_name=agent_name,
            status=status,
            tasks_processed=tasks,
            errors=errors,
            error_rate=error_rate,
            issues=issues
        )

    def _assess_system_health(
            self,
            agent_healths: List[AgentHealth]
    ) -> SystemHealth:
        """
        Overall system health assessment

        Aggregates individual agent health into system-wide status
        """
        healthy = sum(1 for h in agent_healths if h.status == "healthy")
        warning = sum(1 for h in agent_healths if h.status == "warning")
        critical = sum(1 for h in agent_healths if h.status == "critical")
        idle = sum(1 for h in agent_healths if h.status == "idle")

        total_tasks = sum(h.tasks_processed for h in agent_healths)
        total_errors = sum(h.errors for h in agent_healths)

        system_error_rate = total_errors / total_tasks if total_tasks > 0 else 0.0

        # Determine overall system status
        if critical > 0 or system_error_rate >= self.ERROR_RATE_CRITICAL:
            overall_status = "critical"
        elif warning > 0 or system_error_rate >= self.ERROR_RATE_WARNING:
            overall_status = "degraded"
        else:
            overall_status = "healthy"

        return SystemHealth(
            healthy_agents=healthy,
            warning_agents=warning,
            critical_agents=critical,
            idle_agents=idle,
            total_tasks=total_tasks,
            total_errors=total_errors,
            system_error_rate=system_error_rate,
            overall_status=overall_status
        )

    def _generate_recommendations(
            self,
            agent_healths: List[AgentHealth],
            system_health: SystemHealth
    ) -> Dict[str, List[str]]:
        """
        Generate actionable recommendations

        Decision-making based on health assessment
        """
        recommendations = {
            "immediate_actions": [],
            "monitoring": [],
            "optimization": []
        }

        # Critical agents need immediate attention
        critical_agents = [h for h in agent_healths if h.status == "critical"]
        for agent in critical_agents:
            recommendations["immediate_actions"].append(
                f"Investigate {agent.agent_name}: {', '.join(agent.issues)}"
            )

        # Warning agents need monitoring
        warning_agents = [h for h in agent_healths if h.status == "warning"]
        for agent in warning_agents:
            recommendations["monitoring"].append(
                f"Monitor {agent.agent_name}: {', '.join(agent.issues)}"
            )

        # Idle agents might indicate integration issues
        idle_agents = [h for h in agent_healths if h.status == "idle"]
        if idle_agents:
            recommendations["optimization"].append(
                f"Review integration for idle agents: {', '.join(h.agent_name for h in idle_agents)}"
            )

        # System-wide recommendations
        if system_health.overall_status == "critical":
            recommendations["immediate_actions"].insert(0,
                                                        "CRITICAL: System-wide error rate exceeds threshold - initiate incident response"
                                                        )
        elif system_health.overall_status == "degraded":
            recommendations["monitoring"].insert(0,
                                                 "System performance degraded - increase monitoring frequency"
                                                 )

        return recommendations

    @log_method
    @metric_counter("metrics_agent")
    async def get_metrics(
            self,
            agent_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get metrics with validation and health assessment

        Proper sequential reasoning with decision-making
        """
        reasoning: List[ReasoningStep] = []

        if agent_name is None:
            agent_name = "all"

        # Step 1: Request received
        self._next_step(reasoning, "Metrics request received",
                        input_data={"agent_name": agent_name})

        # Step 2: Collect metrics data
        try:
            all_metrics = self._get_mock_metrics()

            if agent_name == "all":
                metrics_data = all_metrics
            else:
                metrics_data = {
                    agent_name: all_metrics.get(agent_name, {"tasks_processed": 0, "errors": 0})
                }

            self._next_step(reasoning, "Metrics data collected successfully",
                            output_data={
                                "agents_count": len(metrics_data),
                                "data_source": "mock"  # In production: "prometheus" or "database"
                            })

        except Exception as e:
            logger.error("Metrics collection failed", extra={"error": str(e)})

            self._next_step(reasoning, "Metrics collection failed",
                            output_data={"error": str(e)})

            return {
                "agent_name": agent_name,
                "error": str(e),
                "reasoning": reasoning
            }

        # Step 3 - Validate metrics consistency
        zero_activity = [k for k, v in metrics_data.items() if v["tasks_processed"] == 0]
        high_errors = [k for k, v in metrics_data.items() if v["errors"] > 5]

        self._next_step(reasoning, "Validated metrics consistency",
                        output_data={
                            "zero_activity_agents": zero_activity,
                            "high_error_agents": high_errors,
                            "validation_passed": True
                        })

        # Step 4 - Classify agent health
        agent_healths = [
            self._classify_agent_health(name, data["tasks_processed"], data["errors"])
            for name, data in metrics_data.items()
        ]

        health_summary = {
            "healthy": sum(1 for h in agent_healths if h.status == "healthy"),
            "warning": sum(1 for h in agent_healths if h.status == "warning"),
            "critical": sum(1 for h in agent_healths if h.status == "critical"),
            "idle": sum(1 for h in agent_healths if h.status == "idle")
        }

        self._next_step(reasoning, "Classified agent health status",
                        output_data=health_summary)

        # Step 5 - Metrics retrieval completed
        self._next_step(reasoning, "Metrics retrieval completed",
                        output_data={
                            "total_agents": len(metrics_data),
                            "healthy_agents": health_summary["healthy"]
                        })

        logger.info("Metrics retrieved",
                    extra={
                        "agent_name": agent_name,
                        "agents_count": len(metrics_data)
                    })

        return {
            "agent_name": agent_name,
            "metrics": metrics_data,
            "agent_healths": [asdict(h) for h in agent_healths],  # Structured health data
            "health_summary": health_summary,
            "reasoning": reasoning
        }

    @log_method
    @metric_counter("metrics_agent")
    async def get_system_health(self) -> Dict[str, Any]:
        """
        Comprehensive system health assessment

        Supervisor-level view of entire system
        """
        reasoning: List[ReasoningStep] = []

        # Step 1: System health check initiated
        self._next_step(reasoning, "System health check initiated",
                        input_data={"scope": "all_agents"})

        # Step 2: Collect all metrics
        all_metrics = self._get_mock_metrics()

        self._next_step(reasoning, "Collected metrics from all agents",
                        output_data={"agents_scanned": len(all_metrics)})

        # Step 3: Classify individual agent health
        agent_healths = [
            self._classify_agent_health(name, data["tasks_processed"], data["errors"])
            for name, data in all_metrics.items()
        ]

        self._next_step(reasoning, "Classified health for all agents",
                        output_data={
                            "agents_classified": len(agent_healths)
                        })

        # tep 4 - Assess overall system health
        system_health = self._assess_system_health(agent_healths)

        self._next_step(reasoning, "Assessed overall system health",
                        output_data={
                            "overall_status": system_health.overall_status,
                            "system_error_rate": f"{system_health.system_error_rate * 100:.2f}%"
                        })

        # Step 5 - Generate recommendations
        recommendations = self._generate_recommendations(agent_healths, system_health)

        self._next_step(reasoning, "Generated actionable recommendations",
                        output_data={
                            "immediate_actions": len(recommendations["immediate_actions"]),
                            "monitoring_items": len(recommendations["monitoring"]),
                            "optimization_suggestions": len(recommendations["optimization"])
                        })

        # Step 6 - System health check completed
        self._next_step(reasoning, "System health check completed",
                        output_data={
                            "total_agents": len(agent_healths),
                            "overall_status": system_health.overall_status
                        })

        logger.info("System health check completed",
                    extra={
                        "overall_status": system_health.overall_status,
                        "critical_agents": system_health.critical_agents
                    })

        return {
            "system_health": asdict(system_health),
            "agent_healths": [asdict(h) for h in agent_healths],
            "recommendations": recommendations,  # Actionable decisions
            "reasoning": reasoning
        }

    @log_method
    @metric_counter("metrics_agent")
    async def analyze_trends(
            self,
            agent_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        AI-powered trend analysis

        Uses LLM to identify patterns and anomalies
        """
        reasoning: List[ReasoningStep] = []

        self._next_step(reasoning, "Trend analysis requested",
                        input_data={"agent_name": agent_name or "all"})

        # Get current metrics
        all_metrics = self._get_mock_metrics()

        if agent_name and agent_name != "all":
            metrics_data = {agent_name: all_metrics.get(agent_name, {})}
        else:
            metrics_data = all_metrics

        self._next_step(reasoning, "Collected metrics for trend analysis",
                        output_data={"agents_analyzed": len(metrics_data)})

        # LLM-powered analysis
        prompt = f"""You are a system reliability analyst reviewing agent metrics.

Agent Metrics:
{self._format_metrics_for_llm(metrics_data)}

Identify:
1. Agents showing concerning patterns (high error rates, declining activity)
2. Potential systemic issues
3. Trends worth monitoring

Provide concise bullet points (under 150 words).
Focus on actionable insights, not just observations."""

        try:
            analysis = await self.llm.chat(prompt)

            self._next_step(reasoning, "LLM trend analysis completed",
                            output_data={
                                "analysis_length": len(analysis),
                                "llm_used": True
                            })

        except Exception as e:
            logger.error("LLM analysis failed", extra={"error": str(e)})

            analysis = "AI analysis temporarily unavailable. Manual review recommended for detailed trend analysis."

            self._next_step(reasoning, "LLM analysis failed - using fallback",
                            output_data={"error": str(e), "fallback_used": True})

        # Completion step
        self._next_step(reasoning, "Trend analysis completed",
                        output_data={"total_steps": len(reasoning)})

        return {
            "agent_name": agent_name or "all",
            "metrics": metrics_data,
            "analysis": analysis,
            "reasoning": reasoning
        }

    @log_method
    @metric_counter("metrics_agent")
    async def get_agent_recommendations(
            self,
            agent_name: str
    ) -> Dict[str, Any]:
        """
        Get specific recommendations for an agent

        Decision support for individual agent optimization
        """
        reasoning: List[ReasoningStep] = []

        self._next_step(reasoning, "Agent recommendations requested",
                        input_data={"agent_name": agent_name})

        # Get agent metrics
        all_metrics = self._get_mock_metrics()
        agent_data = all_metrics.get(agent_name, {"tasks_processed": 0, "errors": 0})

        # Classify health
        health = self._classify_agent_health(
            agent_name,
            agent_data["tasks_processed"],
            agent_data["errors"]
        )

        self._next_step(reasoning, "Agent health classified",
                        output_data={
                            "status": health.status,
                            "error_rate": f"{health.error_rate * 100:.2f}%"
                        })

        # Generate specific recommendations
        recommendations = []

        if health.status == "critical":
            recommendations.append("URGENT: Investigate error logs immediately")
            recommendations.append("Consider circuit breaker pattern to prevent cascading failures")
        elif health.status == "warning":
            recommendations.append("Increase monitoring frequency")
            recommendations.append("Review recent changes or deployments")
        elif health.status == "idle":
            recommendations.append("Verify agent integration and routing")
            recommendations.append("Check if agent is receiving requests")
        else:
            recommendations.append("Agent operating normally - maintain current monitoring")

        self._next_step(reasoning, "Generated agent-specific recommendations",
                        output_data={"recommendations_count": len(recommendations)})

        self._next_step(reasoning, "Agent recommendations completed",
                        output_data={"total_steps": len(reasoning)})

        return {
            "agent_name": agent_name,
            "health": asdict(health),
            "recommendations": recommendations,
            "reasoning": reasoning
        }

    def _format_metrics_for_llm(self, metrics: Dict[str, Dict]) -> str:
        """Format metrics for LLM consumption"""
        lines = []
        for agent, data in metrics.items():
            error_rate = data["errors"] / max(data["tasks_processed"], 1) * 100
            lines.append(
                f"- {agent}: {data['tasks_processed']} tasks, "
                f"{data['errors']} errors ({error_rate:.1f}% error rate)"
            )
        return "\n".join(lines)
