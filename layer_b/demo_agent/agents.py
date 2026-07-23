# layer_b/demo_agent/agents.py

def run_financial_compliance_agent(llm, correlator, test_input: str):
    """
    Minimal two-step pipeline. Works with MockLLM now,
    and with a real SGLang-backed client later — zero code change,
    only the `llm` object passed in changes.
    """

    def analyze_transaction(state):
        response = llm.invoke(f"Review transaction for compliance: {state['input']}")
        return {
            **state,
            "selected_action": "compliance_check",
            "alignment": "ALIGNED",
            "analysis": response.content,
        }

    def flag_or_approve(state):
        decision = "APPROVE" if "compliant" in state["analysis"].lower() else "FLAG"
        return {**state, "decision": decision, "selected_action": decision.lower()}

    step1 = correlator.wrap_node(
        analyze_transaction, "analyze_transaction",
        available_tools=["compliance_lookup"],
        objective="Determine if transaction is compliant")
    step2 = correlator.wrap_node(
        flag_or_approve, "flag_or_approve",
        available_tools=["flag", "approve"],
        objective="Make final compliance decision")

    state = {"input": test_input}
    state = step1(state)
    state = step2(state)
    return state