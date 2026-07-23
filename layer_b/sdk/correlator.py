# layer_b/sdk/correlator.py
import uuid
from psycopg2.extras import Json

class AgentSessionCorrelator:
    def __init__(self, pg_conn):
        """pg_conn: an already-open psycopg2 connection, autocommit=True"""
        self.pg  = pg_conn
        self.cur = self.pg.cursor()
        self.session_id   = None
        self.step_counter  = 0

    def start_session(self, parent_goal, agent_type):
        self.session_id  = str(uuid.uuid4())
        self.step_counter = 0
        self.cur.execute(
            "INSERT INTO sessions (session_id, parent_goal, agent_type) "
            "VALUES (%s,%s,%s)",
            (self.session_id, parent_goal, agent_type))
        return self.session_id

    def wrap_node(self, node_fn, node_name, available_tools, objective):
        def wrapped(state):
            step_id   = f"{self.session_id}__step_{self.step_counter}"
            intent_id = str(uuid.uuid4())
            result    = node_fn(state)
            self.cur.execute("""INSERT INTO intent_events
                (intent_id, session_id, step_id, step_index, node_name,
                 parent_goal, current_objective, available_tools,
                 selected_action, goal_alignment_check)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (intent_id, self.session_id, step_id, self.step_counter,
                 node_name, state.get("input", ""), objective,
                 Json(available_tools),
                 result.get("selected_action", "unknown"),
                 result.get("alignment", "ALIGNED")))
            self.step_counter += 1
            return result
        return wrapped

    def end_session(self, final_decision):
        self.cur.execute(
            "UPDATE sessions SET ended_at=now(), final_decision=%s, "
            "total_steps=%s WHERE session_id=%s",
            (final_decision, self.step_counter, self.session_id))