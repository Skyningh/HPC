#!/usr/bin/env python3
"""
run_sequential.py

Benchmark de Demucs - modo SECUENCIAL (línea base, sin paralelismo).
Procesa las canciones una por una, en el mismo proceso.

Ejemplos de uso:
    python run_sequential.py --input cancion.mp3 --n_canciones 5 \
        --output resultados_sequential.json

    python run_sequential.py --input_dir ./canciones --n_canciones 500 \
        --device cuda --output resultados_sequential.json
"""

import os
import sys
import json
import time
import socket
import platform
import argparse

import psutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from common.demucs_utils import run_demucs_single, preparar_lista_canciones
from common.resource_monitor import ResourceMonitor


def main():
    parser = argparse.ArgumentParser(description="Benchmark Demucs - modo SECUENCIAL")
    parser.add_argument("--input", help="Archivo de audio único, se replica N veces (symlinks)")
    parser.add_argument("--input_dir", help="Carpeta con canciones (usa las primeras N)")
    parser.add_argument("--n_canciones", type=int, default=5, help="Cantidad de canciones a procesar")
    parser.add_argument("--modelo_demucs", default="htdemucs_6s")
    parser.add_argument("--device", default="cpu", choices=["cpu", "cuda"])
    parser.add_argument("--output", default="resultados_sequential.json")
    parser.add_argument("--tmp_dir", default="tmp_canciones_seq")
    parser.add_argument("--out_root", default="separated_sequential", help="Carpeta de salida de audios separados")
    parser.add_argument("--intervalo_muestreo", type=float, default=0.5, help="Segundos entre muestras de recursos")
    args = parser.parse_args()

    if not args.input and not args.input_dir:
        print("❌ Debes indicar --input (archivo único) o --input_dir (carpeta)")
        sys.exit(1)

    canciones = preparar_lista_canciones(
        input_path=args.input,
        input_dir=args.input_dir,
        n=args.n_canciones,
        tmp_dir=args.tmp_dir,
    )

    print(f"🔁 Modo: SECUENCIAL | canciones: {len(canciones)} | "
          f"modelo: {args.modelo_demucs} | device: {args.device}")

    monitor = ResourceMonitor(interval=args.intervalo_muestreo)
    monitor.start()

    t_inicio = time.time()
    resultados = []
    for i, cancion in enumerate(canciones, start=1):
        print(f"  [{i}/{len(canciones)}] procesando {os.path.basename(cancion)} ...")
        r = run_demucs_single(
            cancion,
            modelo=args.modelo_demucs,
            device=args.device,
            out_root=args.out_root,
        )
        estado = "OK" if r["ok"] else "ERROR"
        print(f"      -> {estado} en {r['tiempo_seg']:.2f} s")
        resultados.append(r)
    t_fin = time.time()

    recursos = monitor.stop()

    salida = {
        "modo": "secuencial",
        "metadata": {
            "hostname": socket.gethostname(),
            "sistema": platform.platform(),
            "python_version": platform.python_version(),
            "n_cpus_logicos": psutil.cpu_count(logical=True),
            "n_cpus_fisicos": psutil.cpu_count(logical=False),
            "modelo_demucs": args.modelo_demucs,
            "device": args.device,
            "n_canciones": len(canciones),
            "n_workers_configurados": 1,
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
    print(f"\n✅ Secuencial terminado: {ok}/{len(resultados)} OK")
    print(f"⏱️  Tiempo total: {salida['tiempo_total_seg']:.2f} s")
    print(f"📄 Resultados guardados en: {args.output}")


if __name__ == "__main__":
    main()
