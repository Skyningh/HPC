#!/usr/bin/env python3
"""
consolidar_resultados.py

Combina los `resumen_comparacion.json` generados por generate_plots.py para
distintos valores de N (ej. 5, 100, 500) en una sola tabla, y grafica cómo
evoluciona el tiempo total y el speedup de joblib/ray a medida que crece el
número de canciones -- el "cruce" donde ray empieza a ganarle a joblib.

Uso:
    python consolidar_resultados.py \
        --base_dir resultados_completos \
        --n_valores 5 100 500 \
        --output_dir resultados_completos/consolidado
"""
import os
import json
import csv
import argparse

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt

COLORES = {"Secuencial": "#888888", "Joblib": "#4C72B0", "Ray": "#DD8452"}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--base_dir", default="resultados_completos")
    parser.add_argument("--n_valores", type=int, nargs="+", default=[5, 100, 500])
    parser.add_argument("--output_dir", default="resultados_completos/consolidado")
    args = parser.parse_args()

    os.makedirs(args.output_dir, exist_ok=True)

    filas = []
    for n in args.n_valores:
        path = os.path.join(args.base_dir, f"n_{n}", "comparacion", "resumen_comparacion.json")
        if not os.path.exists(path):
            print(f"⚠️  No se encontró {path}, se omite n={n}")
            continue
        with open(path) as f:
            resumen = json.load(f)
        for fila in resumen:
            fila["n_canciones_solicitadas"] = n
            filas.append(fila)

    if not filas:
        print("❌ No se encontró ningún resumen_comparacion.json todavía. "
              "Corre primero el benchmark (docker compose up) para uno o más "
              "valores de N, guardando cada corrida en su propia carpeta.")
        return

    with open(os.path.join(args.output_dir, "consolidado.json"), "w") as f:
        json.dump(filas, f, indent=2, default=str)

    campos = list(filas[0].keys())
    with open(os.path.join(args.output_dir, "consolidado.csv"), "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=campos)
        writer.writeheader()
        writer.writerows(filas)

    por_modo = {}
    for fila in filas:
        por_modo.setdefault(fila["modo"], []).append(fila)
    for modo in por_modo:
        por_modo[modo].sort(key=lambda f: f["n_canciones_solicitadas"])

    # Gráfico 1: tiempo total vs. número de canciones (log-log)
    plt.figure(figsize=(7, 5))
    for modo, filas_modo in por_modo.items():
        xs = [f["n_canciones_solicitadas"] for f in filas_modo]
        ys = [f["tiempo_total_seg"] for f in filas_modo]
        plt.plot(xs, ys, marker="o", label=modo, color=COLORES.get(modo))
    plt.xscale("log")
    plt.yscale("log")
    plt.xlabel("Número de canciones")
    plt.ylabel("Tiempo total (s)")
    plt.title("Tiempo total vs. número de canciones")
    plt.legend()
    plt.grid(True, which="both", alpha=0.3)
    plt.tight_layout()
    plt.savefig(os.path.join(args.output_dir, "01_tiempo_vs_n.png"), dpi=150)
    plt.close()

    # Gráfico 2: speedup vs secuencial, en función de N -> aquí se ve el cruce
    plt.figure(figsize=(7, 5))
    hay_datos = False
    for modo, filas_modo in por_modo.items():
        if modo == "Secuencial":
            continue
        xs = [f["n_canciones_solicitadas"] for f in filas_modo]
        ys = [f.get("speedup_vs_secuencial") for f in filas_modo]
        if all(y is None for y in ys):
            continue
        hay_datos = True
        plt.plot(xs, ys, marker="o", label=modo, color=COLORES.get(modo))
    if hay_datos:
        plt.axhline(1.0, color="black", linestyle="--", linewidth=1)
        plt.xscale("log")
        plt.xlabel("Número de canciones")
        plt.ylabel("Speedup vs. secuencial (x veces)")
        plt.title("Speedup vs. número de canciones (cruce joblib / ray)")
        plt.legend()
        plt.grid(True, which="both", alpha=0.3)
        plt.tight_layout()
        plt.savefig(os.path.join(args.output_dir, "02_speedup_vs_n.png"), dpi=150)
    plt.close()

    print(f"✅ Consolidado guardado en: {args.output_dir}/")
    print("   - consolidado.json / .csv")
    print("   - 01_tiempo_vs_n.png")
    if hay_datos:
        print("   - 02_speedup_vs_n.png  <- aquí se debería ver el cruce joblib vs ray")


if __name__ == "__main__":
    main()
