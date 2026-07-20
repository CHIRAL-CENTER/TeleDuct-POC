# layer_a/gpu_poller.py
import pynvml, time, threading

class GPUPoller:
    def __init__(self, emitter, interval=2.0):
        self.emitter  = emitter
        self.interval = interval
        self._stop    = threading.Event()
        pynvml.nvmlInit()
        self.handle = pynvml.nvmlDeviceGetHandleByIndex(0)

    def _poll(self):
        mem   = pynvml.nvmlDeviceGetMemoryInfo(self.handle)
        util  = pynvml.nvmlDeviceGetUtilizationRates(self.handle)
        temp  = pynvml.nvmlDeviceGetTemperature(
                    self.handle, pynvml.NVML_TEMPERATURE_GPU)
        power = pynvml.nvmlDeviceGetPowerUsage(self.handle) / 1000.0
        return {
            "event_type":           "gpu_hardware_state",
            "timestamp_ns":         time.time_ns(),
            "gpu_vram_used_gb":     mem.used / 1e9,
            "gpu_vram_pressure":    mem.used / mem.total,
            "gpu_sm_utilization":   util.gpu,
            "gpu_memory_bandwidth": util.memory,
            "gpu_temperature_c":    temp,
            "gpu_power_watts":      power,
        }

    def start(self):
        def loop():
            while not self._stop.is_set():
                try:    self.emitter.emit_hardware_event(self._poll())
                except Exception as e: print(f"[GPU] {e}")
                time.sleep(self.interval)
        threading.Thread(target=loop, daemon=True).start()
        print(f"[GPU] polling every {self.interval}s")

    def stop(self):
        self._stop.set()
        pynvml.nvmlShutdown()