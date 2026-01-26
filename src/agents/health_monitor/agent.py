import logging
from dataclasses import dataclass, asdict
from typing import Dict, Any, List, Optional

import httpx

from shared.llm_client import LLMClient
from shared.mcp_base import MCPAgent
from shared.metrics import metric_counter
from shared.models import ReasoningStep

logger = logging.getLogger("health_monitor_agent")


@dataclass
class AgentHealthStatus:
    """Individual agent health assessment"""
    agent_name: str
    status: str  # "OK", "WARNING", "CRITICAL", "UNKNOWN"
    error_rate: float
    tasks_processed: int
    errors: int
    reachable: bool
    issues: List[str]


@dataclass
class SystemHealthStatus:
    """Overall system health assessment"""
    overall_status: str  # "HEALTHY", "DEGRADED", "CRITICAL", "UNKNOWN"
    total_agents: int
    ok_agents: int
    warning_agents: int
    critical_agents: int
    unknown_agents: int
    unreachable_agents: int
    systemic_risk: bool
    issues: List[str]


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


class HealthMonitorAgent(MCPAgent):
    """
    System Health Monitoring & Diagnostics Agent

    Key Features:
    1. Metrics Integration: Uses MetricsAgent data as source of truth
    2. Health Classification: Deterministic status based on error rates
    3. Reachability Checks: HTTP endpoint validation
    4. Systemic Risk Detection: Identifies cascading failures
    5. Decision Support: Actionable recommendations for issues
    6. AI Analysis (Optional): LLM-powered root cause analysis

    Proper sequential reasoning with metrics integration and decision-making

    This agent is a SUPERVISOR that connects metrics to health decisions.
    """

    # Health classification thresholds
    ERROR_RATE_CRITICAL = 0.15  # 15% errors = critical
    ERROR_RATE_WARNING = 0.05  # 5% errors = warning
    SYSTEMIC_RISK_THRESHOLD = 2  # 2+ critical agents = systemic risk
    HTTP_TIMEOUT = 5.0

    def __init__(self):
        super().__init__("HealthMonitor")
        self.llm = LLMClient()

        self.register_tool("check_health", self.check_health)
        self.register_tool("diagnose_agent", self.diagnose_agent)
        self.register_tool("get_system_status", self.get_system_status)

        logger.info("HealthMonitorAgent initialized as System Supervisor")

    def _next_step(self, reasoning: List[ReasoningStep], description: str,
                   input_data: Optional[Dict] = None, output_data: Optional[Dict] = None):
        """ Helper to add sequential reasoning steps"""
        reasoning.append(ReasoningStep(
            step_number=len(reasoning) + 1,
            description=description,
            input_data=input_data or {},
            output_data=output_data or {}
        ))

    def _classify_agent_health(
            self,
            agent_name: str,
            tasks_processed: int,
            errors: int,
            reachable: bool = True
    ) -> AgentHealthStatus:
        """
        Deterministic health classification

        Critical decision-making based on metrics and reachability
        """
        issues = []

        # Check reachability first
        if not reachable:
            status = "UNKNOWN"
            error_rate = 0.0
            issues.append("Agent unreachable via HTTP")
            return AgentHealthStatus(
                agent_name=agent_name,
                status=status,
                error_rate=error_rate,
                tasks_processed=tasks_processed,
                errors=errors,
                reachable=reachable,
                issues=issues
            )

        # Check activity
        if tasks_processed == 0:
            status = "UNKNOWN"
            error_rate = 0.0
            issues.append("No activity detected")
        else:
            error_rate = errors / tasks_processed

            # Classify based on error rate
            if error_rate >= self.ERROR_RATE_CRITICAL:
                status = "CRITICAL"
                issues.append(f"Critical error rate: {error_rate * 100:.1f}%")
            elif error_rate >= self.ERROR_RATE_WARNING:
                status = "WARNING"
                issues.append(f"Elevated error rate: {error_rate * 100:.1f}%")
            else:
                status = "OK"

        # Additional checks
        if errors > 10:
            issues.append(f"High absolute error count: {errors}")

        return AgentHealthStatus(
            agent_name=agent_name,
            status=status,
            error_rate=error_rate,
            tasks_processed=tasks_processed,
            errors=errors,
            reachable=reachable,
            issues=issues
        )

    def _assess_system_health(
            self,
            agent_healths: List[AgentHealthStatus]
    ) -> SystemHealthStatus:
        """
        System-wide health assessment

        Aggregates individual agent health into system status
        """
        ok = sum(1 for h in agent_healths if h.status == "OK")
        warning = sum(1 for h in agent_healths if h.status == "WARNING")
        critical = sum(1 for h in agent_healths if h.status == "CRITICAL")
        unknown = sum(1 for h in agent_healths if h.status == "UNKNOWN")
        unreachable = sum(1 for h in agent_healths if not h.reachable)

        # Determine overall status
        if critical >= self.SYSTEMIC_RISK_THRESHOLD:
            overall_status = "CRITICAL"
            systemic_risk = True
        elif critical > 0:
            overall_status = "DEGRADED"
            systemic_risk = False
        elif warning > 0:
            overall_status = "DEGRADED"
            systemic_risk = False
        elif unknown > 0:
            overall_status = "UNKNOWN"
            systemic_risk = False
        else:
            overall_status = "HEALTHY"
            systemic_risk = False

        # Collect system-wide issues
        issues = []
        if systemic_risk:
            issues.append(f"SYSTEMIC RISK: {critical} agents in critical state")
        if unreachable > 0:
            issues.append(f"{unreachable} agents unreachable")
        if critical > 0 and not systemic_risk:
            issues.append(f"{critical} agent(s) require immediate attention")

        return SystemHealthStatus(
            overall_status=overall_status,
            total_agents=len(agent_healths),
            ok_agents=ok,
            warning_agents=warning,
            critical_agents=critical,
            unknown_agents=unknown,
            unreachable_agents=unreachable,
            systemic_risk=systemic_risk,
            issues=issues
        )

    def _generate_recommendations(
            self,
            agent_healths: List[AgentHealthStatus],
            system_health: SystemHealthStatus
    ) -> Dict[str, List[str]]:
        """
        Generate actionable recommendations

        Decision support based on health assessment
        """
        recommendations = {
            "immediate_actions": [],
            "monitoring": [],
            "investigation": []
        }

        # Systemic risk requires immediate escalation
        if system_health.systemic_risk:
            recommendations["immediate_actions"].append(
                "ESCALATE: Multiple critical failures detected - initiate incident response"
            )

        # Critical agents
        critical_agents = [h for h in agent_healths if h.status == "CRITICAL"]
        for agent in critical_agents:
            recommendations["immediate_actions"].append(
                f"Restart or investigate {agent.agent_name}: {', '.join(agent.issues)}"
            )

        # Warning agents
        warning_agents = [h for h in agent_healths if h.status == "WARNING"]
        for agent in warning_agents:
            recommendations["monitoring"].append(
                f"Monitor {agent.agent_name} closely: {', '.join(agent.issues)}"
            )

        # Unreachable agents
        unreachable = [h for h in agent_healths if not h.reachable]
        for agent in unreachable:
            recommendations["investigation"].append(
                f"Check network/deployment for {agent.agent_name}"
            )

        # Unknown status agents
        unknown = [h for h in agent_healths if h.status == "UNKNOWN" and h.reachable]
        if unknown:
            recommendations["investigation"].append(
                f"Verify integration for idle agents: {', '.join(h.agent_name for h in unknown)}"
            )

        return recommendations

    async def _check_agent_reachability(
            self,
            agent_name: str,
            url: str
    ) -> bool:
        """
        Check if agent is reachable via HTTP

        Returns True if agent responds, False otherwise
        """
        try:
            async with httpx.AsyncClient(timeout=self.HTTP_TIMEOUT) as client:
                resp = await client.get(url)
                return resp.status_code == 200
        except Exception as e:
            logger.warning(f"Agent {agent_name} unreachable: {str(e)}")
            return False

    @log_method
    @metric_counter("health_monitor")
    async def check_health(
            self,
            agents: Dict[str, str],
            metrics: Optional[Dict[str, Dict[str, int]]] = None
    ) -> Dict[str, Any]:
        """
        Comprehensive health check with metrics integration

        Proper sequential reasoning: collect → classify → assess → recommend → analyze
        """
        reasoning: List[ReasoningStep] = []

        # Step 1: Request received
        self._next_step(reasoning, "Health check request received",
                        input_data={
                            "agents_to_check": list(agents.keys()),
                            "metrics_provided": bool(metrics)
                        })

        # Step 2: Collect metrics (if not provided)
        if metrics is None:
            # In production, call MetricsAgent here
            # For now, use mock data
            metrics = {
                "planner": {"tasks_processed": 45, "errors": 2},
                "risks": {"tasks_processed": 38, "errors": 1},
                "progress": {"tasks_processed": 30, "errors": 0},
                "digest": {"tasks_processed": 25, "errors": 0},
                "image": {"tasks_processed": 15, "errors": 3},
                "health_monitor": {"tasks_processed": 60, "errors": 0},
                "metrics_agent": {"tasks_processed": 10, "errors": 0}
            }

            self._next_step(reasoning, "Collected metrics from internal store",
                            output_data={
                                "metrics_source": "mock",
                                "agents_with_metrics": len(metrics)
                            })
        else:
            self._next_step(reasoning, "Using provided metrics",
                            output_data={
                                "metrics_source": "external",
                                "agents_with_metrics": len(metrics)
                            })

        # Step 3: Check reachability for all agents
        reachability = {}
        for agent_name, url in agents.items():
            reachable = await self._check_agent_reachability(agent_name, url)
            reachability[agent_name] = reachable

        self._next_step(reasoning, "Checked agent reachability via HTTP",
                        output_data={
                            "agents_checked": len(reachability),
                            "reachable": sum(1 for r in reachability.values() if r),
                            "unreachable": sum(1 for r in reachability.values() if not r)
                        })

        # Step 4 - Calculate error rates and classify health
        agent_healths = []
        for agent_name in agents.keys():
            agent_metrics = metrics.get(agent_name, {"tasks_processed": 0, "errors": 0})
            reachable = reachability.get(agent_name, False)

            health = self._classify_agent_health(
                agent_name=agent_name,
                tasks_processed=agent_metrics.get("tasks_processed", 0),
                errors=agent_metrics.get("errors", 0),
                reachable=reachable
            )
            agent_healths.append(health)

        health_summary = {
            "ok": sum(1 for h in agent_healths if h.status == "OK"),
            "warning": sum(1 for h in agent_healths if h.status == "WARNING"),
            "critical": sum(1 for h in agent_healths if h.status == "CRITICAL"),
            "unknown": sum(1 for h in agent_healths if h.status == "UNKNOWN")
        }

        self._next_step(reasoning, "Classified health status for all agents",
                        output_data=health_summary)

        # Step 5 - Assess overall system health
        system_health = self._assess_system_health(agent_healths)

        self._next_step(reasoning, "Assessed overall system health",
                        output_data={
                            "overall_status": system_health.overall_status,
                            "systemic_risk": system_health.systemic_risk
                        })

        #  Step 6 - Generate recommendations
        recommendations = self._generate_recommendations(agent_healths, system_health)

        self._next_step(reasoning, "Generated health recommendations",
                        output_data={
                            "immediate_actions": len(recommendations["immediate_actions"]),
                            "monitoring_items": len(recommendations["monitoring"]),
                            "investigations": len(recommendations["investigation"])
                        })

        #  Step 7 - Optional AI analysis (only if issues detected)
        ai_analysis = None
        if system_health.overall_status != "HEALTHY":
            # Prepare structured summary for LLM
            summary = f"""System Health Summary:
- Overall Status: {system_health.overall_status}
- Critical Agents: {system_health.critical_agents}
- Warning Agents: {system_health.warning_agents}
- Systemic Risk: {system_health.systemic_risk}

Critical Issues:
{chr(10).join(f'- {h.agent_name}: {", ".join(h.issues)}' for h in agent_healths if h.status in ['CRITICAL', 'WARNING'])}

Based on this data, identify:
1. Most likely root causes
2. Potential cascading failures
3. Priority order for remediation

Keep analysis under 200 words."""

            try:
                ai_analysis = await self.llm.chat(summary)

                self._next_step(reasoning, "Generated AI-powered root cause analysis",
                                output_data={
                                    "analysis_length": len(ai_analysis),
                                    "llm_used": True
                                })
            except Exception as e:
                logger.error("AI analysis failed", extra={"error": str(e)})

                self._next_step(reasoning, "AI analysis failed - skipped",
                                output_data={
                                    "error": str(e),
                                    "llm_used": False
                                })

        # Step 8 - Health check completed
        self._next_step(reasoning, "Health check completed",
                        output_data={
                            "total_agents": len(agent_healths),
                            "overall_status": system_health.overall_status,
                            "recommendations_generated": sum(len(v) for v in recommendations.values())
                        })

        logger.info("Health check completed",
                    extra={
                        "agents": len(agent_healths),
                        "status": system_health.overall_status
                    })

        return {
            "system_health": asdict(system_health),
            "agent_healths": [asdict(h) for h in agent_healths],
            "recommendations": recommendations,  # Actionable decisions
            "ai_analysis": ai_analysis,  # Optional LLM insights
            "reasoning": reasoning
        }

    @log_method
    @metric_counter("health_monitor")
    async def diagnose_agent(
            self,
            agent_name: str,
            metrics: Optional[Dict[str, int]] = None
    ) -> Dict[str, Any]:
        """
        Deep diagnostics for a specific agent

        Focused analysis with detailed recommendations
        """
        reasoning: List[ReasoningStep] = []

        self._next_step(reasoning, "Agent diagnostics requested",
                        input_data={"agent_name": agent_name})

        # Get agent metrics
        if metrics is None:
            # Mock for demo
            all_metrics = {
                "planner": {"tasks_processed": 45, "errors": 2},
                "image": {"tasks_processed": 15, "errors": 3}
            }
            metrics = all_metrics.get(agent_name, {"tasks_processed": 0, "errors": 0})

        self._next_step(reasoning, "Collected agent metrics",
                        output_data=metrics)

        # Classify health
        health = self._classify_agent_health(
            agent_name=agent_name,
            tasks_processed=metrics.get("tasks_processed", 0),
            errors=metrics.get("errors", 0)
        )

        self._next_step(reasoning, "Classified agent health",
                        output_data={
                            "status": health.status,
                            "error_rate": f"{health.error_rate * 100:.1f}%"
                        })

        # Generate specific recommendations
        recommendations = []
        if health.status == "CRITICAL":
            recommendations.append("IMMEDIATE: Restart agent or roll back recent changes")
            recommendations.append("Check error logs for stack traces")
            recommendations.append("Verify external dependencies (DB, APIs)")
        elif health.status == "WARNING":
            recommendations.append("Increase monitoring frequency")
            recommendations.append("Review recent deployments or config changes")
            recommendations.append("Check for gradual resource exhaustion")
        elif health.status == "UNKNOWN":
            recommendations.append("Verify agent is receiving requests")
            recommendations.append("Check routing and load balancer configuration")
        else:
            recommendations.append("Agent operating normally - maintain current monitoring")

        self._next_step(reasoning, "Generated agent-specific recommendations",
                        output_data={"recommendations_count": len(recommendations)})

        self._next_step(reasoning, "Agent diagnostics completed",
                        output_data={"total_steps": len(reasoning)})

        return {
            "agent_name": agent_name,
            "health": asdict(health),
            "recommendations": recommendations,
            "reasoning": reasoning
        }

    @log_method
    @metric_counter("health_monitor")
    async def get_system_status(self) -> Dict[str, Any]:
        """
        Quick system status overview

        Lightweight check without full analysis
        """
        reasoning: List[ReasoningStep] = []

        self._next_step(reasoning, "System status check initiated",
                        input_data={"mode": "lightweight"})

        # Get metrics
        metrics = {
            "planner": {"tasks_processed": 45, "errors": 2},
            "risks": {"tasks_processed": 38, "errors": 1},
            "progress": {"tasks_processed": 30, "errors": 0},
            "digest": {"tasks_processed": 25, "errors": 0}
        }

        # Classify health
        agent_healths = [
            self._classify_agent_health(name, data["tasks_processed"], data["errors"])
            for name, data in metrics.items()
        ]

        system_health = self._assess_system_health(agent_healths)

        self._next_step(reasoning, "System status assessed",
                        output_data={
                            "overall_status": system_health.overall_status,
                            "agents_checked": len(agent_healths)
                        })

        return {
            "overall_status": system_health.overall_status,
            "ok_agents": system_health.ok_agents,
            "warning_agents": system_health.warning_agents,
            "critical_agents": system_health.critical_agents,
            "systemic_risk": system_health.systemic_risk,
            "reasoning": reasoning
        }