#!/bin/bash
# ==============================================================================
# docker/entrypoint.sh
#
# Punto de entrada del contenedor. Lee la configuración desde variables de
# entorno (ver .env.example) y corre el benchmark de Demucs en modo
# secuencial, joblib, ray, o los 3, según lo indicado.
#
# Si no hay canciones reales montadas en $INPUT_DIR, genera automáticamente
# un audio sintético de prueba para que el contenedor funcione sin
# depender de que la persona tenga música a mano.
# ==============================================================================
set -uo pipefail

# ---------- Variables de entorno (con valores por defecto razonables) ----------
MODO="${MODO:-todos}"                                    # secuencial | joblib | parallel | ray | todos
DEVICE="${DEVICE:-cpu}"                                   # cpu | cuda
N_CANCIONES="${N_CANCIONES:-5}"
MODELO_DEMUCS="${MODELO_DEMUCS:-htdemucs_6s}"
N_WORKERS="${N_WORKERS:-4}"
INTERVALO_MUESTREO="${INTERVALO_MUESTREO:-0.5}"
INPUT_DIR="${INPUT_DIR:-/data/song}"
OUTPUT_DIR="${OUTPUT_DIR:-/data/resultados}"
GENERAR_AUDIO_SINTETICO="${GENERAR_AUDIO_SINTETICO:-auto}"  # auto | si | no
DURACION_AUDIO_SINTETICO_SEG="${DURACION_AUDIO_SINTETICO_SEG:-30}"

mkdir -p "$INPUT_DIR" "$OUTPUT_DIR"

EXT_AUDIO="mp3 wav flac ogg m4a aac"

hay_audio_real() {
    for ext in $EXT_AUDIO; do
        if compgen -G "$INPUT_DIR"/*."$ext" > /dev/null 2>&1; then
            return 0
        fi
    done
    return 1
}

# ---------- Generar audio sintético si hace falta ----------
if [ "$GENERAR_AUDIO_SINTETICO" = "si" ] || { [ "$GENERAR_AUDIO_SINTETICO" = "auto" ] && ! hay_audio_real; }; then
    echo "[entrypoint] No se encontró audio real en $INPUT_DIR (o se forzó con GENERAR_AUDIO_SINTETICO=si)."
    echo "[entrypoint] Generando audio sintético de ${DURACION_AUDIO_SINTETICO_SEG}s para poder correr el benchmark..."
    python docker/generar_audio_sintetico.py \
        --output "$INPUT_DIR/audio_sintetico.wav" \
        --duracion "$DURACION_AUDIO_SINTETICO_SEG"
fi

# ---------- Armar los argumentos de entrada para los scripts ----------
N_ARCHIVOS=$(find "$INPUT_DIR" -maxdepth 1 -type f \( -iname "*.mp3" -o -iname "*.wav" -o -iname "*.flac" -o -iname "*.ogg" -o -iname "*.m4a" -o -iname "*.aac" \) | wc -l)

if [ "$N_ARCHIVOS" -eq 1 ]; then
    ARCHIVO=$(find "$INPUT_DIR" -maxdepth 1 -type f \( -iname "*.mp3" -o -iname "*.wav" -o -iname "*.flac" -o -iname "*.ogg" -o -iname "*.m4a" -o -iname "*.aac" \) | head -n1)
    # Un solo archivo -> se replica N_CANCIONES veces vía symlinks (ver common/demucs_utils.py)
    ENTRADA_ARGS=(--input "$ARCHIVO")
else
    # Varios archivos -> se usan hasta N_CANCIONES de ellos
    ENTRADA_ARGS=(--input_dir "$INPUT_DIR")
fi

echo "=============================================================="
echo " Benchmark Demucs (secuencial / joblib / ray) - contenedor Docker"
echo "   modo:              $MODO"
echo "   device:            $DEVICE"
echo "   n_canciones:       $N_CANCIONES"
echo "   modelo_demucs:     $MODELO_DEMUCS"
echo "   n_workers:         $N_WORKERS"
echo "   entrada:           ${ENTRADA_ARGS[*]}"
echo "   salida (montada):  $OUTPUT_DIR"
echo "=============================================================="

correr_secuencial() {
    echo "[entrypoint] --- Corriendo modo SECUENCIAL ---"
    python run_sequential.py \
        "${ENTRADA_ARGS[@]}" \
        --n_canciones "$N_CANCIONES" \
        --modelo_demucs "$MODELO_DEMUCS" \
        --device "$DEVICE" \
        --intervalo_muestreo "$INTERVALO_MUESTREO" \
        --tmp_dir "$OUTPUT_DIR/tmp_sequential" \
        --out_root "$OUTPUT_DIR/separated_sequential" \
        --output "$OUTPUT_DIR/resultados_sequential.json"
}

correr_joblib() {
    echo "[entrypoint] --- Corriendo modo JOBLIB (paralelo) ---"
    python run_joblib.py \
        "${ENTRADA_ARGS[@]}" \
        --n_canciones "$N_CANCIONES" \
        --n_workers "$N_WORKERS" \
        --backend loky \
        --modelo_demucs "$MODELO_DEMUCS" \
        --device "$DEVICE" \
        --intervalo_muestreo "$INTERVALO_MUESTREO" \
        --tmp_dir "$OUTPUT_DIR/tmp_joblib" \
        --out_root "$OUTPUT_DIR/separated_joblib" \
        --output "$OUTPUT_DIR/resultados_joblib.json"
}

correr_ray() {
    echo "[entrypoint] --- Corriendo modo RAY ---"
    GPUS_POR_TAREA=0
    [ "$DEVICE" = "cuda" ] && GPUS_POR_TAREA=1
    python run_ray.py \
        "${ENTRADA_ARGS[@]}" \
        --n_canciones "$N_CANCIONES" \
        --n_workers "$N_WORKERS" \
        --cpus_por_tarea 1 \
        --gpus_por_tarea "$GPUS_POR_TAREA" \
        --modelo_demucs "$MODELO_DEMUCS" \
        --device "$DEVICE" \
        --intervalo_muestreo "$INTERVALO_MUESTREO" \
        --tmp_dir "$OUTPUT_DIR/tmp_ray" \
        --out_root "$OUTPUT_DIR/separated_ray" \
        --output "$OUTPUT_DIR/resultados_ray.json"
}

case "$MODO" in
    secuencial)
        correr_secuencial
        ;;
    joblib|parallel)
        correr_joblib
        ;;
    ray)
        correr_ray
        ;;
    todos)
        correr_secuencial
        correr_joblib
        correr_ray
        ;;
    *)
        echo "[entrypoint] ❌ MODO inválido: '$MODO'. Usa: secuencial | joblib | parallel | ray | todos"
        exit 1
        ;;
esac

# Si se corrieron los 3 modos, generar automáticamente los gráficos comparativos
if [ "$MODO" = "todos" ]; then
    echo "[entrypoint] --- Generando gráficos comparativos ---"
    python generate_plots.py \
        --secuencial "$OUTPUT_DIR/resultados_sequential.json" \
        --joblib "$OUTPUT_DIR/resultados_joblib.json" \
        --ray "$OUTPUT_DIR/resultados_ray.json" \
        --output_dir "$OUTPUT_DIR/comparacion"
fi

echo "=============================================================="
echo "[entrypoint] ✅ Listo. Resultados disponibles en: $OUTPUT_DIR"
echo "   (carpeta montada como volumen -> visible en tu computador en ./data/resultados)"
echo "=============================================================="
