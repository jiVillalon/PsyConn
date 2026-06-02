#!/bin/bash
# =============================================================================
# download_ds006072.sh — Descarga selectiva de OpenNeuro ds006072
# con compresion inmediata .nii -> .nii.gz
#
# Dataset: "Psilocybin desynchronizes the human brain" (Siegel et al., 2024)
# Fuente:  https://openneuro.org/datasets/ds006072/versions/1.0.8
#
# Uso (dos modos):
#   1) Bulk (defecto, sin argumentos): descarga la matriz completa
#      P1..P7 x DRUG1/DRUG2 x BOLDREST1..BOLDREST${MAX_REST}.
#        bash src/bash/download_ds006072.sh
#
#   2) Single (con --sub/--ses/--task [--run]): descarga un unico BOLD
#      especifico (part-mag + part-phase si aplica) mas el anat de
#      referencia del sujeto y los fmap de la sesion target. Util para
#      recuperar runs fuera del tope MAX_REST sin reabrir el scope global
#      (caso sub-P7/ses-7 BOLDREST5/BOLDREST6, ver PsiloConn_1.3.qmd
#      §sec-ds006072-heterogeneidad).
#        bash src/bash/download_ds006072.sh --sub P7 --ses 7 --task BOLDREST5 --run 1
#
#   (ejecutar desde Git Bash / terminal de VS Code)
#
# Que descarga (modo bulk):
#   - Metadatos raiz (dataset_description.json, README, session_data.csv, etc.)
#   - Datos conductuales (BehavioralAssessments/)
#   - Por cada sujeto (P1-P7):
#       - Anatomia T1w + T2w de la sesion baseline (ses-1, o ses-0 para P7)
#       - Fieldmaps spin-echo AP/PA de las sesiones de droga
#       - BOLD resting state: tareas BOLDREST1..BOLDREST4 (tope por diseno,
#         ver MAX_REST abajo), todos los runs (run-1 y run-2 cuando existan),
#         todos los echoes (1..5), part-mag para todos los sujetos +
#         part-phase solo para P4-P7 (P1-P3 se publicaron sin reconstruccion
#         de fase; la convencion BIDS para rest cambio durante el estudio:
#         P1/P3/P5 usan task-REST1/REST2 con run-1/run-2, mientras que
#         P4/P6/P7 usan task-REST1..REST6 sin repetir run-. Ver
#         PsiloConn_1.0.qmd §sec-ds006072-heterogeneidad). NORDIC se aplica
#         en modo complex-valued para P4-P7 y en modo magnitude-only para
#         P1-P3, ambos validados en Moeller 2021 / Vizioli 2021.
#
#         El tope en REST4 deja un pool minimamente redundante para poder
#         sustituir scans corruptos sin volver a S3 (caso sub-P6/ses-9:
#         REST1/REST2 truncados => se usa REST3 o REST4 como fallback).
#         REST5/REST6 de sub-P7/ses-7 no se descargan; quedan fuera del
#         escopo del TFM por viabilidad de NORDIC + fMRIPrep + TEDANA.
#
# Que NO descarga:
#   - Task BOLD (BOLDTASK1, BOLDTASK2)
#   - Difusion (DWI)
#   - Sujetos de replicacion (P1R-P5R)
#   - CIFTIs procesados (NON_BIDS/)
#   - Sesiones baseline, between y after (solo las de droga)
#
# Compresion:
#   - Cada run BOLD (part-mag y part-phase) se comprime a .nii.gz tras la descarga
#   - Compresion lossless (gzip): sin perdida de informacion
#   - Pico de espacio temporal: ~8.6 GB (1 tarea x 5 ecos x 2 partes sin comprimir)
#
# Reanudable:
#   - Si se interrumpe, re-ejecutar el script y saltara lo ya completado
#   - aws s3 sync solo descarga archivos faltantes o modificados
# =============================================================================

set -euo pipefail

S3="s3://openneuro.org/ds006072"
LOCAL="E:/ds006072"
AWS="/c/Program Files/Amazon/AWSCLIV2/aws"

# Tope de tareas BOLDREST* a descargar (por viabilidad computacional).
# Se conservan REST1..REST4 para todos los sujetos. REST5/REST6 (solo
# presentes en sub-P7/ses-7) se descartan. Subir este numero reabre el
# scope si hay tiempo de computo disponible mas adelante.
MAX_REST=4

