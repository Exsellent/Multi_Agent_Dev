from agents.health_monitor.agent import HealthMonitorAgent

agent = HealthMonitorAgent()
app = agent.app


@app.get("/")
async def root():
    return {
        "message": "Multi-agent-devops-assistant Agent is running!",
        "agent": agent.name,
        "available_tools": list(agent.tools.keys()),
        "docs": "/docs"
    }
