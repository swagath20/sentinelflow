import streamlit as st
import subprocess
from agent import agent

# Page Configuration
st.set_page_config(
    page_title="SentinelFlow | SRE Incident Deck",
    page_icon="⚡",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom Design System
st.markdown("""
<style>
    /* Global Styles */
    @import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');
    
    html, body, [class*="css"] {
        font-family: 'Inter', sans-serif;
    }
    
    code, pre {
        font-family: 'JetBrains Mono', monospace !important;
    }

    /* Cards */
    .card {
        background-color: #161b22;
        border: 1px solid #30363d;
        border-radius: 8px;
        padding: 18px 20px;
        margin-bottom: 16px;
    }
    
    .card-title {
        color: #8b949e;
        font-size: 0.8rem;
        font-weight: 600;
        text-transform: uppercase;
        letter-spacing: 0.05em;
        margin-bottom: 8px;
    }
    
    .status-badge {
        display: inline-block;
        padding: 4px 10px;
        border-radius: 9999px;
        font-size: 0.75rem;
        font-weight: 600;
        letter-spacing: 0.04em;
    }
    
    .badge-safe {
        background-color: rgba(35, 134, 54, 0.2);
        color: #3fb950;
        border: 1px solid rgba(63, 185, 80, 0.4);
    }
    
    .badge-risky {
        background-color: rgba(218, 54, 51, 0.2);
        color: #f85149;
        border: 1px solid rgba(248, 81, 73, 0.4);
    }
    
    .badge-mode {
        background-color: rgba(56, 139, 253, 0.15);
        color: #58a6ff;
        border: 1px solid rgba(88, 166, 255, 0.4);
    }
</style>
""", unsafe_allow_html=True)

# Sidebar
with st.sidebar:
    st.markdown("### ⚡ SentinelFlow")
    st.caption("Autonomous Incident Command Center")
    st.divider()
    
    st.markdown("**Engine Specifications**")
    st.markdown("""
    * **Runtime:** Local ROCm (RX 7800 XT)
    * **Model:** Qwen2.5-Coder-7B
    * **Vector DB:** Qdrant (In-Memory)
    * **Reranker:** ms-marco-MiniLM-L-6-v2
    * **State Engine:** LangGraph
    * **Guardrail:** HITL Approval Wall
    """)
    st.divider()
    st.success("● Cluster Online & Secure (0 API Costs)")

# Main Header
st.title("Incident Response Dashboard")
st.markdown("Automated root-cause triage, runbook fusion, and safe command execution.")

# Input Panel
with st.container():
    tab_text, tab_file = st.tabs(["Traceback Input", "Log File Upload"])
    
    input_type = "text"
    raw_input = ""

    with tab_text:
        text_error = st.text_area(
            "Incident Trace / Error Message",
            value="OperationalError 10061: Target machine actively refused connection on port 3306.",
            height=100,
            placeholder="Paste stack traces or terminal outputs here..."
        )
        if text_error:
            raw_input = text_error
            input_type = "text"

    with tab_file:
        uploaded_file = st.file_uploader("Upload Incident Log (.log, .txt)", type=["log", "txt"])
        if uploaded_file:
            temp_path = "uploaded_incident.log"
            with open(temp_path, "wb") as f:
                f.write(uploaded_file.getbuffer())
            raw_input = temp_path
            input_type = "log_file"
            st.info(f"Target file attached: `{uploaded_file.name}`")

    trigger = st.button("🚀 Analyze Incident & Plan Mitigation", type="primary", use_container_width=True)

if trigger:
    with st.spinner("Traversing LangGraph state machine..."):
        payload = {"input_type": input_type, "raw_input": raw_input}
        st.session_state["last_state"] = agent.invoke(payload)

# Results Surface
if "last_state" in st.session_state:
    state = st.session_state["last_state"]
    st.markdown("---")
    
    # Overview Metrics Row
    m1, m2, m3 = st.columns(3)
    with m1:
        st.markdown(f"""
        <div class="card">
            <div class="card-title">Orchestration Path</div>
            <span class="status-badge badge-mode">{state.get("reasoning_mode", "Standard Triage")}</span>
        </div>
        """, unsafe_allow_html=True)
    with m2:
        is_risky = state.get("is_risky", False)
        badge_class = "badge-risky" if is_risky else "badge-safe"
        badge_text = "MUTATING / RISKY" if is_risky else "READ-ONLY / SAFE"
        st.markdown(f"""
        <div class="card">
            <div class="card-title">Risk Assessment</div>
            <span class="status-badge {badge_class}">{badge_text}</span>
        </div>
        """, unsafe_allow_html=True)
    with m3:
        st.markdown(f"""
        <div class="card">
            <div class="card-title">Ingestion Format</div>
            <span class="status-badge badge-mode">{state.get("input_type", "Text String").upper()}</span>
        </div>
        """, unsafe_allow_html=True)

    # Diagnostic & Runbook Columns
    col_runbook, col_diag = st.columns([1, 1])

    with col_runbook:
        st.markdown("#### Retrieved Runbook Grounding")
        st.markdown(f"""
        <div class="card">
            <div class="card-title">Matched Knowledge Article</div>
            <p style="font-size: 0.95rem; line-height: 1.5;">{state.get("retrieved_runbook", "No runbook found.")}</p>
        </div>
        """, unsafe_allow_html=True)

    with col_diag:
        st.markdown("#### Automated System Diagnosis")
        st.markdown(f"""
        <div class="card">
            <div class="card-title">Root Cause Analysis</div>
            <div style="font-size: 0.95rem; line-height: 1.5;">{state.get("diagnosis_plan", "No plan created.")}</div>
        </div>
        """, unsafe_allow_html=True)

    # Action / Remediation Zone
    st.markdown("#### Remediation & Inspection Plan")
    cmd = state.get("suggested_command", "Get-Process | Select-Object -First 5")
    
    st.code(cmd, language="powershell")

    if is_risky:
        st.error("⚠️ **Operator Intervention Required:** This command changes system states. Execution paused.")
        if st.button("Authorize Execution", type="primary"):
            with st.spinner("Dispatching authorized command to host shell..."):
                proc = subprocess.run(["powershell", "-Command", cmd], capture_output=True, text=True, timeout=10)
                output = proc.stdout if proc.stdout else proc.stderr
                st.markdown("**Host Response:**")
                st.code(output.strip() if output.strip() else "[Command ran successfully. Empty stdout]")
    else:
        st.markdown("**Host Telemetry Output:**")
        cmd_out = state.get("command_output", "")
        if cmd_out:
            st.code(cmd_out)
        else:
            st.code("[Inspection complete. No errors or empty response returned.]")