# Verificar que AWS CLI esta disponible
if ! "$AWS" --version &>/dev/null; then
  echo "ERROR: AWS CLI no encontrado en: $AWS"
  echo "Instalar con: winget install Amazon.AWSCLI (en PowerShell)"
  exit 1
fi

# ---- Mapeo sujeto -> sesiones (extraido de session_data.csv y README) ----
# ANAT: sesion con imagenes anatomicas T1w/T2w
# DRUG1/DRUG2: sesiones de administracion de droga
# ORDER: que droga se administro en cada sesion
declare -A ANAT=(  [P1]=1  [P2]=1  [P3]=1  [P4]=1  [P5]=1  [P6]=1  [P7]=0 )
declare -A DRUG1=( [P1]=6  [P2]=10 [P3]=8  [P4]=6  [P5]=6  [P6]=5  [P7]=7 )
declare -A DRUG2=( [P1]=11 [P2]=16 [P3]=12 [P4]=10 [P5]=10 [P6]=9  [P7]=11 )

# Sujetos publicados SIN imagenes de fase (part-phase). NORDIC se aplica en
# modo magnitude-only para estos sujetos (Moeller 2021, Vizioli 2021).
# Ver PsiloConn_1.0.qmd §sec-nordic-magonly para justificacion.
declare -A HAS_PHASE=( [P1]=0 [P2]=0 [P3]=0 [P4]=1 [P5]=1 [P6]=1 [P7]=1 )
# Orden de administracion (para referencia):
# P1: Drug1=MTP, Drug2=PSIL  |  P2: Drug1=PSIL, Drug2=MTP
# P3: Drug1=MTP, Drug2=PSIL  |  P4: Drug1=MTP,  Drug2=PSIL
# P5: Drug1=PSIL, Drug2=MTP  |  P6: Drug1=MTP,  Drug2=PSIL
# P7: Drug1=PSIL, Drug2=MTP

# ---- Argumentos CLI: bulk (defecto) vs single (BOLD especifico) ----
# Modo single sirve para recuperar runs fuera del tope MAX_REST (caso
# sub-P7/ses-7 BOLDREST5/BOLDREST6) sin reabrir el scope global.
TARGET_SUB=""
TARGET_SES=""
TARGET_TASK=""
TARGET_RUN=""

print_usage() {
  cat <<USAGE
Uso:
  bash download_ds006072.sh
      Modo bulk: P1..P7 x DRUG1/DRUG2 x BOLDREST1..BOLDREST${MAX_REST}.

  bash download_ds006072.sh --sub P7 --ses 7 --task BOLDREST5 [--run 1]
      Modo single: descarga un unico BOLD especifico (part-mag y part-phase
      si aplica) mas el anat del sujeto y los fmap de la sesion. --run es
      opcional; si se omite, descarga todos los runs publicados de esa task.
USAGE
}

while [ $# -gt 0 ]; do
  case "$1" in
    --sub)  TARGET_SUB="$2";  shift 2 ;;
    --ses)  TARGET_SES="$2";  shift 2 ;;
    --task) TARGET_TASK="$2"; shift 2 ;;
    --run)  TARGET_RUN="$2";  shift 2 ;;
    -h|--help) print_usage; exit 0 ;;
    *) echo "ERROR: argumento desconocido: $1"; print_usage; exit 1 ;;
  esac
done

MODE="bulk"
if [ -n "${TARGET_SUB}${TARGET_SES}${TARGET_TASK}${TARGET_RUN}" ]; then
  : "${TARGET_SUB:?--sub requerido (ej: P7)}"
  : "${TARGET_SES:?--ses requerido (ej: 7)}"
  : "${TARGET_TASK:?--task requerido (ej: BOLDREST5)}"
  case " P1 P2 P3 P4 P5 P6 P7 " in
    *" $TARGET_SUB "*) ;;
    *) echo "ERROR: sub-${TARGET_SUB} no es un sujeto valido (P1..P7)."; exit 1 ;;
  esac
  MODE="single"
fi

