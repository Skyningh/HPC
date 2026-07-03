#!/usr/bin/env python3
"""
generate_plots.py

Lee los 3 archivos JSON generados por run_sequential.py, run_joblib.py y
run_ray.py, genera gráficos comparativos (PNG) y un resumen consolidado
(JSON + CSV) que sirve de insumo para un script posterior que arme un
documento (informe) con los resultados.

Uso:
    python generate_plots.py \
        --secuencial resultados_sequential.json \
        --joblib resultados_joblib.json \
        --ray resultados_ray.json \
        --output_dir comparacion/
"""

import os
import json
import csv
import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

COLORES = {"Secuencial": "#888888", "Joblib": "#4C72B0", "Ray": "#DD8452"}


def cargar(path):
    if not path or not os.path.exists(path):
        return None
    with open(path) as f:
        return json.load(f)


def etiqueta_barras(barras, valores, fmt="{:.1f}"):
    for b, v in zip(barras, valores):
        if v is None:
            continue
        plt.text(b.get_x() + b.get_width() / 2, v, fmt.format(v), ha="center", va="bottom")


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--secuencial", default="resultados_sequential.json")
    parser.add_argument("--joblib", default="resultados_joblib.json")
    parser.add_argument("--ray", default="resultados_ray.json")
    parser.add_argument("--output_dir", default="comparacion")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    datos = {
        "Secuencial": cargar(args.secuencial),
        "Joblib": cargar(args.joblib),
        "Ray": cargar(args.ray),
    }
    datos = {k: v for k, v in datos.items() if v is not None}

    if not datos:
        print("❌ No se encontró ninguno de los 3 archivos de resultados. "
              "Corre primero run_sequential.py / run_joblib.py / run_ray.py.")
        return

    modos = list(datos.keys())
    paleta = [COLORES.get(m, "#333333") for m in modos]

    tiempos_totales = [datos[m]["tiempo_total_seg"] for m in modos]
    tiempos_prom = [datos[m]["tiempo_promedio_por_cancion_seg"] for m in modos]
    n_canciones = [datos[m]["metadata"]["n_canciones"] for m in modos]
    cpu_avg = [datos[m]["recursos"].get("cpu_percent_avg") for m in modos]
    cpu_max = [datos[m]["recursos"].get("cpu_percent_max") for m in modos]
    gpu_avg = [datos[m]["recursos"].get("gpu_util_percent_avg") for m in modos]
    threads_avg = [datos[m]["recursos"].get("process_threads_avg") for m in modos]
    energia_cpu = [datos[m]["recursos"].get("cpu_energy_j_rapl") for m in modos]
    energia_gpu = [datos[m]["recursos"].get("gpu_energy_j_estimate") for m in modos]

    # 1. Tiempo total
    plt.figure(figsize=(7, 5))
    barras = plt.bar(modos, tiempos_totales, color=paleta)
    etiqueta_barras(barras, tiempos_totales, "{:.1f}s")
    plt.ylabel("Tiempo total (s)")
    plt.title(f"Tiempo total de ejecución ({n_canciones[0]} canciones)")
    plt.tight_layout()
    plt.savefig(os.path.join(args.output_dir, "01_tiempo_total.png"), dpi=150)
    plt.close()

    # 2. Tiempo promedio por canción
    plt.figure(figsize=(7, 5))
    barras = plt.bar(modos, tiempos_prom, color=paleta)
    etiqueta_barras(barras, tiempos_prom, "{:.1f}s")
    plt.ylabel("Tiempo promedio por canción (s)")
    plt.title("Tiempo promedio por canción")
    plt.tight_layout()
    plt.savefig(os.path.join(args.output_dir, "02_tiempo_promedio.png"), dpi=150)
    plt.close()

    # 3. Speedup vs secuencial
    if "Secuencial" in datos:
        base = datos["Secuencial"]["tiempo_total_seg"]
        speedups = [base / datos[m]["tiempo_total_seg"] for m in modos]
        plt.figure(figsize=(7, 5))
        barras = plt.bar(modos, speedups, color=paleta)
        plt.axhline(1.0, color="black", linestyle="--", linewidth=1)
        etiqueta_barras(barras, speedups, "{:.2f}x")
        plt.ylabel("Speedup (veces vs. secuencial)")
        plt.title("Speedup respecto a la ejecución secuencial")
        plt.tight_layout()
        plt.savefig(os.path.join(args.output_dir, "03_speedup.png"), dpi=150)
        plt.close()

    # 4. Uso de CPU (promedio / máximo)
    x = list(range(len(modos)))
    plt.figure(figsize=(7, 5))
    plt.bar([i - 0.15 for i in x], [v or 0 for v in cpu_avg], width=0.3, label="CPU % promedio")
    plt.bar([i + 0.15 for i in x], [v or 0 for v in cpu_max], width=0.3, label="CPU % máximo")
    plt.xticks(x, modos)
    plt.ylabel("Uso de CPU del sistema (%)")
    plt.title("Uso de CPU durante la ejecución")
    plt.legend()
    plt.tight_layout()
    plt.savefig(os.path.join(args.output_dir, "04_uso_cpu.png"), dpi=150)
    plt.close()

    # 5. Threads promedio
    plt.figure(figsize=(7, 5))
    barras = plt.bar(modos, [v or 0 for v in threads_avg], color=paleta)
    etiqueta_barras(barras, threads_avg, "{:.1f}")
    plt.ylabel("Threads promedio (proceso principal)")
    plt.title("Threads promedio utilizados")
    plt.tight_layout()
    plt.savefig(os.path.join(args.output_dir, "05_threads.png"), dpi=150)
    plt.close()

    # 6. GPU (si hay datos)
    if any(v is not None for v in gpu_avg):
        plt.figure(figsize=(7, 5))
        barras = plt.bar(modos, [v or 0 for v in gpu_avg], color=paleta)
        etiqueta_barras(barras, gpu_avg, "{:.1f}%")
        plt.ylabel("Uso de GPU promedio (%)")
        plt.title("Uso de GPU durante la ejecución")
        plt.tight_layout()
        plt.savefig(os.path.join(args.output_dir, "06_uso_gpu.png"), dpi=150)
        plt.close()

    # 7. Energía estimada (CPU RAPL + GPU NVML)
    if any(v is not None for v in energia_cpu) or any(v is not None for v in energia_gpu):
        cpu_e = [v or 0 for v in energia_cpu]
        gpu_e = [v or 0 for v in energia_gpu]
        plt.figure(figsize=(7, 5))
        plt.bar(modos, cpu_e, color="#55A868", label="Energía CPU (J, RAPL)")
        plt.bar(modos, gpu_e, bottom=cpu_e, color="#C44E52", label="Energía GPU estimada (J)")
        plt.ylabel("Energía (Joules)")
        plt.title("Consumo energético estimado")
        plt.legend()
        plt.tight_layout()
        plt.savefig(os.path.join(args.output_dir, "07_energia.png"), dpi=150)
        plt.close()
    else:
        print("ℹ️  No hay datos de energía (RAPL/NVML no disponibles en este nodo); "
              "se omite el gráfico de energía.")

    # Resumen consolidado para el generador de documento
    resumen = []
    for m in modos:
        d = datos[m]
        resumen.append({
            "modo": m,
            "n_canciones": d["metadata"]["n_canciones"],
            "modelo_demucs": d["metadata"]["modelo_demucs"],
            "device": d["metadata"]["device"],
            "hostname": d["metadata"]["hostname"],
            "n_cpus_logicos": d["metadata"].get("n_cpus_logicos"),
            "tiempo_total_seg": d["tiempo_total_seg"],
            "tiempo_promedio_por_cancion_seg": d["tiempo_promedio_por_cancion_seg"],
            "n_canciones_ok": sum(1 for r in d["resultados_por_cancion"] if r["ok"]),
            "n_canciones_error": sum(1 for r in d["resultados_por_cancion"] if not r["ok"]),
            "cpu_percent_avg": d["recursos"].get("cpu_percent_avg"),
            "cpu_percent_max": d["recursos"].get("cpu_percent_max"),
            "ram_used_mb_avg": d["recursos"].get("ram_used_mb_avg"),
            "ram_used_mb_max": d["recursos"].get("ram_used_mb_max"),
            "process_threads_avg": d["recursos"].get("process_threads_avg"),
            "process_threads_max": d["recursos"].get("process_threads_max"),
            "gpu_util_percent_avg": d["recursos"].get("gpu_util_percent_avg"),
            "gpu_power_w_avg": d["recursos"].get("gpu_power_w_avg"),
            "cpu_energy_j_rapl": d["recursos"].get("cpu_energy_j_rapl"),
            "gpu_energy_j_estimate": d["recursos"].get("gpu_energy_j_estimate"),
            "speedup_vs_secuencial": (
                datos["Secuencial"]["tiempo_total_seg"] / d["tiempo_total_seg"]
                if "Secuencial" in datos else None
            ),
        })

    with open(os.path.join(args.output_dir, "resumen_comparacion.json"), "w") as f:
        json.dump(resumen, f, indent=2, default=str)

    with open(os.path.join(args.output_dir, "resumen_comparacion.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(resumen[0].keys()))
        writer.writeheader()
        writer.writerows(resumen)

    print(f"\n✅ Gráficos y resumen guardados en: {args.output_dir}/")
    print("   - 01_tiempo_total.png")
    print("   - 02_tiempo_promedio.png")
    print("   - 03_speedup.png (si hay datos secuenciales)")
    print("   - 04_uso_cpu.png")
    print("   - 05_threads.png")
    print("   - 06_uso_gpu.png (si hay GPU)")
    print("   - 07_energia.png (si hay RAPL/NVML)")
    print("   - resumen_comparacion.json / .csv  <- insumo para el generador de documento")
    print()
    for m, t in zip(modos, tiempos_totales):
        print(f"   {m:12s}: {t:8.2f} s total")


if __name__ == "__main__":
    main()
