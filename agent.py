import subprocess
from typing import TypedDict, Optional, Literal, List
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END
from rag import HybridRAG

# 1. State Definition
class AgentState(TypedDict):
    error_message: str
    is_complex: bool
    reasoning_mode: str
    retrieved_runbook: str
    diagnosis_plan: str
    suggested_command: str
    is_risky: bool
    command_output: Optional[str]

# 2. Centralized Local Model Client (AMD RX 7800 XT via LM Studio)
local_llm = ChatOpenAI(
    base_url="http://localhost:1234/v1",
    api_key="not-needed",
    model="default",
    temperature=0.1,
    extra_body={"model": ""}
)

# Initialize RAG Engine
rag_engine = HybridRAG()

# 3. Router & Triage Nodes
def evaluate_complexity(state: AgentState) -> dict:
    err = state["error_message"].lower()
    complex_signals = ["deadlock", "distributed", "corrupt", "kernel", "out of memory", "panic"]
    is_complex = any(sig in err for sig in complex_signals) or len(err.split()) > 30
    return {"is_complex": is_complex}

def retrieve_knowledge(state: AgentState) -> dict:
    """Node: Retrieves and reranks matching incident runbooks."""
    print("\n[Node: retrieve_knowledge] Running Hybrid Search & Cross-Encoder...")
    matched = rag_engine.retrieve_and_rerank(state["error_message"], top_k=1)
    if matched:
        runbook = f"Runbook: {matched[0]['title']}\nInstructions: {matched[0]['content']}"
        print(f" -> Found: {matched[0]['title']}")
    else:
        runbook = "No specific runbook found. Proceed with standard diagnostics."
    return {"retrieved_runbook": runbook}

def route_decision(state: AgentState) -> Literal["fast_triage", "deep_reasoning"]:
    if state["is_complex"]:
        print("🔀 Route: High complexity issue -> Activating Deep Reasoning Mode")
        return "deep_reasoning"
    print("🔀 Route: Routine issue -> Activating Fast Triage Mode")
    return "fast_triage"

# 4. Diagnostic Nodes (Grounded in Retrieved Runbook)
def fast_triage(state: AgentState) -> dict:
    print("[Node: fast_triage] Formulating quick diagnosis with runbook guidance...")
    prompt = [
        SystemMessage(content=(
            "You are SentinelFlow in FAST-TRIAGE mode. Use the provided runbook context to solve the error.\n"
            f"{state['retrieved_runbook']}\n"
            "Provide a 2-sentence cause analysis and ONE single-line Windows PowerShell command to inspect or resolve it."
        )),
        HumanMessage(content=f"Error: {state['error_message']}")
    ]
    res = local_llm.invoke(prompt)
    return {"diagnosis_plan": res.content, "reasoning_mode": "Fast Triage (Local RAG)"}

def deep_reasoning(state: AgentState) -> dict:
    print("[Node: deep_reasoning] Formulating chain-of-thought analysis with runbook guidance...")
    prompt = [
        SystemMessage(content=(
            "You are SentinelFlow in DEEP REASONING mode. Use the provided runbook context to solve the error.\n"
            f"{state['retrieved_runbook']}\n"
            "Analyze systematically:\n"
            "1. Concurrency / State Invalidation Analysis\n"
            "2. Root Cause Hypothesis\n"
            "3. Single-line Windows PowerShell command to inspect or resolve the system state."
        )),
        HumanMessage(content=f"Complex Failure: {state['error_message']}")
    ]
    res = local_llm.invoke(prompt)
    return {"diagnosis_plan": res.content, "reasoning_mode": "Deep Chain-of-Thought (Local RAG)"}

# 5. Extraction & Execution Node (With HITL Guardrail)
def extract_and_execute(state: AgentState) -> dict:
    extract_prompt = [
        SystemMessage(content=(
            "Extract ONE executable Windows PowerShell command from this text. "
            "Do not use placeholders like '<PID>' or '<process_name>'. "
            "If an exact ID is unknown, output a generic inspection command like: "
            "'Get-Process | Sort-Object CPU -Descending | Select-Object -First 5'. "
            "Return ONLY the raw one-line command without markdown or tags:"
        )),
        HumanMessage(content=state["diagnosis_plan"])
    ]
    raw_cmd = local_llm.invoke(extract_prompt).content.strip().replace("`", "")
    
    lines = [line.strip() for line in raw_cmd.splitlines() if line.strip()]
    command = lines[-1] if lines else "Get-Process | Select-Object -First 5"
    if command.lower().startswith("powershell"):
        command = command[10:].strip()

    if "<" in command or ">" in command:
        command = "Get-Process | Sort-Object CPU -Descending | Select-Object -First 5"

    risky_keywords = ["restart", "stop", "kill", "remove", "delete", "rm", "net stop", "sc stop", "start-service"]
    is_risky = any(kw in command.lower() for kw in risky_keywords)

    print(f"\n[Reasoning Profile]: {state['reasoning_mode']}")
    print(f"[Sanitized Command]: {command}")
    print(f"[Risk Classification]: {'RISKY (Requires Human Approval)' if is_risky else 'SAFE (Read-Only)'}")

    if is_risky:
        choice = input("⚠️  Action tagged as RISKY. Run command? (y/n): ").strip().lower()
        if choice != "y":
            return {"suggested_command": command, "is_risky": is_risky, "command_output": "Cancelled by operator."}

    print("⚡ Executing command...")
    try:
        proc = subprocess.run(["powershell", "-Command", command], capture_output=True, text=True, timeout=10)
        output = proc.stdout if proc.stdout else proc.stderr
        print(f"\n[Execution Output]:\n{output.strip()}")
        return {"suggested_command": command, "is_risky": is_risky, "command_output": output.strip()}
    except Exception as e:
        print(f"\n[Execution Failed]: {str(e)}")
        return {"suggested_command": command, "is_risky": is_risky, "command_output": str(e)}

# 6. Build the Connected Graph
builder = StateGraph(AgentState)

builder.add_node("evaluate", evaluate_complexity)
builder.add_node("retrieve", retrieve_knowledge)
builder.add_node("fast_triage", fast_triage)
builder.add_node("deep_reasoning", deep_reasoning)
builder.add_node("execute", extract_and_execute)

builder.add_edge(START, "evaluate")
builder.add_edge("evaluate", "retrieve")
builder.add_conditional_edges("retrieve", route_decision)
builder.add_edge("fast_triage", "execute")
builder.add_edge("deep_reasoning", "execute")
builder.add_edge("execute", END)

agent = builder.compile()

# 7. Test Run (Routine MySQL error to test RAG grounding)
if __name__ == "__main__":
    test_incident = "OperationalError 10061: Target machine actively refused connection on port 3306."
    print(f"Submitting Incident:\n{test_incident}")
    agent.invoke({"error_message": test_incident})