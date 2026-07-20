# layer_a/sglang_scraper.py
import requests, time, threading, re

class SGLangMetricsScraper:
    """Scrapes SGLang's native /metrics — directly satisfies the PS:
       GPU util, queue depth, token throughput, latency."""

    def __init__(self, emitter, sglang_url="http://localhost:30000",
                 interval=3.0):
        self.emitter  = emitter
        self.url      = sglang_url
        self.interval = interval
        self._stop    = threading.Event()

    def _parse(self, text):
        m = {}
        for line in text.splitlines():
            if line.startswith('#'): continue
            match = re.match(r'(\w+).*?\s+([\d.eE+-]+)$', line)
            if match: m[match.group(1)] = float(match.group(2))
        return m

    def _scrape(self):
        r = requests.get(f"{self.url}/metrics", timeout=5)
        m = self._parse(r.text)
        return {
            "event_type":     "sglang_metrics",
            "timestamp_ns":   time.time_ns(),
            "ttft_ms":        m.get("sglang_time_to_first_token_seconds", 0) * 1000,
            "tokens_per_sec": m.get("sglang_gen_throughput", 0),
            "queue_depth":    int(m.get("sglang_num_queue_reqs", 0)),
            "kv_cache_usage": m.get("sglang_token_usage", 0),
            "running_requests": int(m.get("sglang_num_running_reqs", 0)),
        }

    def start(self):
        def loop():
            while not self._stop.is_set():
                try:    self.emitter.emit_sglang_metrics(self._scrape())
                except Exception as e: print(f"[SGLang scrape] {e}")
                time.sleep(self.interval)
        threading.Thread(target=loop, daemon=True).start()
        print(f"[SGLang scraper] every {self.interval}s")

    def stop(self): self._stop.set()