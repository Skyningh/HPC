#!/usr/bin/env python3
"""
run_ray.py

Benchmark de Demucs - modo RAY (paralelo/distribuido). Por defecto levanta
su propio cluster local de Ray en el computador donde se ejecuta (útil
tanto en un laptop como en un servidor con muchos cores). También admite
conectarse a un cluster Ray ya existente vía --ray_address si se dispone
de uno.

Ejemplos de uso:
    # Local (Ray levanta su propio cluster local):
    python run_ray.py --input cancion.mp3 --n_canciones 100 \
        --n_workers 8 --output resultados_ray.json

    # Conectándose a un Ray cluster ya iniciado en otra parte:
    python run_ray.py --input_dir ./canciones --n_canciones 100 \
        --ray_address auto --output resultados_ray.json
"""

import os
import sys
import json
import time
import socket
import platform
import argparse

import psutil
import ray

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common.demucs_utils import run_demucs_single, preparar_lista_canciones
from common.resource_monitor import ResourceMonitor


def main():
    parser = argparse.ArgumentParser(description="Benchmark Demucs - modo RAY (paralelo/distribuido)")
    parser.add_argument("--input", help="Archivo de audio único, se replica N veces (symlinks)")
    parser.add_argument("--input_dir", help="Carpeta con canciones (usa las primeras N)")
    parser.add_argument("--n_canciones", type=int, default=5, help="Cantidad de canciones a procesar")
    parser.add_argument("--modelo_demucs", default="htdemucs_6s")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--n_workers", type=int, default=None,
                         help="Nº de CPUs a usar para el cluster local de Ray. "
                              "Ignorado si --ray_address apunta a un cluster existente.")
    parser.add_argument("--cpus_por_tarea", type=float, default=1.0,
                         help="CPUs reservadas por tarea de demucs (num_cpus en @ray.remote)")
    parser.add_argument("--gpus_por_tarea", type=float, default=0.0,
                         help="GPUs reservadas por tarea (ej. 1 o 0.5 para compartir una GPU)")
    parser.add_argument("--ray_address", default=None,
                         help="Dirección de un Ray cluster existente (ej. 'auto'). "
                              "Si no se indica, Ray arranca un cluster local en este nodo.")
    parser.add_argument("--output", default="resultados_ray.json")
    parser.add_argument("--tmp_dir", default="tmp_canciones_ray")
    parser.add_argument("--out_root", default="separated_ray")
    parser.add_argument("--intervalo_muestreo", type=float, default=0.5)
    args = parser.parse_args()

    if not args.input and not args.input_dir:
        print("❌ Debes indicar --input (archivo único) o --input_dir (carpeta)")
        sys.exit(1)

    if args.gpus_por_tarea > 0:
        args.device = "cuda"

    canciones = preparar_lista_canciones(
        input_path=args.input,
        input_dir=args.input_dir,
        n=args.n_canciones,
        tmp_dir=args.tmp_dir,
    )

    if args.ray_address:
        ray.init(address=args.ray_address)
    else:
        ray.init(num_cpus=args.n_workers)  # None = usa todos los cores del nodo

    recursos_cluster = ray.cluster_resources()
    print(f"🚀 Modo: RAY | canciones: {len(canciones)} | recursos cluster ray: {recursos_cluster} | "
          f"cpus_por_tarea: {args.cpus_por_tarea} | gpus_por_tarea: {args.gpus_por_tarea} | "
          f"modelo: {args.modelo_demucs} | device: {args.device}")

    tarea_remota = ray.remote(
        num_cpus=args.cpus_por_tarea,
        num_gpus=args.gpus_por_tarea,
    )(run_demucs_single)

    monitor = ResourceMonitor(interval=args.intervalo_muestreo)
    monitor.start()

    t_inicio = time.time()
    futuros = [
        tarea_remota.remote(
            cancion, modelo=args.modelo_demucs, device=args.device, out_root=args.out_root
        )
        for cancion in canciones
    ]
    resultados = ray.get(futuros)
    t_fin = time.time()

    recursos = monitor.stop()

    salida = {
        "modo": "ray",
        "metadata": {
            "hostname": socket.gethostname(),
            "sistema": platform.platform(),
            "python_version": platform.python_version(),
            "n_cpus_logicos": psutil.cpu_count(logical=True),
            "n_cpus_fisicos": psutil.cpu_count(logical=False),
            "modelo_demucs": args.modelo_demucs,
            "device": args.device,
            "n_canciones": len(canciones),
            "n_workers_configurados": args.n_workers,
            "cpus_por_tarea": args.cpus_por_tarea,
            "gpus_por_tarea": args.gpus_por_tarea,
            "ray_address": args.ray_address,
            "ray_cluster_resources": recursos_cluster,
            "timestamp_inicio": t_inicio,
            "timestamp_fin": t_fin,
        },
        "tiempo_total_seg": t_fin - t_inicio,
        "tiempo_promedio_por_cancion_seg": (t_fin - t_inicio) / len(canciones) if canciones else None,
        "resultados_por_cancion": resultados,
        "recursos": recursos,
    }

    with open(args.output, "w") as f:
        json.dump(salida, f, indent=2, default=str)

    ok = sum(1 for r in resultados if r["ok"])
    print(f"\n✅ Ray terminado: {ok}/{len(resultados)} OK")
    print(f"⏱️  Tiempo total: {salida['tiempo_total_seg']:.2f} s")
    print(f"📄 Resultados guardados en: {args.output}")

    ray.shutdown()


if __name__ == "__main__":
    main()
