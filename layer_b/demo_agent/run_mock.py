# layer_b/demo_agent/run_mock.py
"""
Runs the ENTIRE Layer B pipeline locally — LangGraph-style agent,
correlator, PostgreSQL writes — using MockLLM. Zero GPU, zero SGLang,
zero network calls. This is your proof that Layer B is bug-free
before you ever touch the rented GPU.
"""
import sys, os, psycopg2

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "sdk"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "storage"))

from correlator import AgentSessionCorrelator
from repository import ObservabilityRepository
from mock_llm import MockLLM
from agents import run_financial_compliance_agent

PG_DSN = "postgresql://researcher:hackathon2026@localhost:5433/agent_observability"

def main():
    pg = psycopg2.connect(PG_DSN)
    pg.autocommit = True

    correlator = AgentSessionCorrelator(pg)
    repo       = ObservabilityRepository(pg)
    llm        = MockLLM()

    test_inputs = [f"Review transaction TXN-{i:03d} for regulatory compliance"
                   for i in range(5)]

    for i, test_input in enumerate(test_inputs):
        session_id = correlator.start_session(
            parent_goal=test_input, agent_type="financial_compliance")
        result = run_financial_compliance_agent(llm, correlator, test_input)
        correlator.end_session(result.get("decision", "UNKNOWN"))
        print(f"Run {i+1}/5 — session {session_id[:8]}... decision: {result.get('decision')}")

    print("\n--- Verifying data landed in PostgreSQL ---")
    sessions = repo.get_all_sessions()
    print(f"Total sessions in DB: {len(sessions)}")
    assert len(sessions) >= 5, "Expected at least 5 sessions"

    last_session_id = sessions[0]["session_id"]
    events = repo.get_session_intent_events(last_session_id)
    print(f"Intent events for last session: {len(events)}")
    assert len(events) == 2, "Expected exactly 2 intent_events per session"

    print("\n✅ LAYER B FULL PIPELINE WORKS — safe to proceed")

if __name__ == "__main__":
    main()