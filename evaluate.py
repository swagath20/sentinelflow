import json
from rag import HybridRAG
from langchain_openai import ChatOpenAI
from langchain_core.messages import SystemMessage, HumanMessage

# Initialize local Qwen judge running on your RX 7800 XT
judge_llm = ChatOpenAI(
    base_url="http://localhost:1234/v1",
    api_key="not-needed",
    model="default",
    temperature=0.0,
    extra_body={"model": ""}
)

rag_engine = HybridRAG()

# Benchmark evaluation dataset
BENCHMARK_CASES = [
    {
        "query": "Error 10061: Target machine actively refused connection on port 3306",
        "expected_topic": "MySQL Connection Refused (10061)",
        "expected_command_fragment": "netstat"
    },
    {
        "query": "Kernel lock wait timeout exceeded during distributed table synchronization",
        "expected_topic": "Distributed Transaction Deadlock",
        "expected_command_fragment": "Get-Process"
    },
    {
        "query": "Kernel OOM occurs: system memory allocation exceeds swap limits",
        "expected_topic": "Out of Memory (OOM) Killer Invocation",
        "expected_command_fragment": "Get-Process"
    }
]

def score_context_relevance(query: str, retrieved_title: str) -> float:
    """Evaluates if the hybrid RAG engine fetched the right document."""
    prompt = [
        SystemMessage(content=(
            "You are an LLMOps evaluator. Given an incident query and the title of a retrieved runbook, "
            "determine if the runbook is relevant to the issue. Output ONLY a floating point score between 0.0 and 1.0."
        )),
        HumanMessage(content=f"Query: {query}\nRetrieved Runbook: {retrieved_title}")
    ]
    raw = judge_llm.invoke(prompt).content.strip()
    try:
        # Extract number if wrapped in text
        score = float([token for token in raw.split() if token.replace('.', '', 1).isdigit()][0])
        return min(max(score, 0.0), 1.0)
    except Exception:
        return 1.0 if retrieved_title.lower() in query.lower() else 0.5

def run_evaluation():
    print("=" * 55)
    print("      SENTINELFLOW LLMOps EVALUATION BENCHMARK       ")
    print("=" * 55)
    
    total_cases = len(BENCHMARK_CASES)
    passed_retrievals = 0
    relevance_scores = []

    for idx, test in enumerate(BENCHMARK_CASES, 1):
        print(f"\n[Case {idx}/{total_cases}] Query: {test['query']}")
        
        # 1. Test Retrieval
        hits = rag_engine.retrieve_and_rerank(test["query"], top_k=1)
        retrieved = hits[0] if hits else {"title": "None", "content": ""}
        
        retrieval_ok = test["expected_topic"].lower() in retrieved["title"].lower()
        if retrieval_ok:
            passed_retrievals += 1
            print(f"  ✓ Retrieval: PASS (Matched: {retrieved['title']})")
        else:
            print(f"  ✗ Retrieval: FAIL (Expected: {test['expected_topic']}, Got: {retrieved['title']})")

        # 2. Score Context Relevance via Local LLM Judge
        rel_score = score_context_relevance(test["query"], retrieved["title"])
        relevance_scores.append(rel_score)
        print(f"  • LLM Judge Relevance Score: {rel_score:.2f}")

    # Summary Metrics
    hit_rate = (passed_retrievals / total_cases) * 100
    avg_relevance = sum(relevance_scores) / len(relevance_scores)

    print("\n" + "=" * 55)
    print("                 BENCHMARK SUMMARY                  ")
    print("=" * 55)
    print(f"Total Test Cases:            {total_cases}")
    print(f"Retrieval Top-1 Hit Rate:    {hit_rate:.1f}%")
    print(f"Mean Context Relevance:      {avg_relevance:.2f} / 1.00")
    print("=" * 55)

if __name__ == "__main__":
    run_evaluation()