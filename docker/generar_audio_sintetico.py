#!/usr/bin/env python3
"""
docker/generar_audio_sintetico.py

Genera un archivo .wav sintético (una mezcla simple de tonos que simula
bajo + melodía + batería + ruido de fondo) para que el benchmark de Demucs
se pueda ejecutar "out of the box" sin depender de que la persona tenga
canciones reales a mano (y sin problemas de copyright).

Esto NO reemplaza probar con audio real -- es solo para que el contenedor
funcione de inmediato. Si tienes canciones propias, móntalas en
data/song/ y el benchmark las va a usar automáticamente en vez de esto
(ver entrypoint.sh).
"""
import argparse
import numpy as np
import soundfile as sf


def generar_audio(duracion_seg=30.0, sr=44100, seed=42):
    rng = np.random.default_rng(seed)
    t = np.linspace(0, duracion_seg, int(sr * duracion_seg), endpoint=False)

    # "bajo": tono grave con un vaivén lento de volumen
    bajo = 0.30 * np.sin(2 * np.pi * 80 * t) * (0.5 + 0.5 * np.sin(2 * np.pi * 0.25 * t))

    # "melodía": suma de unos pocos armónicos en rango medio, con fase aleatoria
    frecuencias = [220.0, 330.0, 440.0, 550.0]
    melodia = sum(
        np.sin(2 * np.pi * f * t + rng.uniform(0, 2 * np.pi)) for f in frecuencias
    ) / len(frecuencias)
    melodia *= 0.20

    # "batería": pulsos periódicos de ruido con caída exponencial (simil golpe)
    bateria = np.zeros_like(t)
    periodo_muestras = int(sr * 0.5)  # un "golpe" cada ~0.5s
    largo_golpe = min(2000, periodo_muestras)
    envolvente = np.exp(-np.linspace(0, 8, largo_golpe))
    for inicio in range(0, len(t) - largo_golpe, periodo_muestras):
        bateria[inicio:inicio + largo_golpe] += 0.40 * rng.standard_normal(largo_golpe) * envolvente

    # "otros": ruido de fondo suave
    otros = 0.05 * rng.standard_normal(len(t))

    mezcla = bajo + melodia + bateria + otros
    pico = np.max(np.abs(mezcla))
    if pico > 0:
        mezcla = mezcla / (pico * 1.1)  # normalizar dejando algo de headroom

    return mezcla.astype(np.float32), sr


def main():
    parser = argparse.ArgumentParser(description="Genera un audio sintético de prueba para el benchmark de Demucs")
    parser.add_argument("--output", default="audio_sintetico.wav", help="Ruta del .wav a generar")
    parser.add_argument("--duracion", type=float, default=30.0, help="Duración en segundos")
    parser.add_argument("--sr", type=int, default=44100, help="Sample rate")
    args = parser.parse_args()

    audio, sr = generar_audio(duracion_seg=args.duracion, sr=args.sr)
    sf.write(args.output, audio, sr)
    print(f"✅ Audio sintético generado: {args.output} ({args.duracion:.0f}s @ {sr} Hz)")


if __name__ == "__main__":
    main()
