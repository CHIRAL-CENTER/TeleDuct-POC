# layer_b/storage/repository.py
import psycopg2.extras

class ObservabilityRepository:
    def __init__(self, pg_conn):
        self.pg  = pg_conn
        self.cur = self.pg.cursor(cursor_factory=psycopg2.extras.RealDictCursor)

    def get_fragile_steps(self, session_id):
        self.cur.execute("""
            SELECT step_id, sampling_margin, confidence_label, timestamp_ns
            FROM logit_telemetry
            WHERE session_id = %s AND fragility_flag = true
            ORDER BY timestamp_ns""", (session_id,))
        return self.cur.fetchall()

    def get_all_sessions(self):
        self.cur.execute("SELECT * FROM sessions ORDER BY started_at DESC")
        return self.cur.fetchall()

    def get_session_intent_events(self, session_id):
        self.cur.execute("""
            SELECT * FROM intent_events
            WHERE session_id = %s ORDER BY step_index""", (session_id,))
        return self.cur.fetchall()