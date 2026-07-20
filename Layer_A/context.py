# layer_a/context.py
from contextvars import ContextVar

_current_agent_context: ContextVar[dict] = ContextVar(
    'agent_context', default={}
)

def set_agent_context(ctx: dict):
    _current_agent_context.set(ctx)

def get_agent_context() -> dict:
    return _current_agent_context.get()