# ---- Funcion: comprimir .nii a .nii.gz ----
# $1: directorio donde buscar
# $2 (opcional): patron glob para filtrar (ej: "*BOLDREST1*")
#     Si se omite, comprime todos los .nii del directorio
compress_nii() {
  local dir="$1"
  local filter="${2:-}"
  local count=0

  if [ ! -d "$dir" ]; then
    return
  fi

  # Construir patron de busqueda: si hay filtro, usarlo; si no, todos los .nii
  local find_name="*.nii"
  if [ -n "$filter" ]; then
    find_name="${filter}.nii"
  fi

  while IFS= read -r -d '' nii_file; do
    gz_file="${nii_file}.gz"
    local basename_file
    basename_file=$(basename "$nii_file")

    if [ -f "$gz_file" ]; then
      # Ambos .nii y .nii.gz existen: verificar integridad del .gz
      # (puede ocurrir si gzip fue interrumpido y dejo un .gz parcial)
      if gzip -t "$gz_file" 2>/dev/null; then
        rm -f "$nii_file"
      else
        echo "    ⚠ ${basename_file}.gz corrupto, recomprimiendo..."
        rm -f "$gz_file"
        gzip "$nii_file"
        count=$((count + 1))
      fi
    else
      local size_mb
      size_mb=$(du -m "$nii_file" | cut -f1)
      echo "    Comprimiendo: ${basename_file} (${size_mb} MB)..."
      gzip "$nii_file"
      local gz_size_mb
      gz_size_mb=$(du -m "$gz_file" | cut -f1)
      local ratio
      ratio=$(awk "BEGIN {printf \"%.1f\", $size_mb / $gz_size_mb}")
      echo "    -> ${gz_size_mb} MB (ratio ${ratio}x)"
      count=$((count + 1))
    fi
  done < <(find "$dir" -name "$find_name" -not -name "*.nii.gz" -print0 2>/dev/null)

  if [ $count -gt 0 ]; then
    echo "    $count archivos comprimidos en $dir"
  fi
}

# ---- Funcion: verificar si un directorio ya esta completo ----
# $1: directorio a comprobar
# $2: patron glob para .nii.gz (ej: "*BOLDREST1*.nii.gz")
# $3: patron glob para .nii sin comprimir (ej: "*BOLDREST1*.nii")
#     Si se omite, busca cualquier .nii en el directorio
# $4: numero minimo esperado de .nii.gz (ej: 10 para 2 runs x 5 ecos)
#     Si se omite o es 0, solo comprueba que haya al menos uno
is_complete() {
  local dir="$1"
  local gz_pattern="$2"
  local raw_pattern="${3:-*.nii}"
  local expected="${4:-0}"

  [ -d "$dir" ] || return 1

  local gz_count
  gz_count=$(find "$dir" -name "$gz_pattern" 2>/dev/null | wc -l)

  # Debe tener al menos los archivos esperados (o al menos 1 si no se especifica)
  if [ "$expected" -gt 0 ]; then
    [ "$gz_count" -ge "$expected" ] || return 1
  else
    [ "$gz_count" -gt 0 ] || return 1
  fi

  # No debe haber .nii sin comprimir del mismo patron
  [ "$(find "$dir" -name "$raw_pattern" -not -name '*.nii.gz' 2>/dev/null | wc -l)" -eq 0 ]
}

# ---- Funcion: descubrir tareas BOLDREST* presentes en S3 para una sesion ----
# $1: sujeto (ej: P5)
# $2: sesion (ej: 6)
# Devuelve (stdout): lista unica y ordenada de tareas (BOLDREST1, BOLDREST2, ...)
#     separadas por espacio. Vacio si no hay tareas REST en la sesion.
list_s3_rest_tasks() {
  local sub="$1"
  local ses="$2"
  "$AWS" s3 ls "$S3/sub-${sub}/ses-${ses}/func/" --no-sign-request 2>/dev/null \
    | grep -oE "BOLDREST[0-9]+" \
    | sort -u \
    | awk -v max="$MAX_REST" '{
        n = substr($0, length("BOLDREST")+1) + 0
        if (n >= 1 && n <= max) print $0
      }' \
    | tr '\n' ' '
}

# =============================================================================
echo "============================================================"
echo " ds006072 — Descarga selectiva + compresion"
echo " Psilocybin Precision Functional Mapping (Siegel et al. 2024)"
echo "============================================================"
echo ""

