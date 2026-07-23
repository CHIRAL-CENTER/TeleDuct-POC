# layer_a/test_local_dryrun.py
"""
Validates ALL layer_a logic using CPU-only torch and a stub emitter
that just prints instead of calling real SigNoz/PostgreSQL.
Catches logic bugs (math errors, wrong dict keys, broken imports)
without needing a GPU or any running infra.
"""
import torch, torch.nn as nn

from context import set_agent_context, get_agent_context
from logit_processor import ChainOfIntentLogitProcessor
from moe_capture import MoERoutingCapture, patch_qwen_moe_router
from sglang_scraper import SGLangMetricsScraper

# ── Stub emitter: prints instead of writing to SigNoz/PostgreSQL ──
class StubEmitter:
    def __init__(self):
        self.logit_events  = []
        self.moe_events    = []

    def emit_logit_event(self, d):
        self.logit_events.append(d)
        print(f"[logit_event] margin={d['sampling_margin']:.3f} "
              f"flag={d['fragility_flag']} label={d['confidence_label']}")

    def emit_moe_event(self, d):
        self.moe_events.append(d)
        print(f"[moe_event] layer={d['layer_idx']} "
              f"margin={d['avg_routing_margin']:.3f} "
              f"fragile={d['routing_fragile']} load={d['expert_load']}")

    def emit_hardware_event(self, d): pass
    def emit_sglang_metrics(self, d): pass


def test_context_bridge():
    set_agent_context({"session_id": "s1", "step_id": "st1", "node_name": "n1"})
    ctx = get_agent_context()
    assert ctx["session_id"] == "s1"
    print("✅ context.py — set/get works")


def test_logit_processor():
    emitter = StubEmitter()
    proc = ChainOfIntentLogitProcessor(emitter, top_k=5)

    set_agent_context({"session_id": "s1", "step_id": "st1", "node_name": "n1"})

    batch_size, vocab_size = 2, 100
    fake_logits = torch.randn(batch_size, vocab_size)
    out = proc(fake_logits, request_ids=["req1", "req2"])

    assert torch.equal(out, fake_logits), "Logits must be returned unchanged"
    assert len(emitter.logit_events) == 2, "Expected one event per request"
    for e in emitter.logit_events:
        assert 0 <= e["sampling_margin"] <= 1
        assert e["confidence_label"] in ("HIGH", "MEDIUM", "LOW")
    print("✅ logit_processor.py — math + emission correct")


def test_moe_capture():
    # Build a tiny fake model with a module matching MOE_MODULE_TYPES
    class Qwen2MoeSparseMoeBlock(nn.Module):
        def forward(self, x):
            return x  # dummy — hook fires on this call

    class FakeModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.moe_layer_0 = Qwen2MoeSparseMoeBlock()

    model = FakeModel()
    emitter = StubEmitter()
    set_agent_context({"session_id": "s1", "step_id": "st1", "node_name": "n1"})

    capture = MoERoutingCapture(model, emitter)

    # Manually attach fake router logits (normally SGLang would set this)
    num_tokens, num_experts = 4, 8
    model.moe_layer_0.last_router_logits = torch.randn(num_tokens, num_experts)

    # Trigger the forward hook
    _ = model.moe_layer_0(torch.randn(num_tokens, 16))

    assert len(emitter.moe_events) == 1, "Expected exactly one MoE event"
    e = emitter.moe_events[0]
    assert e["num_experts_total"] == 8
    assert e["experts_per_token"] == 4
    assert 0 <= e["avg_routing_margin"] <= 1
    print("✅ moe_capture.py — hook registration + math correct")

    capture.remove_hooks if hasattr(capture, "remove_hooks") else None


def test_patch_qwen_router():
    class FakeGateModel(nn.Module):
        def __init__(self):
            super().__init__()
            self.gate = nn.Linear(16, 8)

    model = FakeGateModel()
    patched_model = patch_qwen_moe_router(model)
    _ = patched_model.gate(torch.randn(4, 16))
    assert hasattr(patched_model.gate, "last_router_logits"), \
        "Patch should attach last_router_logits after forward call"
    print("✅ moe_capture.py — patch_qwen_moe_router works")


def test_sglang_scraper_parsing():
    scraper = SGLangMetricsScraper(emitter=None)  # only testing _parse, no network
    fake_prometheus_text = """
# HELP sglang_gen_throughput tokens/sec
sglang_gen_throughput 42.7
sglang_num_queue_reqs 3
sglang_num_running_reqs 1
sglang_time_to_first_token_seconds 0.083
sglang_token_usage 0.61
"""
    parsed = scraper._parse(fake_prometheus_text)
    assert parsed["sglang_gen_throughput"] == 42.7
    assert parsed["sglang_num_queue_reqs"] == 3
    print("✅ sglang_scraper.py — Prometheus text parsing correct")


def test_gpu_poller_import_only():
    # Cannot call pynvml.nvmlInit() on a Mac (no NVIDIA GPU) —
    # this only proves the file has no syntax/import errors.
    import gpu_poller  # noqa: F401
    print("✅ gpu_poller.py — imports cleanly (functional test requires real GPU)")


if __name__ == "__main__":
    test_context_bridge()
    test_logit_processor()
    test_moe_capture()
    test_patch_qwen_router()
    test_sglang_scraper_parsing()
    test_gpu_poller_import_only()
    print("\n✅✅✅ ALL LAYER A LOGIC TESTS PASSED — safe to deploy to GPU instance")