# layer_a/emitter.py
import psycopg2, json
from psycopg2.extras import Json
from opentelemetry import trace, metrics
from opentelemetry.sdk.trace import TracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.sdk.resources import Resource

class DualWriteEmitter:
    def __init__(self, signoz_endpoint, pg_dsn,
                 service_name="teleduct-sglang"):

        # ── SigNoz (traces + metrics) ──
        res = Resource.create({"service.name": service_name})
        tp  = TracerProvider(resource=res)
        tp.add_span_processor(BatchSpanProcessor(
            OTLPSpanExporter(endpoint=f"{signoz_endpoint}/v1/traces")))
        trace.set_tracer_provider(tp)
        self.tracer = trace.get_tracer(service_name)

        reader = PeriodicExportingMetricReader(
            OTLPMetricExporter(endpoint=f"{signoz_endpoint}/v1/metrics"),
            export_interval_millis=5000)
        metrics.set_meter_provider(
            MeterProvider(resource=res, metric_readers=[reader]))
        meter = metrics.get_meter(service_name)

        # Metric instruments
        self.m_margin  = meter.create_histogram("llm.sampling_margin",  unit="prob")
        self.m_fragile = meter.create_counter("llm.fragile_decisions")
        self.m_moe     = meter.create_histogram("llm.moe_routing_margin", unit="prob")
        self.m_vram    = meter.create_gauge("gpu.vram_used_gb",    unit="GB")
        self.m_sm      = meter.create_gauge("gpu.sm_utilization",  unit="%")
        self.m_power   = meter.create_gauge("gpu.power_watts",     unit="W")
        self.m_ttft    = meter.create_gauge("sglang.ttft_ms",      unit="ms")
        self.m_tps     = meter.create_gauge("sglang.tokens_per_sec")
        self.m_queue   = meter.create_gauge("sglang.queue_depth")

        # ── PostgreSQL (Ally's ASUS, reached via ngrok) ──
        self.pg  = psycopg2.connect(pg_dsn)
        self.pg.autocommit = True
        self.cur = self.pg.cursor()

    def emit_logit_event(self, d):
        with self.tracer.start_as_current_span("logit_capture") as s:
            s.set_attribute("llm.sampling_margin",  d["sampling_margin"])
            s.set_attribute("llm.fragility_flag",   d["fragility_flag"])
            s.set_attribute("llm.confidence_label", d["confidence_label"])
            s.set_attribute("llm.session_id",       str(d.get("session_id")))
            s.set_attribute("llm.step_id",          str(d.get("step_id")))
        self.m_margin.record(d["sampling_margin"],
                             {"node": str(d.get("node_name"))})
        if d["fragility_flag"]:
            self.m_fragile.add(1)
        self.cur.execute("""INSERT INTO logit_telemetry
            (session_id, step_id, request_id, timestamp_ns, top_k_token_ids,
             top_k_probs, sampling_margin, fragility_flag, confidence_label)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (d.get("session_id"), d.get("step_id"), d.get("request_id"),
             d["timestamp_ns"], Json(d["top_k_token_ids"]),
             Json(d["top_k_probs"]), d["sampling_margin"],
             d["fragility_flag"], d["confidence_label"]))

    def emit_moe_event(self, d):
        with self.tracer.start_as_current_span("moe_routing") as s:
            s.set_attribute("moe.layer_idx",          d["layer_idx"])
            s.set_attribute("moe.avg_routing_margin", d["avg_routing_margin"])
            s.set_attribute("moe.routing_fragile",    d["routing_fragile"])
            s.set_attribute("moe.expert_load",        json.dumps(d["expert_load"]))
        self.m_moe.record(d["avg_routing_margin"],
                          {"layer": str(d["layer_idx"])})
        self.cur.execute("""INSERT INTO moe_telemetry
            (session_id, step_id, timestamp_ns, layer_idx, num_experts_total,
             experts_per_token, avg_routing_margin, routing_fragile, expert_load)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
            (d.get("session_id"), d.get("step_id"), d["timestamp_ns"],
             d["layer_idx"], d["num_experts_total"], d["experts_per_token"],
             d["avg_routing_margin"], d["routing_fragile"],
             Json(d["expert_load"])))

    def emit_hardware_event(self, d):
        with self.tracer.start_as_current_span("gpu_hardware_state") as s:
            for k, v in d.items():
                if k != "event_type": s.set_attribute(f"hw.{k}", v)
        self.m_vram.set(d["gpu_vram_used_gb"])
        self.m_sm.set(d["gpu_sm_utilization"])
        self.m_power.set(d["gpu_power_watts"])
        self.cur.execute("""INSERT INTO hardware_telemetry
            (timestamp_ns, gpu_vram_used_gb, gpu_vram_pressure,
             gpu_sm_utilization, gpu_memory_bandwidth,
             gpu_temperature_c, gpu_power_watts)
            VALUES (%s,%s,%s,%s,%s,%s,%s)""",
            (d["timestamp_ns"], d["gpu_vram_used_gb"], d["gpu_vram_pressure"],
             d["gpu_sm_utilization"], d["gpu_memory_bandwidth"],
             d["gpu_temperature_c"], d["gpu_power_watts"]))

    def emit_sglang_metrics(self, d):
        self.m_ttft.set(d["ttft_ms"])
        self.m_tps.set(d["tokens_per_sec"])
        self.m_queue.set(d["queue_depth"])
        self.cur.execute("""INSERT INTO sglang_metrics
            (timestamp_ns, ttft_ms, tokens_per_sec, queue_depth,
             kv_cache_usage, running_requests)
            VALUES (%s,%s,%s,%s,%s,%s)""",
            (d["timestamp_ns"], d["ttft_ms"], d["tokens_per_sec"],
             d["queue_depth"], d["kv_cache_usage"], d["running_requests"]))