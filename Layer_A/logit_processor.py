# layer_a/logit_processor.py
import torch, time
from typing import List
from context import get_agent_context

class ChainOfIntentLogitProcessor:
    def __init__(self, emitter, top_k: int = 10):
        self.emitter = emitter
        self.top_k   = top_k

    def __call__(
        self, logits: torch.Tensor, request_ids: List[str]
    ) -> torch.Tensor:
        probs = torch.softmax(logits, dim=-1)
        topk  = torch.topk(probs, k=self.top_k, dim=-1)

        for i, req_id in enumerate(request_ids):
            top_probs = topk.values[i].tolist()
            top_ids   = topk.indices[i].tolist()
            margin    = top_probs[0] - top_probs[1]
            ctx       = get_agent_context()

            self.emitter.emit_logit_event({
                "event_type":      "logit_capture",
                "timestamp_ns":    time.time_ns(),
                "request_id":      req_id,
                "session_id":      ctx.get("session_id"),
                "step_id":         ctx.get("step_id"),
                "node_name":       ctx.get("node_name"),
                "top_k_token_ids": top_ids,
                "top_k_probs":     top_probs,
                "sampling_margin": margin,
                "fragility_flag":  margin < 0.05,
                "confidence_label": (
                    "HIGH"   if margin > 0.30 else
                    "MEDIUM" if margin > 0.05 else "LOW"),
            })
        return logits  # unchanged — observer only