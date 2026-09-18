import subprocess
from typing import TypedDict, Optional, Literal
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage
from langgraph.graph import StateGraph, START, END

# 1. State Definition
class AgentState(TypedDict):
    error_message: str
    is_complex: bool
    reasoning_mode: str
    diagnosis_plan: str
    suggested_command: str
    is_risky: bool
    command_output: Optional[str]

# 2. Centralized Local Client (Runs exclusively on your RX 7800 XT)
local_llm = ChatOpenAI(
    base_url="http://localhost:1234/v1",
    api_key="not-needed",
    model="default",
    temperature=0.1,
    extra_body={"model": ""}  # Tells LM Studio to route to whatever model is currently loaded
)

# 3. Router Node
def evaluate_complexity(state: AgentState) -> dict:
    """Evaluates whether an error requires fast triage or deep architectural reasoning."""
    err = state["error_message"].lower()
    complex_signals = ["deadlock", "distributed", "corrupt", "kernel", "out of memory", "panic"]
    is_complex = any(sig in err for sig in complex_signals) or len(err.split()) > 30
    return {"is_complex": is_complex}

def route_decision(state: AgentState) -> Literal["fast_triage", "deep_reasoning"]:
    if state["is_complex"]:
        print("\n🔀 Route: High complexity issue -> Activating Deep Reasoning Mode")
        return "deep_reasoning"
    print("\n🔀 Route: Standard issue -> Activating Fast Triage Mode")
    return "fast_triage"

# 4. Diagnostic Nodes (Locally Served)
def fast_triage(state: AgentState) -> dict:
    """Standard, concise diagnosis for routine bugs."""
    print("[Node: fast_triage] Executing standard analysis on local GPU...")
    prompt = [
        SystemMessage(content=(
            "You are SentinelFlow in FAST-TRIAGE mode. "
            "Provide a 2-sentence cause analysis and exactly ONE single-line Windows PowerShell command to inspect it."
        )),
        HumanMessage(content=f"Error: {state['error_message']}")
    ]
    res = local_llm.invoke(prompt)
    return {"diagnosis_plan": res.content, "reasoning_mode": "Fast Triage (Local)"}

def deep_reasoning(state: AgentState) -> dict:
    """Chain-of-thought, in-depth root-cause analysis for complex failures."""
    print("[Node: deep_reasoning] Executing multi-step root-cause analysis on local GPU...")
    prompt = [
        SystemMessage(content=(
            "You are SentinelFlow in DEEP REASONING mode. Analyze the failure systematically:\n"
            "1. Concurrency / State Invalidation Analysis\n"
            "2. Root Cause Hypothesis\n"
            "3. Single-line Windows PowerShell command to inspect or resolve the system state."
        )),
        HumanMessage(content=f"Complex Failure: {state['error_message']}")
    ]
    res = local_llm.invoke(prompt)
    return {"diagnosis_plan": res.content, "reasoning_mode": "Deep Chain-of-Thought (Local)"}

# 5. Extraction & Execution Node (With HITL Guardrail)
def extract_and_execute(state: AgentState) -> dict:
    extract_prompt = [
        SystemMessage(content=(
            "Extract ONE executable Windows PowerShell command from this text. "
            "IMPORTANT: Do not use placeholders like '<PID>' or '<process_name>'. "
            "If an exact ID is unknown, write a generic inspection command like: "
            "'Get-Process | Sort-Object CPU -Descending | Select-Object -First 5'. "
            "Return ONLY the raw one-line command without markdown codeblocks or tags:"
        )),
        HumanMessage(content=state["diagnosis_plan"])
    ]
    raw_cmd = local_llm.invoke(extract_prompt).content.strip().replace("`", "")
    
    # Strip leading shell names if present
    lines = [line.strip() for line in raw_cmd.splitlines() if line.strip()]
    command = lines[-1] if lines else "Get-Process | Select-Object -First 5"
    if command.lower().startswith("powershell"):
        command = command[10:].strip()

    # If the model still generated a placeholder bracket, swap to safe fallback
    if "<" in command or ">" in command:
        command = "Get-Process | Sort-Object CPU -Descending | Select-Object -First 5"

    risky_keywords = ["restart", "stop", "kill", "remove", "delete", "rm", "net stop", "sc stop"]
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
# 6. Build the Graph
builder = StateGraph(AgentState)

builder.add_node("evaluate", evaluate_complexity)
builder.add_node("fast_triage", fast_triage)
builder.add_node("deep_reasoning", deep_reasoning)
builder.add_node("execute", extract_and_execute)

builder.add_edge(START, "evaluate")
builder.add_conditional_edges("evaluate", route_decision)
builder.add_edge("fast_triage", "execute")
builder.add_edge("deep_reasoning", "execute")
builder.add_edge("execute", END)

agent = builder.compile()

# 7. Test Run with a Complex Deadlock Error
if __name__ == "__main__":
    complex_test = (
        "Fatal deadlock encountered in transaction worker 0x8F: "
        "kernel lock wait timeout exceeded during distributed table synchronization."
    )
    print(f"Input Error:\n{complex_test}")
    agent.invoke({"error_message": complex_test})