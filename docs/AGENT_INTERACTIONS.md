# 🔄 Agent Interaction Diagram

---

# ✅ Final Architecture: 7 Agents

### ✅ Complete List of Agents

| № | Agent                | Port     | Purpose                               |
| - |----------------------|----------|---------------------------------------|
| 1 | PlannerAgent         | 8201     | Task planning, decomposition, Jira    |
| 2 | ProgressAgent        | 8202     | Progress and velocity analysis        |
| 3 | RisksAgent           | 8203     | Risk analysis                         |
| 4 | DigestAgent          | 8204     | Daily / weekly summaries              |
| 5 | ImageAgent           | 8205     | Image / diagram analysis              |
| 6 | HealthMonitorAgent   | 8206     | Health + circuit breaker              |
| 7 | MetricsAgent         | 8207     | Prometheus / business metrics         |

---
# 🔄 Architecture Diagram (7 Agents)

```text
┌────────────────────────────────────────────────────────────────────────────────────────────┐
│                                 n8n Orchestrator                                           │
│                            (Workflow Automation Layer)                                     │
└───────┬───────────┬───────────┬───────────┬───────────┬───────────┬───────────┬────────────┘
        │           │           │           │           │           │           │
   ┌────▼────┐ ┌────▼────┐ ┌────▼────┐ ┌────▼────┐ ┌────▼────┐ ┌────▼────┐ ┌────▼────┐
   │Planner  │ │Progress │ │ Risks   │ │ Digest  │ │ Image   │ │Health   │ │Metrics  │
   │ Agent   │ │ Agent   │ │ Agent   │ │ Agent   │ │ Agent   │ │Monitor  │ │ Agent   │
   │ :8201   │ │ :8202   │ │ :8203   │ │ :8204   │ │ :8205   │ │ :8206   │ │ :8207   │
   └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘ └─────────┘
                                         │
                         ┌───────────────▼───────────────┐
                         │         Shared Layer          │
                         ├───────────────────────────────┤
                         │• MCP Protocol                 │
                         │• LLM Client                   │
                         │• Jira Client                  │
                         │• Error Handler                │
                         │• CircuitBreaker               │
                         │• Metrics Core                 │
                         └───────────────────────────────┘
```
---

# 🧠 Role of Each Agent (Detailed Description)

---

## 1️⃣ Planner Agent (8201)

**Purpose:** Intelligent task decomposition.

### Responsibilities:
* Accepts task description  
* Generates subtasks via LLM  
* Validates response (anti-stub protection)  
* Optionally creates tasks in Jira  
* Returns reasoning chain  

### Used when:
* A task comes from the user  
* GitHub webhook triggers  
* Workflow starts in n8n  

---

## 2️⃣ Progress Agent (8202)

**Purpose:** Project progress analysis.

### Functions:
* Analyze commit messages  
* Calculate velocity from Jira  
* Compute completion rate  
* Classify status (`excellent / good / at_risk / critical`)  

### Typical Metrics:
* Number of tasks  
* Completed / total  
* Completion percentage  
* Progress status  

---

## 3️⃣ Risks Agent (8203)

**Purpose:** Risk analysis of changes and features.

### Analyzes:
* Security risks  
* Performance risks  
* Technical debt  
* Compliance risks  

### Outputs:
* List of risks  
* Impact level  
* Mitigation recommendations  

**Used:**
* Before release  
* After PR  
* During architectural changes  

---

## 4️⃣ Digest Agent (8204)

**Purpose:** Generate concise reports.

### Aggregates:
* Results from other agents  
* Project status  
* Progress  
* Blockers  

### Formats:
* Daily digest  
* Weekly summary  
* Slack / Email text  

---

## 5️⃣ Image Agent (8205)

**Purpose:** Image and diagram analysis.

### Sources:
* Architecture diagrams  
* UI screenshots  
* Infrastructure diagrams  

### Performs:
* Structure analysis  
* Detects architectural issues  
* Provides recommendations  
* Best practices  

(via Vision / Groq / multimodal LLM)

---

## 6️⃣ Health Monitor Agent (8206)

**Purpose:** System health monitoring.

### Checks:
* Agent availability (`/health`)  
* Latency  
* Circuit breaker  
* Errors  

### Outputs:
* Overall system state  
* Status of each agent  
* Recommendations (restart, logs)  

**Runs:**
* Periodically  
* Or on demand  

---

## 7️⃣ Metrics Agent (8207)

**Purpose:** Centralized metrics and observability.

### Provides:
* `/metrics` (Prometheus)  
* System metrics  
* Agent metrics  
* RED metrics  

### Collects:
* Latency  
* Error rate  
* Request count  
* Per-agent statistics  

---

# 🔁 Updated End-to-End Scenario (Full)

```text
GitHub / User Action
        │
        ▼
   n8n Workflow
        │
        ├─▶ PlannerAgent
        │     ├─ LLM → subtasks
        │     └─ Jira issues
        │
        ├─▶ RisksAgent
        │     └─ Risk evaluation
        │
        ├─▶ ImageAgent
        │     └─ Diagram analysis
        │
        ├─▶ ProgressAgent
        │     └─ Velocity + status
        │
        ├─▶ DigestAgent
        │     └─ Final human-readable summary
        │
        ├─▶ MetricsAgent
        │     └─ Collect metrics
        │
        └─▶ HealthMonitor (background)
              ├─ ping agents
              ├─ check breakers
              └─ alerts
```

---

# 🧩 Architectural Logic  
### ✅ SOLID + Micro-agent Design
* Each agent = single responsibility  
* Easy to test  
* Easy to scale  

### ✅ Observability-first
* Metrics separated  
* Health separated  
* Business logic not cluttered with monitoring  

### ✅ Fault Isolation
* Circuit breaker at agent level  
* One agent failure doesn’t crash the system  

### ✅ MCP as Contract
* Unified entry (`/mcp`)  
* Unified format  
* Transparent routing  

---

