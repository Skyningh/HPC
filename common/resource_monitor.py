"""
common/resource_monitor.py

ResourceMonitor: muestrea en un hilo de fondo, cada `interval` segundos,
el uso de CPU (global y por núcleo), RAM, threads del proceso principal,
y si hay GPU NVIDIA disponible: uso de GPU, memoria de GPU y potencia (W).

También estima el consumo energético:
  - CPU: usando Intel RAPL (/sys/class/powercap/intel-rapl*), disponible
    en la mayoría de los nodos Linux con CPU Intel. Si el nodo es AMD o
    no hay acceso a RAPL, esta métrica queda en None (no rompe el script).
  - GPU: usando la potencia instantánea reportada por NVML (pynvml),
    integrada aproximadamente en el tiempo (potencia promedio * tiempo).

Notas importantes:
  - psutil.cpu_percent mide uso de CPU de TODO el sistema (no solo del
    proceso), lo cual es correcto para este benchmark porque nos interesa
    cuánto del nodo completo se está usando (joblib/ray lanzan procesos
    hijos separados).
  - nvmlDeviceGetPowerUsage mide la potencia de TODA la GPU, no solo el
    proceso. Es razonable cuando el proceso que corre el benchmark es el
    principal consumidor de GPU en ese momento (uso típico al correr esto
    en un computador dedicado o un contenedor Docker sin otras cargas GPU).
"""

import os
import time
import threading

import psutil

try:
    import pynvml
    pynvml.nvmlInit()
    _HAS_NVML = True
except Exception:
    _HAS_NVML = False


