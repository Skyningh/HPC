"""
common/demucs_utils.py

Funciones compartidas por los 3 modos de ejecución (secuencial, joblib, ray):
  - run_demucs_single: corre demucs sobre UNA canción y mide su tiempo.
  - preparar_lista_canciones: arma la lista de N canciones a procesar,
    ya sea desde una carpeta o replicando un único archivo N veces
    (vía symlinks, para no duplicar audio en disco).

Basado en el script original de demucs entregado por el usuario.
"""

import os
import glob
import shutil
import subprocess
import time

AUDIO_EXTS = (".mp3", ".wav", ".flac", ".ogg", ".m4a", ".aac")


def run_demucs_single(ruta_audio, modelo="htdemucs_6s", device="cpu", out_root="separated"):
    """
    Ejecuta demucs sobre una canción y retorna un diccionario con
    los resultados y el tiempo que demoró.

    No lanza excepción si demucs falla: en su lugar retorna ok=False
    y el stderr, para que el benchmark completo no se caiga por una
    canción problemática.
    """
    nombre = os.path.splitext(os.path.basename(ruta_audio))[0]

    comando = [
        "demucs",
        "-n", modelo,
        "--device", device,
        "-o", out_root,
        ruta_audio,
    ]

    t0 = time.time()
    ok = True
    err = None
    try:
        subprocess.run(comando, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError as e:
        ok = False
        err = (e.stderr or "")[-4000:]  # se recorta por si el log es muy largo
    except FileNotFoundError as e:
        ok = False
        err = f"No se encontró el ejecutable 'demucs': {e}"
    t1 = time.time()

    out_dir = os.path.join(out_root, modelo, nombre)

    return {
        "cancion": ruta_audio,
        "nombre": nombre,
        "modelo": modelo,
        "device": device,
        "ok": ok,
        "error": err,
        "tiempo_seg": t1 - t0,
        "out_dir": out_dir,
        "pid": os.getpid(),
    }


def preparar_lista_canciones(input_path=None, input_dir=None, n=5, tmp_dir="tmp_canciones"):
    """
    Arma la lista de canciones a procesar.

    - Si se entrega input_dir: usa los audios encontrados en esa carpeta
      (ordenados alfabéticamente), tomando las primeras `n` (o todas si n<=0).
    - Si se entrega input_path (un único archivo): crea `n` symlinks hacia
      ese archivo dentro de tmp_dir, para simular N canciones distintas
      sin duplicar el audio en disco y evitando que procesos paralelos
      escriban sobre el mismo nombre de salida.
    """
    if input_dir:
        archivos = sorted(
            f for f in glob.glob(os.path.join(input_dir, "*"))
            if f.lower().endswith(AUDIO_EXTS)
        )
        if n and n > 0:
            archivos = archivos[:n]
        if not archivos:
            raise FileNotFoundError(f"No se encontraron audios en: {input_dir}")
        return archivos

    if input_path:
        if not os.path.exists(input_path):
            raise FileNotFoundError(input_path)

        os.makedirs(tmp_dir, exist_ok=True)
        ext = os.path.splitext(input_path)[1]
        abs_input = os.path.abspath(input_path)

        canciones = []
        for i in range(n):
            destino = os.path.join(tmp_dir, f"cancion_{i:04d}{ext}")
            if not os.path.exists(destino):
                try:
                    os.symlink(abs_input, destino)
                except (OSError, NotImplementedError):
                    shutil.copy(abs_input, destino)
            canciones.append(destino)
        return canciones

    raise ValueError("Debes indicar --input (archivo único) o --input_dir (carpeta)")