# ---- Paso 0: Metadatos y datos conductuales ----
echo "=== Paso 0: Metadatos y datos conductuales ==="
"$AWS" s3 sync --no-sign-request \
  --exclude "*" \
  --include "dataset_description.json" \
  --include "README" \
  --include "CHANGES" \
  --include "LICENSE" \
  --include "session_data.csv" \
  --include ".bidsignore" \
  --include "BehavioralAssessments/*" \
  --include "PPFM_session_notes*" \
  "$S3" "$LOCAL/"
echo "  Metadatos descargados."
echo ""

# ---- Modo single: descarga dirigida (anat ref + fmap + BOLD especifico) ----
# Bypasea Paso 1 / Resumen final del modo bulk y sale tras descargar solo lo
# pedido. anat y fmap se descargan tambien (idempotentes) porque son
# requisitos minimos para procesar el BOLD en fMRIPrep.
if [ "$MODE" = "single" ]; then
  RUN_TAG=${TARGET_RUN:+ run-${TARGET_RUN}}
  echo "=== Modo single: sub-${TARGET_SUB} ses-${TARGET_SES} ${TARGET_TASK}${RUN_TAG} ==="

  # anat de referencia (sesion definida en mapa ANAT)
  ASES=${ANAT[$TARGET_SUB]}
  ANAT_DIR="$LOCAL/sub-${TARGET_SUB}/ses-${ASES}/anat"
  if is_complete "$ANAT_DIR" "*.nii.gz" "*.nii"; then
    anat_n=$(find "$ANAT_DIR" -name "*.nii.gz" 2>/dev/null | wc -l)
    echo "  [OK] anat ses-${ASES} (ya completo: ${anat_n} .nii.gz)"
  else
    echo "  Descargando anat de referencia (ses-${ASES}, T1w + T2w)..."
    "$AWS" s3 sync --no-sign-request \
      --exclude "*" --include "anat/*" \
      "$S3/sub-${TARGET_SUB}/ses-${ASES}/" \
      "$LOCAL/sub-${TARGET_SUB}/ses-${ASES}/"
    compress_nii "$ANAT_DIR"
  fi

  # fmap de la sesion target (necesario para SDC)
  SES_DIR="$LOCAL/sub-${TARGET_SUB}/ses-${TARGET_SES}"
  FMAP_DIR="$SES_DIR/fmap"
  FUNC_DIR="$SES_DIR/func"
  if is_complete "$FMAP_DIR" "*.nii.gz" "*.nii"; then
    fmap_n=$(find "$FMAP_DIR" -name "*.nii.gz" 2>/dev/null | wc -l)
    echo "  [OK] ses-${TARGET_SES} fmap (ya completo: ${fmap_n} .nii.gz)"
  else
    echo "  Descargando ses-${TARGET_SES} fmap (AP/PA)..."
    "$AWS" s3 sync --no-sign-request \
      --exclude "*" --include "fmap/*" \
      "$S3/sub-${TARGET_SUB}/ses-${TARGET_SES}/" "$SES_DIR/"
    compress_nii "$FMAP_DIR"
  fi

  # Patron de seleccion del BOLD especifico
  if [ -n "$TARGET_RUN" ]; then
    RUN_GLOB="*${TARGET_TASK}_*run-${TARGET_RUN}_*"
  else
    RUN_GLOB="*${TARGET_TASK}_*"
  fi
  MAG_GLOB="${RUN_GLOB}part-mag*"
  PHA_GLOB="${RUN_GLOB}part-phase*"

  # part-mag (siempre)
  if is_complete "$FUNC_DIR" "${MAG_GLOB}.nii.gz" "${MAG_GLOB}.nii"; then
    m_n=$(find "$FUNC_DIR" -name "${MAG_GLOB}.nii.gz" 2>/dev/null | wc -l)
    echo "  [OK] ${TARGET_TASK}${RUN_TAG} part-mag (ya completo: ${m_n} .nii.gz)"
  else
    echo "  Descargando ${TARGET_TASK}${RUN_TAG} part-mag (5 ecos)..."
    "$AWS" s3 sync --no-sign-request \
      --exclude "*" --include "func/${MAG_GLOB}" \
      "$S3/sub-${TARGET_SUB}/ses-${TARGET_SES}/" "$SES_DIR/"
    compress_nii "$FUNC_DIR" "$MAG_GLOB"
  fi

  # part-phase (solo si el sujeto la tiene publicada)
  if [ "${HAS_PHASE[$TARGET_SUB]}" -eq 1 ]; then
    if is_complete "$FUNC_DIR" "${PHA_GLOB}.nii.gz" "${PHA_GLOB}.nii"; then
      p_n=$(find "$FUNC_DIR" -name "${PHA_GLOB}.nii.gz" 2>/dev/null | wc -l)
      echo "  [OK] ${TARGET_TASK}${RUN_TAG} part-phase (ya completo: ${p_n} .nii.gz)"
    else
      echo "  Descargando ${TARGET_TASK}${RUN_TAG} part-phase (5 ecos)..."
      "$AWS" s3 sync --no-sign-request \
        --exclude "*" --include "func/${PHA_GLOB}" \
        "$S3/sub-${TARGET_SUB}/ses-${TARGET_SES}/" "$SES_DIR/"
      compress_nii "$FUNC_DIR" "$PHA_GLOB"
    fi
  else
    echo "  [SKIP] ${TARGET_TASK}${RUN_TAG} part-phase (sub-${TARGET_SUB} sin fase publicada -> NORDIC magnitude-only)"
  fi

  # Resumen single
  echo ""
  echo "============================================================"
  echo " Modo single completado:"
  echo "============================================================"
  N_ANAT=$(find "$ANAT_DIR" -name "*.nii.gz" 2>/dev/null | wc -l)
  N_FMAP=$(find "$FMAP_DIR" -name "*.nii.gz" 2>/dev/null | wc -l)
  N_MAG=$(find "$FUNC_DIR" -name "${MAG_GLOB}.nii.gz" 2>/dev/null | wc -l)
  N_PHA=$(find "$FUNC_DIR" -name "${PHA_GLOB}.nii.gz" 2>/dev/null | wc -l)
  TARGET_SIZE=$(du -sh "$SES_DIR" 2>/dev/null | cut -f1)
  PHASE_TAG="mag-only-NORDIC"
  [ "${HAS_PHASE[$TARGET_SUB]}" -eq 1 ] && PHASE_TAG="complex-NORDIC"
  echo "  sub-${TARGET_SUB} ses-${TARGET_SES} ${TARGET_TASK}${RUN_TAG} [${PHASE_TAG}]"
  echo "  anat (ses-${ASES}): ${N_ANAT} .nii.gz"
  echo "  fmap (ses-${TARGET_SES}): ${N_FMAP} .nii.gz"
  echo "  func: ${N_MAG} mag + ${N_PHA} phase = $((N_MAG + N_PHA)) .nii.gz"
  echo "  Tamano ses-${TARGET_SES}: ${TARGET_SIZE:-pendiente}"
  REMAINING=$(find "$LOCAL" -name "*.nii" -not -name "*.nii.gz" 2>/dev/null | wc -l)
  if [ "$REMAINING" -gt 0 ]; then
    echo "  ⚠ Quedan ${REMAINING} archivos .nii sin comprimir en $LOCAL"
  fi
  if [ "$N_MAG" -eq 0 ]; then
    echo "  ⚠ No se descargo ningun part-mag — verificar que ${TARGET_TASK}${RUN_TAG} existe en S3 para sub-${TARGET_SUB}/ses-${TARGET_SES}."
    exit 1
  fi
  echo "  ✓ Descarga single completada."
  exit 0
