# layer_a/moe_capture.py
import torch, time
from context import get_agent_context

class MoERoutingCapture:
    MOE_MODULE_TYPES = {
        'Qwen2MoeSparseMoeBlock', 'QWenMLPMoE',
        'MixtralSparseMoeBlock', 'DeepseekV2MoE', 'MoELayer',
    }

    def __init__(self, model, emitter):
        self.emitter = emitter
        self.hooks   = []
        self._register_hooks(model)

    def _register_hooks(self, model):
        found = 0
        for layer_idx, (name, module) in enumerate(model.named_modules()):
            if type(module).__name__ in self.MOE_MODULE_TYPES:
                self.hooks.append(
                    module.register_forward_hook(
                        self._make_hook(layer_idx, name)))
                found += 1
        print(f"[MoE] Registered {found} router hooks" if found else
              "[MoE] WARNING: no MoE modules found — is this a dense model?")

    def _make_hook(self, layer_idx, module_name):
        def hook(module, inp, out):
            try:
                rl = getattr(module, 'last_router_logits', None)
                if rl is None:
                    return
                probs  = torch.softmax(rl.float(), dim=-1)
                k      = min(4, probs.shape[-1])
                topk   = torch.topk(probs, k=k, dim=-1)
                ids    = topk.indices.tolist()
                wts    = topk.values.tolist()
                margins = [w[0] - w[1] for w in wts]
                avg_margin = sum(margins) / len(margins)

                flat  = [e for row in ids for e in row]
                total = len(flat)
                load  = {}
                for e in flat:
                    load[str(e)] = load.get(str(e), 0) + 1
                load = {k2: round(v/total, 4) for k2, v in load.items()}

                ctx = get_agent_context()
                self.emitter.emit_moe_event({
                    "event_type":         "moe_routing",
                    "timestamp_ns":       time.time_ns(),
                    "layer_idx":          layer_idx,
                    "num_experts_total":  rl.shape[-1],
                    "experts_per_token":  k,
                    "avg_routing_margin": avg_margin,
                    "routing_fragile":    avg_margin < 0.10,
                    "expert_load":        load,
                    "session_id":         ctx.get("session_id"),
                    "step_id":            ctx.get("step_id"),
                    "node_name":          ctx.get("node_name"),
                })
            except Exception as e:
                print(f"[MoE] hook error L{layer_idx}: {e}")
        return hook


def patch_qwen_moe_router(model):
    """Qwen1.5-MoE discards router logits — patch gate to retain them."""
    patched = 0
    for name, module in model.named_modules():
        if name.endswith('gate') and isinstance(module, torch.nn.Linear):
            orig = module.forward
            def mk(o, m):
                def f(x):
                    out = o(x)
                    m.last_router_logits = out
                    return out
                return f
            module.forward = mk(orig, module)
            patched += 1
    print(f"[MoE] patched {patched} gate modules")
    return model