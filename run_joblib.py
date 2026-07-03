#!/usr/bin/env python3
"""
run_joblib.py

Benchmark de Demucs - modo PARALELO con joblib.Parallel (multiproceso,
backend "loky"). Pensado para paralelismo dentro de UN SOLO nodo
(comparte memoria de disco, no requiere cluster).

Ejemplos de uso:
    python run_joblib.py --input cancion.mp3 --n_canciones 5 \
        --n_workers 4 --output resultados_joblib.json

    python run_joblib.py --input_dir ./canciones --n_canciones 500 \
        --n_workers 16 --device cpu --output resultados_joblib.json
"""

import os
import sys
import json
import time
import socket
import platform
import argparse

import psutil
from joblib import Parallel, delayed

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common.demucs_utils import run_demucs_single, preparar_lista_canciones
from common.resource_monitor import ResourceMonitor


def main():
    parser = argparse.ArgumentParser(description="Benchmark Demucs - modo JOBLIB (paralelo, 1 nodo)")
    parser.add_argument("--input", help="Archivo de audio único, se replica N veces (symlinks)")
    parser.add_argument("--input_dir", help="Carpeta con canciones (usa las primeras N)")
    parser.add_argument("--n_canciones", type=int, default=5, help="Cantidad de canciones a procesar")
    parser.add_argument("--modelo_demucs", default="htdemucs_6s")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--n_workers", type=int, default=-1,
                         help="Nº de procesos joblib. -1 = todos los cores disponibles")
    parser.add_argument("--backend", default="loky", choices=["loky", "threading", "multiprocessing"])
    parser.add_argument("--output", default="resultados_joblib.json")
    parser.add_argument("--tmp_dir", default="tmp_canciones_joblib")
    parser.add_argument("--out_root", default="separated_joblib")
    parser.add_argument("--intervalo_muestreo", type=float, default=0.5)
    args = parser.parse_args()

    if not args.input and not args.input_dir:
        print("❌ Debes indicar --input (archivo único) o --input_dir (carpeta)")
        sys.exit(1)

    if args.device == "cuda" and args.n_workers not in (1, -1) and args.n_workers > 1:
        print("⚠️  Aviso: usar --device cuda con varios workers joblib puede saturar la "
              "memoria de una sola GPU. Considera --n_workers 1 o -2 para pruebas con GPU.")

    canciones = preparar_lista_canciones(
        input_path=args.input,
        input_dir=args.input_dir,
        n=args.n_canciones,
        tmp_dir=args.tmp_dir,
    )

    n_workers_reales = args.n_workers if args.n_workers > 0 else (os.cpu_count() or 1)

    print(f"⚡ Modo: JOBLIB | canciones: {len(canciones)} | workers: {args.n_workers} "
          f"(~{n_workers_reales}) | backend: {args.backend} | "
          f"modelo: {args.modelo_demucs} | device: {args.device}")

    monitor = ResourceMonitor(interval=args.intervalo_muestreo)
    monitor.start()

    t_inicio = time.time()
    resultados = Parallel(n_jobs=args.n_workers, backend=args.backend, verbose=10)(
        delayed(run_demucs_single)(
            cancion, modelo=args.modelo_demucs, device=args.device, out_root=args.out_root
        )
        for cancion in canciones
    )
    t_fin = time.time()

    recursos = monitor.stop()

    salida = {
        "modo": "joblib",
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
            "n_workers_reales_estimados": n_workers_reales,
            "backend_joblib": args.backend,
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
    print(f"\n✅ Joblib terminado: {ok}/{len(resultados)} OK")
    print(f"⏱️  Tiempo total: {salida['tiempo_total_seg']:.2f} s")
    print(f"📄 Resultados guardados en: {args.output}")


if __name__ == "__main__":
    main()