fi

# ---- Paso 1: Datos de imagen por sujeto ----
for SUB in P1 P2 P3 P4 P5 P6 P7; do
  echo "=== sub-${SUB} ==="

  # --- Anatomia (T1w + T2w) ---
  ASES=${ANAT[$SUB]}
  ANAT_DIR="$LOCAL/sub-${SUB}/ses-${ASES}/anat"

  # anat: T1w + T2w (ya .nii.gz en S3; numero de runs varia por sujeto)
  if is_complete "$ANAT_DIR" "*.nii.gz" "*.nii"; then
    anat_n=$(find "$ANAT_DIR" -name "*.nii.gz" 2>/dev/null | wc -l)
    echo "  [OK] anat ses-${ASES} (ya completo: ${anat_n} .nii.gz)"
  else
    echo "  Descargando anat (ses-${ASES}, T1w + T2w)..."
    "$AWS" s3 sync --no-sign-request \
      --exclude "*" --include "anat/*" \
      "$S3/sub-${SUB}/ses-${ASES}/" \
      "$LOCAL/sub-${SUB}/ses-${ASES}/"
    compress_nii "$ANAT_DIR"
  fi

  # --- Sesiones de droga (Drug1 + Drug2) ---
  for DSES in ${DRUG1[$SUB]} ${DRUG2[$SUB]}; do
    SES_DIR="$LOCAL/sub-${SUB}/ses-${DSES}"
    FUNC_DIR="$SES_DIR/func"
    FMAP_DIR="$SES_DIR/fmap"

    # Fieldmaps (AP/PA; numero de runs varia por sujeto)
    if is_complete "$FMAP_DIR" "*.nii.gz" "*.nii"; then
      fmap_n=$(find "$FMAP_DIR" -name "*.nii.gz" 2>/dev/null | wc -l)
      echo "  [OK] ses-${DSES} fmap (ya completo: ${fmap_n} .nii.gz)"
    else
      echo "  Descargando ses-${DSES} fmap (AP/PA)..."
      "$AWS" s3 sync --no-sign-request \
        --exclude "*" --include "fmap/*" \
        "$S3/sub-${SUB}/ses-${DSES}/" "$SES_DIR/"
      compress_nii "$FMAP_DIR"
    fi

    # Descubrir tareas BOLDREST* presentes en S3 para esta sesion
    REST_TASKS=$(list_s3_rest_tasks "$SUB" "$DSES")
    if [ -z "$REST_TASKS" ]; then
      echo "  ⚠ ses-${DSES}: no se encontraron tareas BOLDREST* en S3"
      continue
    fi
    echo "  ses-${DSES}: tareas rest detectadas en S3 -> ${REST_TASKS}"

    # Iterar por cada tarea REST descubierta (bajar mag + phase si aplica)
    for RTASK in $REST_TASKS; do
      # part-mag (descargar -> comprimir -> liberar espacio)
      if is_complete "$FUNC_DIR" "*${RTASK}_*part-mag*.nii.gz" "*${RTASK}_*part-mag*.nii"; then
        rm_n=$(find "$FUNC_DIR" -name "*${RTASK}_*part-mag*.nii.gz" 2>/dev/null | wc -l)
        echo "    [OK] ${RTASK} part-mag (ya completo: ${rm_n} .nii.gz)"
      else
        echo "    Descargando ${RTASK} part-mag (5 ecos x runs)..."
        "$AWS" s3 sync --no-sign-request \
          --exclude "*" --include "func/*${RTASK}_*part-mag*" \
          "$S3/sub-${SUB}/ses-${DSES}/" "$SES_DIR/"
        compress_nii "$FUNC_DIR" "*${RTASK}_*part-mag*"
      fi

      # part-phase (solo si el sujeto la tiene publicada)
      if [ "${HAS_PHASE[$SUB]}" -eq 1 ]; then
        if is_complete "$FUNC_DIR" "*${RTASK}_*part-phase*.nii.gz" "*${RTASK}_*part-phase*.nii"; then
          rp_n=$(find "$FUNC_DIR" -name "*${RTASK}_*part-phase*.nii.gz" 2>/dev/null | wc -l)
          echo "    [OK] ${RTASK} part-phase (ya completo: ${rp_n} .nii.gz)"
        else
          echo "    Descargando ${RTASK} part-phase (5 ecos x runs)..."
          "$AWS" s3 sync --no-sign-request \
            --exclude "*" --include "func/*${RTASK}_*part-phase*" \
            "$S3/sub-${SUB}/ses-${DSES}/" "$SES_DIR/"
          compress_nii "$FUNC_DIR" "*${RTASK}_*part-phase*"
        fi
      else
        echo "    [SKIP] ${RTASK} part-phase (sub-${SUB} sin fase publicada -> NORDIC magnitude-only)"
      fi
    done
  done

  # Resumen del sujeto
  SUB_SIZE=$(du -sh "$LOCAL/sub-${SUB}/" 2>/dev/null | cut -f1)
  echo "  sub-${SUB} total en disco: ${SUB_SIZE:-pendiente}"
  echo ""
