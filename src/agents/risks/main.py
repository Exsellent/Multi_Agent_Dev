from agents.risks.agent import RisksAgent

agent = RisksAgent()
app = agent.app


@app.get("/")
async def root():
    return {
        "message": "Multi-agent-devops-assistant Agent is running!",
        "agent": agent.name,
        "available_tools": list(agent.tools.keys()),
        "docs": "/docs"
    }
