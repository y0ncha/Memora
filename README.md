# Interlock
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)
[![Status](https://img.shields.io/badge/status-workshop--project-lightgrey)](#)

**Interlock** turns Jira ticket resolution into an **agentic context compiler** controlled by a **deterministic FSM/graph** and powered by a **structured State Bus**.

Instead of pushing raw dumps of Jira tickets and Confluence pages into a large language model, Interlock compiles the context into a **validated snapshot**: requirements are pinned early, evidence is indexed, claims are grounded, and the final output is a plan that is strictly traceable back to its sources.

---

## **Motivation**

AI workflows for complex tickets often suffer from:
1.  **The Context Tax**: Passing huge raw documents increases costs and latency while reducing accuracy.
2.  **Compounding Hallucinations**: Early mistakes in file paths or assumptions cascade into the final output.
3.  **Non-Deterministic Behavior**: Agents that "improvise" tool use often loop or fail unpredictably.
4.  **Memory Drift**: Requirements get diluted or forgotten as more context is gathered.

Interlock solves this by enforcing **evidence-first reasoning** and **pinned requirements**.

---

## **Core Principles**

-   **Determinism over Improvisation**: A Finite State Machine (FSM) decides the next step, not the LLM. The model proposes structured data; the orchestrator handles routing.
-   **Evidence-First**: The unit of reasoning is an **evidence object** (snippet + locator + provenance), not a full document.
-   **Pinned Requirements**: Acceptance criteria are extracted and "pinned" immediately. Every later step must prove coverage against them.
-   **Traceability**: A structured **State Bus** records every event (tool call, validation, delta), making runs fully replayable and debuggable.

---

## **Architecture**

Interlock separates control from data:

-   **Control Plane**: An FSM/Graph orchestrator that applies guards, budgets, and retry policies.
-   **Data Plane**: Connectors (Jira, Confluence, GitHub, Repo) that fetch and normalize data into evidence.
-   **State Bus**: An append-only event log and a materialized snapshot of the current run.

```mermaid
flowchart LR
  U["User / Trigger"] --> O["FSM/Graph Orchestrator"]
  O <--> SB["State Bus (Snapshot + Events)"]
  O --> T["Tools (Jira, Confluence, GitHub, Repo)"]
  O --> M["LLM (Structured Outputs)"]
  SB --> OUT["Plan + Coverage + Traceability"]
```

### **Execution Phases**

1.  **Phase A - Pin and Gather**: Parse intent, validate scope, and **pin requirements** (immutable).
2.  **Phase B - Compile Evidence**: Fetch sources, chunk them into **evidence objects**, and extract typed entities.
3.  **Phase C - Verify and Plan**: Generate a plan where every step cites specific evidence IDs. Verify coverage against pinned requirements.
4.  **Phase D - Deliver**: Post the grounded plan to Jira, or trigger a human interrupt if unknowns remain.

---

## **Tech Stack**

-   **Runtime**: Python 3.11+
-   **Orchestration**: LangGraph-style deterministic FSM
-   **Validation**: Pydantic schemas for all artifacts (Requirements, Evidence, Plan)
-   **Integration**: MCP-style tool interfaces for Jira, Confluence, and GitHub

---

## **Project Status**

This project is developed as part of an academic workshop. The focus is on **governance, traceability, and deterministic design** for AI-assisted workflows.

See [Implementation Plan](docs/Implementation.md) for the delivery roadmap.

---

## **License**

This project is licensed under the MIT License. See the [LICENSE](LICENSE) file for details.