done

# ---- Resumen final ----
echo "============================================================"
echo " Descarga completada. Resumen por sujeto:"
echo "============================================================"
# Se descargan TODAS las tareas BOLDREST* de cada sesion de droga (part-mag
# para todos + part-phase solo en P4-P7). La validacion comprueba que no
# queden .nii sin comprimir y que, cuando hay fase, mag y phase coincidan
# en numero de archivos (necesario para NORDIC complex-valued).
TOTAL_OK=true

for SUB in P1 P2 P3 P4 P5 P6 P7; do
  SUB_DIR="$LOCAL/sub-${SUB}"
  if [ ! -d "$SUB_DIR" ]; then
    echo "  sub-${SUB}: NO DESCARGADO"
    TOTAL_OK=false
    continue
  fi

  ASES=${ANAT[$SUB]}
  ANAT_DIR="$SUB_DIR/ses-${ASES}/anat"
  SUB_SIZE=$(du -sh "$SUB_DIR" 2>/dev/null | cut -f1)
  NII_RAW=$(find "$SUB_DIR" -name "*.nii" -not -name "*.nii.gz" 2>/dev/null | wc -l)

  # Contar archivos por componente agregando todas las tareas REST
  N_ANAT=$(find "$ANAT_DIR" -name "*.nii.gz" 2>/dev/null | wc -l)
  N_FMAP=0; N_RM=0; N_RP=0
  for DSES in ${DRUG1[$SUB]} ${DRUG2[$SUB]}; do
    N_FMAP=$((N_FMAP + $(find "$SUB_DIR/ses-${DSES}/fmap" -name "*.nii.gz" 2>/dev/null | wc -l)))
    N_RM=$((N_RM + $(find "$SUB_DIR/ses-${DSES}/func" -name "*BOLDREST*part-mag*.nii.gz" 2>/dev/null | wc -l)))
    N_RP=$((N_RP + $(find "$SUB_DIR/ses-${DSES}/func" -name "*BOLDREST*part-phase*.nii.gz" 2>/dev/null | wc -l)))
  done
  N_TOTAL=$((N_ANAT + N_FMAP + N_RM + N_RP))

  # Verificar componentes minimos. Phase solo es obligatoria si HAS_PHASE=1.
  ISSUES=""
  PHASE_TAG=""
  [ "$NII_RAW" -gt 0 ] && ISSUES="${ISSUES} ${NII_RAW} .nii sin comprimir;"
  [ "$N_ANAT" -eq 0 ] && ISSUES="${ISSUES} falta anat;"
  [ "$N_FMAP" -eq 0 ] && ISSUES="${ISSUES} faltan fmap;"
  [ "$N_RM" -eq 0 ] && ISSUES="${ISSUES} faltan BOLDREST* mag;"
  if [ "${HAS_PHASE[$SUB]}" -eq 1 ]; then
    [ "$N_RP" -eq 0 ] && ISSUES="${ISSUES} faltan BOLDREST* phase;"
    [ "$N_RM" -ne "$N_RP" ] && ISSUES="${ISSUES} mag/phase desbalanceado (${N_RM}/${N_RP});"
    PHASE_TAG="complex-NORDIC"
  else
    PHASE_TAG="mag-only-NORDIC"
  fi

  if [ -n "$ISSUES" ]; then
    echo "  sub-${SUB}: ${SUB_SIZE}  (anat:${N_ANAT} fmap:${N_FMAP} REST:${N_RM}m+${N_RP}p = ${N_TOTAL}) [${PHASE_TAG}]  [⚠${ISSUES}]"
    TOTAL_OK=false
  else
    echo "  sub-${SUB}: ${SUB_SIZE}  (anat:${N_ANAT} fmap:${N_FMAP} REST:${N_RM}m+${N_RP}p = ${N_TOTAL}) [${PHASE_TAG}]  [OK]"
  fi
done

echo ""
TOTAL=$(du -sh "$LOCAL" 2>/dev/null | cut -f1)
echo "  TOTAL: ${TOTAL}"
echo ""

# Verificacion final
REMAINING=$(find "$LOCAL" -name "*.nii" -not -name "*.nii.gz" 2>/dev/null | wc -l)
if [ "$REMAINING" -gt 0 ]; then
  echo "  ⚠ ATENCION: quedan $REMAINING archivos .nii sin comprimir:"
  find "$LOCAL" -name "*.nii" -not -name "*.nii.gz" 2>/dev/null
  echo ""
fi

if [ "$TOTAL_OK" = true ] && [ "$REMAINING" -eq 0 ]; then
  echo "  ✓ Todos los archivos descargados y comprimidos. Listo para NORDIC + fMRIPrep."
else
  echo "  ⚠ Descarga incompleta. Re-ejecutar el script para completar."
fi
