# ==============================================================================
# Dockerfile - Benchmark Demucs: secuencial vs joblib vs ray
#
# Imagen pensada para que cualquier persona (con o sin canciones propias,
# con o sin GPU) pueda correr el benchmark con un solo comando.
#
# Uso rápido:
#   docker compose up --build
#
# Ver DOCKER.md para instrucciones detalladas y la lista de variables de
# entorno configurables (env.example).
# ==============================================================================
FROM python:3.11-slim

LABEL description="Benchmark Demucs: secuencial vs joblib vs ray"

# Dependencias de sistema:
#   - ffmpeg: requerido por demucs/torchaudio para leer/escribir audio
#   - git: algunas dependencias de demucs se instalan desde repos git
#   - build-essential: para compilar extensiones nativas de algunos paquetes
RUN apt-get update && apt-get install -y --no-install-recommends \
        ffmpeg \
        git \
        build-essential \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalar dependencias de Python primero (mejor cacheo de capas de Docker)
COPY requirements.txt .
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir -r requirements.txt

# Copiar el código del proyecto
COPY common/ ./common/
COPY run_sequential.py run_joblib.py run_ray.py generate_plots.py consolidar_resultados.py ./
COPY docker/entrypoint.sh ./docker/entrypoint.sh
COPY docker/generar_audio_sintetico.py ./docker/generar_audio_sintetico.py

RUN chmod +x ./docker/entrypoint.sh

# Carpetas de entrada (canciones) y salida (resultados), pensadas para
# montarse como volúmenes desde el host -- ver docker-compose.yml
RUN mkdir -p /data/song /data/resultados
VOLUME ["/data/song", "/data/resultados"]

ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["./docker/entrypoint.sh"]