class ResourceMonitor:
    def __init__(self, interval=0.5, gpu_index=0):
        self.interval = interval
        self.gpu_index = gpu_index

        self._stop_event = threading.Event()
        self._thread = None
        self.samples = []

        self._proc = psutil.Process()

        self._gpu_handle = None
        if _HAS_NVML:
            try:
                self._gpu_handle = pynvml.nvmlDeviceGetHandleByIndex(gpu_index)
            except Exception:
                self._gpu_handle = None

        self._rapl_paths = self._find_rapl_paths()
        self._rapl_start = self._read_rapl_energy_uj()

    # ---------- RAPL (energía CPU) ----------

    def _find_rapl_paths(self):
        base = "/sys/class/powercap"
        paths = []
        if os.path.isdir(base):
            for entry in os.listdir(base):
                # solo paquetes de nivel superior tipo "intel-rapl:0"
                if entry.startswith("intel-rapl:") and entry.count(":") == 1:
                    energy_file = os.path.join(base, entry, "energy_uj")
                    if os.access(energy_file, os.R_OK):
                        paths.append(energy_file)
        return paths

    def _read_rapl_energy_uj(self):
        if not self._rapl_paths:
            return None
        total = 0
        try:
            for p in self._rapl_paths:
                with open(p) as f:
                    total += int(f.read().strip())
            return total
        except Exception:
            return None

    # ---------- Loop de muestreo ----------

    def _sample_loop(self):
        psutil.cpu_percent(percpu=True)  # llamada de "priming"
        while not self._stop_event.is_set():
            ts = time.time()
            cpu_percpu = psutil.cpu_percent(percpu=True)
            cpu_avg = sum(cpu_percpu) / len(cpu_percpu) if cpu_percpu else None

            mem = psutil.virtual_memory()

            try:
                proc_threads = self._proc.num_threads()
            except Exception:
                proc_threads = None

            try:
                proc_children = len(self._proc.children(recursive=True))
            except Exception:
                proc_children = None

            gpu_util = gpu_mem_mb = gpu_power_w = gpu_temp = None
            if self._gpu_handle is not None:
                try:
                    util = pynvml.nvmlDeviceGetUtilizationRates(self._gpu_handle)
                    gpu_util = util.gpu
                    meminfo = pynvml.nvmlDeviceGetMemoryInfo(self._gpu_handle)
                    gpu_mem_mb = meminfo.used / (1024 ** 2)
                    gpu_power_w = pynvml.nvmlDeviceGetPowerUsage(self._gpu_handle) / 1000.0
                    gpu_temp = pynvml.nvmlDeviceGetTemperature(
                        self._gpu_handle, pynvml.NVML_TEMPERATURE_GPU
                    )
                except Exception:
                    pass

            self.samples.append({
                "t": ts,
                "cpu_percpu": cpu_percpu,
                "cpu_avg": cpu_avg,
                "ram_used_mb": mem.used / (1024 ** 2),
                "ram_percent": mem.percent,
                "proc_threads": proc_threads,
                "proc_children": proc_children,
                "gpu_util_percent": gpu_util,
                "gpu_mem_used_mb": gpu_mem_mb,
                "gpu_power_w": gpu_power_w,
                "gpu_temp_c": gpu_temp,
            })

            time.sleep(self.interval)

    def start(self):
        self.samples = []
        self._rapl_start = self._read_rapl_energy_uj()
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._sample_loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self.interval * 5 + 2)
        return self.summary()

    # ---------- Resumen ----------

    def summary(self):
        if not self.samples:
            return {
                "n_samples": 0,
                "nvml_disponible": _HAS_NVML,
                "rapl_disponible": bool(self._rapl_paths),
            }

        def _avg(vals):
            vals = [v for v in vals if v is not None]
            return sum(vals) / len(vals) if vals else None

        def _max(vals):
            vals = [v for v in vals if v is not None]
            return max(vals) if vals else None

        cpu_avgs = [s["cpu_avg"] for s in self.samples]
        ram_used = [s["ram_used_mb"] for s in self.samples]
        threads = [s["proc_threads"] for s in self.samples]
        gpu_utils = [s["gpu_util_percent"] for s in self.samples]
        gpu_powers = [s["gpu_power_w"] for s in self.samples]
        gpu_mems = [s["gpu_mem_used_mb"] for s in self.samples]

        # energía CPU vía RAPL (diferencia de contador, en microjoules)
        rapl_end = self._read_rapl_energy_uj()
        cpu_energy_j = None
        if self._rapl_start is not None and rapl_end is not None:
            delta_uj = rapl_end - self._rapl_start
            if delta_uj < 0:
                # el contador de RAPL puede desbordarse en jobs muy largos
                delta_uj = None
            if delta_uj is not None:
                cpu_energy_j = delta_uj / 1e6

        # energía GPU estimada: potencia promedio * tiempo total (trapezoidal simple)
        gpu_energy_j = None
        gpu_powers_validas = [p for p in gpu_powers if p is not None]
        if gpu_powers_validas and len(self.samples) > 1:
            elapsed = self.samples[-1]["t"] - self.samples[0]["t"]
            gpu_energy_j = (sum(gpu_powers_validas) / len(gpu_powers_validas)) * elapsed

        # uso de CPU por núcleo, promediado a lo largo del tiempo
        n_cores = len(self.samples[0]["cpu_percpu"]) if self.samples[0]["cpu_percpu"] else 0
        cpu_percpu_avg = None
        if n_cores:
            sums = [0.0] * n_cores
            counts = 0
            for s in self.samples:
                if s["cpu_percpu"] and len(s["cpu_percpu"]) == n_cores:
                    for i, v in enumerate(s["cpu_percpu"]):
                        sums[i] += v
                    counts += 1
            if counts:
                cpu_percpu_avg = [round(v / counts, 2) for v in sums]

        return {
            "n_samples": len(self.samples),
            "nvml_disponible": _HAS_NVML,
            "rapl_disponible": bool(self._rapl_paths),
            "duracion_muestreo_seg": self.samples[-1]["t"] - self.samples[0]["t"],

            "cpu_percent_avg": _avg(cpu_avgs),
            "cpu_percent_max": _max(cpu_avgs),
            "cpu_percpu_avg": cpu_percpu_avg,
            "n_cores_logicos": n_cores,

            "ram_used_mb_avg": _avg(ram_used),
            "ram_used_mb_max": _max(ram_used),

            "process_threads_avg": _avg(threads),
            "process_threads_max": _max(threads),

            "gpu_util_percent_avg": _avg(gpu_utils),
            "gpu_util_percent_max": _max(gpu_utils),
            "gpu_mem_used_mb_avg": _avg(gpu_mems),
            "gpu_power_w_avg": _avg(gpu_powers),
            "gpu_power_w_max": _max(gpu_powers),
            "gpu_energy_j_estimate": gpu_energy_j,

            "cpu_energy_j_rapl": cpu_energy_j,

            # samples crudos por si se quieren graficar series de tiempo después
            "raw_samples": self.samples,
        }
