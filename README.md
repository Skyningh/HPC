# Benchmark Demucs con Docker (secuencial vs joblib vs ray)

Corre en cualquier computador (Windows, Mac o Linux) que tenga Docker
instalado — no requiere SLURM ni un cluster. Compara 3 formas de ejecutar
la separación de fuentes de audio con
[Demucs](https://github.com/facebookresearch/demucs):

1. **Secuencial** — una canción a la vez, sin paralelismo (línea base).
2. **Joblib** — paralelismo multiproceso en un solo computador.
3. **Ray** — paralelismo/distribución de tareas.

## Requisitos

- [Docker](https://docs.docker.com/get-docker/) y Docker Compose (viene
  incluido en Docker Desktop para Windows/Mac; en Linux puede requerir
  instalar el plugin `docker-compose-plugin` aparte).
- Conexión a internet la **primera vez** que se corre: se descargan las
  dependencias de Python (PyTorch, Demucs, Ray, etc., pesan ~1-2 GB en
  total) y los pesos del modelo de Demucs (~80-300 MB según el modelo).
- Al menos ~4 GB de RAM libres (más si usas `N_WORKERS` alto). Con GPU no
  es obligatorio, pero acelera bastante.
- (Opcional, para usar GPU) Una GPU NVIDIA + drivers + el
  [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)
  instalado en el computador.

No necesitas tener Python, ffmpeg, ni nada más instalado a mano — todo
vive dentro del contenedor.

## Inicio rápido (3 pasos)

```bash
# 1. Copiar el archivo de configuración de ejemplo
cp .env.example .env

# 2. (Opcional) Poner tus propias canciones en data/song/
#    Si no pones nada, el benchmark genera automáticamente un audio de
#    prueba sintético para que igual funcione sin necesitar música real.
mkdir -p data/song

# 3. Construir y correr el benchmark (los 3 modos, con n=5 por defecto)
docker compose up --build
```

Al terminar, los resultados quedan en tu computador en `data/resultados/`
(no se pierden aunque borres el contenedor):

```
data/resultados/
├── resultados_sequential.json
├── resultados_joblib.json
├── resultados_ray.json
└── comparacion/
    ├── 01_tiempo_total.png
    ├── 02_tiempo_promedio.png
    ├── 03_speedup.png
    ├── 04_uso_cpu.png
    ├── 05_threads.png
    ├── 06_uso_gpu.png            (si se corrió con GPU)
    ├── 07_energia.png            (si el sistema expone esa info)
    ├── resumen_comparacion.json
    └── resumen_comparacion.csv   <- pensado como insumo para armar un
                                     informe/documento después
```

## Configuración (variables de entorno)

Todo se configura editando el archivo `.env` (copiado desde
`.env.example`). No hace falta tocar ningún código.

| Variable | Valores | Default | Descripción |
|---|---|---|---|
| `MODO` | `secuencial` \| `joblib` \| `parallel` \| `ray` \| `todos` | `todos` | Qué benchmark(s) correr. `todos` además genera los gráficos comparativos automáticamente. |
| `DEVICE` | `cpu` \| `cuda` | `cpu` | Dispositivo para Demucs. `cuda` requiere GPU NVIDIA (ver sección GPU más abajo). |
| `N_CANCIONES` | entero | `5` | Cuántas "canciones" procesar. |
| `MODELO_DEMUCS` | `htdemucs_6s`, `htdemucs`, `htdemucs_ft`, `mdx_extra`, etc. | `htdemucs_6s` | Modelo de Demucs a usar. |
| `N_WORKERS` | entero | `4` | Procesos/tareas paralelas para joblib y ray. Ajusta según los cores de tu computador (`nproc` en Linux/Mac, o revisa el Administrador de Tareas en Windows). |
| `INTERVALO_MUESTREO` | segundos (decimal) | `0.5` | Cada cuánto se mide CPU/RAM/GPU durante la ejecución. |
| `GENERAR_AUDIO_SINTETICO` | `auto` \| `si` \| `no` | `auto` | Si generar un audio de prueba cuando `data/song/` está vacía. |
| `DURACION_AUDIO_SINTETICO_SEG` | segundos | `30` | Duración del audio sintético generado (si aplica). |

### Ejemplos de uso

Correr solo el modo ray, con 10 canciones:
```bash
# en tu .env:
MODO=ray
N_CANCIONES=10
```

Correr solo secuencial, para tener la línea base:
```bash
MODO=secuencial
```

Comparar los 3 modos con más canciones y más workers:
```bash
MODO=todos
N_CANCIONES=50
N_WORKERS=8
```

También puedes sobrescribir variables al vuelo sin editar `.env`:
```bash
MODO=ray N_CANCIONES=20 docker compose up --build
```

## Usar tus propias canciones

Copia tus archivos de audio (`.mp3`, `.wav`, `.flac`, `.ogg`, `.m4a`,
`.aac`) dentro de `data/song/` antes de correr `docker compose up`:

- Si dejas **una sola** canción ahí, se replica `N_CANCIONES` veces (vía
  symlinks internos) para simular ese número de canciones — útil para
  medir cómo escala cada modo sin necesitar 50 canciones distintas.
- Si dejas **varias** canciones, se usan hasta `N_CANCIONES` de ellas.
- Si la carpeta queda vacía, se genera un audio sintético automáticamente
  (no reemplaza probar con audio real, pero permite correr el benchmark
  igual).

## Usar GPU (opcional)

1. Verifica que tu computador tenga una GPU NVIDIA y el
   [NVIDIA Container Toolkit](https://docs.nvidia.com/datacenter/cloud-native/container-toolkit/)
   instalado.
2. En `docker-compose.yml`, descomenta el bloque `deploy` dentro del
   servicio `demucs-benchmark`.
3. En tu `.env`, pon `DEVICE=cuda`.
4. `docker compose up --build`.

Si no tienes GPU o no quieres configurar esto, simplemente deja
`DEVICE=cpu` (funciona en cualquier computador, solo que más lento).

## Comparar varias corridas con distinto N (opcional)

Si quieres ver cómo cambia el resultado al variar `N_CANCIONES` (por
ejemplo 5, 20, 100), puedes correr el contenedor varias veces guardando
cada resultado en una carpeta distinta:

```bash
N_CANCIONES=5   docker compose up --build && mv data/resultados data/resultados_n5
N_CANCIONES=20  docker compose up --build && mv data/resultados data/resultados_n20
N_CANCIONES=100 docker compose up --build && mv data/resultados data/resultados_n100
```

Luego organízalas como `resultados_completos/n_5/comparacion/`,
`resultados_completos/n_20/comparacion/`, etc. (copiando la carpeta
`comparacion/` de cada corrida), y usa el script incluido
`consolidar_resultados.py` para juntar todo en una sola tabla y un
gráfico que muestra el "cruce" entre joblib y ray a medida que crece N:

```bash
python consolidar_resultados.py \
    --base_dir resultados_completos \
    --n_valores 5 20 100 \
    --output_dir resultados_completos/consolidado
```

(Este script corre en tu computador con Python normal, no necesita
Docker — solo requiere `matplotlib` instalado: `pip install matplotlib`.)

## Preguntas frecuentes / problemas comunes

**"Se demora mucho en el primer `docker compose up`"** — Es normal: la
primera vez descarga PyTorch, Demucs, Ray y los pesos del modelo. Las
siguientes veces es mucho más rápido porque Docker cachea la imagen.

**"¿Por qué con pocas canciones parece que joblib es más rápido que ray, y
al revés con muchas?"** — Ray tiene un overhead de arranque (levantar su
runtime, el object store, etc.) que pesa más cuando hay pocas tareas. Con
muchas canciones, ese overhead se diluye y Ray suele escalar mejor. El
gráfico `03_speedup.png` es el mejor lugar para verlo.

**"El gráfico de energía (`07_energia.png`) no aparece"** — La medición de
energía de CPU depende de que el sistema exponga contadores Intel RAPL
(`/sys/class/powercap`), lo cual normalmente **no está disponible dentro
de contenedores Docker** (Docker Desktop en Mac/Windows corre en una VM, y
en Linux depende de permisos del host). No es un error: simplemente esa
métrica queda en `null` y el gráfico se omite. La energía de GPU sí puede
funcionar si hay GPU NVIDIA expuesta al contenedor.

**"¿Cómo limpio todo y empiezo de nuevo?"**
```bash
docker compose down
rm -rf data/resultados/*
```

**"Quiero ver los logs mientras corre"** — `docker compose up` (sin
`--build` en las siguientes veces) ya muestra los logs en pantalla en
vivo. También quedan en `docker compose logs -f`.
