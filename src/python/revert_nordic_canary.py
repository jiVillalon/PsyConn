"""Revierte los canarys NORDIC de ds006072 al estado pre-NORDIC.

Descubre automáticamente los canarys escaneando BIDS en busca de backups
`<base>.nii.gz.pre-nordic` (generados por el chunk NORDIC con
KEEP_BACKUP=True), restaura los ficheros `_part-mag_bold.nii.gz` y
elimina los campos NORDIC de los JSON sidecar para romper la idempotencia
y permitir re-ejecución con el nuevo esquema de dos ejes
(§sec-nordic-magonly).

Cada canary se identifica por el tuple (subj, ses, task, run) y agrupa
todos los ecos cuyo backup `.pre-nordic` está presente. El modo
(magnitude-only vs complex) se infiere de la presencia del
`_part-phase_bold.nii.gz` correspondiente: si la fase aún existe en
disco, el canary puede re-correrse como complex; si no, como
magnitude-only.

Protocolo por fichero:
  1. Validar que `.pre-nordic` existe y abre como NIfTI 4D íntegro.
  2. Validar que el post-NORDIC actual existe (no re-revertir).
  3. Eliminar el post-NORDIC.
  4. Renombrar `.pre-nordic` → `.nii.gz`.
  5. Re-escribir el JSON sidecar eliminando los campos NORDIC.

Usage:
    python D:/ProfessionalProyects/PsyConn/src/python/revert_nordic_canary.py --dry-run
    python D:/ProfessionalProyects/PsyConn/src/python/revert_nordic_canary.py --execute
"""

from __future__ import annotations

import argparse
import functools
import glob
import gzip
import json
import os
import re
import sys
from pathlib import Path

import nibabel as nib

print = functools.partial(print, flush=True)

BIDS = Path("F:/JIVillL/openneuro/ds006072")

# Regex para parsear el basename de un backup pre-nordic. Captura
# subject, session, task, run y echo; dir-* se ignora porque puede ser
# AP o PA según el canary.
PRE_NORDIC_RE = re.compile(
    r"^(?P<subj>sub-[^_]+)_(?P<ses>ses-[^_]+)_task-(?P<task>[^_]+)_"
    r"dir-[^_]+_(?P<run>run-[^_]+)_echo-(?P<echo>\d+)_"
    r"part-mag_bold\.nii\.gz\.pre-nordic$"
)

# Campos añadidos por mark_json_nordic que hay que eliminar del sidecar.
# Incluye los dos nuevos del esquema de dos ejes (NoiseVolumesDetected,
# NoiseLast3RatioToCentral) por si el canary se re-ejecutase con el
# chunk nuevo antes del revert.
NORDIC_JSON_FIELDS = [
    "DenoisingMethod",
    "NORDICMode",
    "DenoisingSoftware",
    "NORDICArgs",
    "NoiseVolumesDetected",
    "NoiseLast3RatioToCentral",
    "NoiseVolumesUsed",
    "NoiseVolumesTrimmed",
    "NumVolumesBeforeNORDIC",
    "NumVolumesAfterNORDIC",
    "DenoisingDate",
]


def discover_canarys(bids_root: Path) -> list[dict]:
    """Auto-detecta canarys NORDIC escaneando los `.pre-nordic` bajo BIDS.

    Cada canary se identifica por el tuple (subj, ses, task, run); los
    ecos se acumulan desde los backups presentes. El modo se infiere así:
      * complex          -> existe algún `_part-phase_bold.nii.gz` para
                            ese (subj, ses, task, run).
      * magnitude-only   -> no hay fase en disco.
    """
    groups: dict[tuple, dict] = {}
    for p in sorted(bids_root.rglob("*_part-mag_bold.nii.gz.pre-nordic")):
        m = PRE_NORDIC_RE.match(p.name)
        if not m:
            print(f"  [!] backup no parseable, ignorado: {p}")
            continue
        key = (m["subj"], m["ses"], m["task"], m["run"])
        grp = groups.setdefault(key, {
            "subj": m["subj"], "ses": m["ses"], "task": m["task"],
            "run": m["run"], "echoes": [],
        })
        grp["echoes"].append(int(m["echo"]))

    canarys = []
    for key, grp in groups.items():
        grp["echoes"] = sorted(set(grp["echoes"]))
        phase_pat = (f"{bids_root}/{grp['subj']}/{grp['ses']}/func/"
                     f"{grp['subj']}_{grp['ses']}_task-{grp['task']}_dir-*_"
                     f"{grp['run']}_echo-*_part-phase_bold.nii.gz")
        has_phase = any(not h.endswith(".pre-nordic") for h in glob.glob(phase_pat))
        grp["mode"] = "complex" if has_phase else "magnitude-only"
        canarys.append(grp)

    canarys.sort(key=lambda c: (c["subj"], c["ses"], c["task"], c["run"]))
    return canarys


def find_mag(canary: dict, echo: int) -> Path | None:
    """Localiza el `_part-mag_bold.nii.gz` del eco sin asumir dirección AP/PA."""
    pat = (f"{BIDS}/{canary['subj']}/{canary['ses']}/func/"
           f"{canary['subj']}_{canary['ses']}_task-{canary['task']}_dir-*_"
           f"{canary['run']}_echo-{echo}_part-mag_bold.nii.gz")
    hits = [h for h in glob.glob(pat) if not h.endswith(".pre-nordic")]
    return Path(hits[0]) if hits else None


def load_pre_nordic(path: Path) -> nib.Nifti1Image:
    """Carga un NIfTI gzipped con sufijo `.pre-nordic` (nibabel no lo reconoce)."""
    with open(path, "rb") as f:
        raw = gzip.decompress(f.read())
    return nib.Nifti1Image.from_bytes(raw)


def strip_nordic_fields_from_json(json_path: Path) -> list[str]:
    """Elimina los campos NORDIC del sidecar preservando formato tipo BIDS.

    Opera sobre el texto crudo con regex, lo mismo que set_json_field en
    el chunk NORDIC, para no reindentar ni re-encodear el resto de claves
    (preserva PatchBytes y garantiza estabilidad de git diff).

    Devuelve la lista de campos efectivamente eliminados.
    """
    text = json_path.read_text(encoding="utf-8")
    removed = []

    for field in NORDIC_JSON_FIELDS:
        if f'"{field}"' not in text:
            continue
        # Captura coma + whitespace previo (si la hay) + "field": <value>
        # <value> puede ser objeto {...}, array [...], string "...", número,
        # true/false/null. Usamos un matcher no-greedy con alternativas
        # para cubrir los tipos que realmente escribe mark_json_nordic.
        pattern = (
            rf',\s*\n[ \t]*"{re.escape(field)}"\s*:\s*'
            rf'(?:\{{[^{{}}]*\}}|\[[^\[\]]*\]|"[^"]*"|-?\d+(?:\.\d+)?|true|false|null)'
        )
        new_text, n = re.subn(pattern, "", text, count=1, flags=re.DOTALL)
        if n == 0:
            # Fallback: podría ser el primer campo del bloque NORDIC sin
            # coma previa (no debería ocurrir con el formato actual, pero
            # por robustez). Intentar coma POSTERIOR en su lugar.
            pattern2 = (
                rf'"{re.escape(field)}"\s*:\s*'
                rf'(?:\{{[^{{}}]*\}}|\[[^\[\]]*\]|"[^"]*"|-?\d+(?:\.\d+)?|true|false|null)'
                rf',?\s*\n'
            )
            new_text, n = re.subn(pattern2, "", text, count=1, flags=re.DOTALL)
        if n == 1:
            text = new_text
            removed.append(field)
        else:
            print(f"    [!] no se pudo eliminar {field!r} de {json_path.name}")

    # Validar que el resultado es JSON parseable
    try:
        parsed = json.loads(text)
    except json.JSONDecodeError as e:
        raise RuntimeError(f"JSON corrupto tras strip en {json_path}: {e}")
    for field in removed:
        if field in parsed:
            raise RuntimeError(f"Strip incompleto: {field} sigue en {json_path}")

    json_path.write_text(text, encoding="utf-8")
    return removed


def validate_canary(canary: dict) -> list[dict]:
    """Construye el plan de revert por eco y valida pre-requisitos."""
    plan = []
    for echo in canary["echoes"]:
        mag = find_mag(canary, echo)
        if mag is None:
            raise FileNotFoundError(
                f"Eco {echo} no encontrado para {canary['subj']} {canary['ses']} "
                f"{canary['task']} {canary['run']}"
            )
        pre = Path(str(mag) + ".pre-nordic")
        if not pre.exists():
            raise FileNotFoundError(f"Backup pre-NORDIC ausente: {pre}")
        if not mag.exists():
            raise FileNotFoundError(f"Post-NORDIC ausente (ya revertido?): {mag}")

        # Validar que el pre-nordic abre y es 4D
        try:
            img = load_pre_nordic(pre)
            shape = tuple(img.shape)
        except Exception as e:
            raise RuntimeError(f"pre-NORDIC corrupto en {pre}: {e}")
        if len(shape) != 4:
            raise ValueError(f"pre-NORDIC no es 4D: {shape} en {pre}")

        # Validar fase para canary complex (debe existir el .nii.gz)
        phase = Path(str(mag).replace("_part-mag_", "_part-phase_"))
        if canary["mode"] == "complex" and not phase.exists():
            raise FileNotFoundError(
                f"Canary complex pero falta fase: {phase} "
                "(DROP_PHASE borró la fase tras NORDIC; no se puede re-correr)"
            )

        json_path = Path(str(mag).replace(".nii.gz", ".json"))
        if not json_path.exists():
            raise FileNotFoundError(f"JSON sidecar ausente: {json_path}")

        plan.append({
            "echo": echo,
            "mag": mag,
            "pre": pre,
            "phase": phase if canary["mode"] == "complex" else None,
            "json": json_path,
            "pre_shape": shape,
            "pre_bytes": pre.stat().st_size,
            "post_bytes": mag.stat().st_size,
        })
    return plan


def print_plan(canary: dict, plan: list[dict]) -> None:
    print(f"\n--- {canary['subj']} {canary['ses']} {canary['task']} {canary['run']} "
          f"[{canary['mode']}, {len(plan)} ecos] ---")
    for step in plan:
        phase_tag = ""
        if canary["mode"] == "complex" and step["phase"] is not None:
            phase_tag = f"  phase={'OK' if step['phase'].exists() else 'MISSING'}"
        print(f"  echo-{step['echo']}: shape={step['pre_shape']}  "
              f"pre={step['pre_bytes']/1e6:7.1f} MB  "
              f"post={step['post_bytes']/1e6:7.1f} MB{phase_tag}")


def execute_revert(canary: dict, plan: list[dict]) -> None:
    print(f"\n>>> ejecutando revert: {canary['subj']} {canary['ses']} "
          f"{canary['task']} {canary['run']}")
    for step in plan:
        mag = step["mag"]
        pre = step["pre"]
        json_path = step["json"]
        print(f"  echo-{step['echo']}:")

        # 1) Eliminar post-NORDIC
        print(f"    - rm  {mag.name}  ({step['post_bytes']/1e6:.1f} MB)")
        os.remove(mag)

        # 2) Renombrar pre-nordic -> nii.gz (atómico dentro del mismo FS)
        print(f"    - mv  {pre.name}  ->  {mag.name}")
        os.rename(pre, mag)

        # 3) Validar que el resultado abre como NIfTI estándar ya
        try:
            img = nib.load(str(mag))
            shape_after = tuple(img.shape)
        except Exception as e:
            raise RuntimeError(f"Post-revert unreadable: {mag}: {e}")
        if shape_after != step["pre_shape"]:
            raise RuntimeError(
                f"Shape mismatch post-revert: pre={step['pre_shape']} "
                f"post={shape_after} en {mag}"
            )

        # 4) Strip campos NORDIC del JSON
        removed = strip_nordic_fields_from_json(json_path)
        print(f"    - json: eliminados {len(removed)} campos: {removed}")

    print(f"<<< revert completado: {canary['subj']} "
          f"{canary['ses']} {canary['task']} {canary['run']}")


def main():
    ap = argparse.ArgumentParser()
    g = ap.add_mutually_exclusive_group(required=True)
    g.add_argument("--dry-run", action="store_true",
                   help="Solo validar y mostrar plan, sin tocar ficheros.")
    g.add_argument("--execute", action="store_true",
                   help="Ejecutar el revert (destructivo sobre post-NORDIC).")
    args = ap.parse_args()

    print("=" * 78)
    print("Revert canarys NORDIC -> estado pre-NORDIC")
    print("=" * 78)
    print(f"BIDS root: {BIDS}")

    canarys = discover_canarys(BIDS)
    if not canarys:
        print("\nNo se encontró ningún backup `.pre-nordic` bajo BIDS. Nada que revertir.")
        return

    print(f"\nDescubiertos {len(canarys)} canary(s):")
    for c in canarys:
        print(f"  - {c['subj']} {c['ses']} {c['task']} {c['run']}  "
              f"[{c['mode']}]  ecos={c['echoes']}")

    plans = []
    for canary in canarys:
        plan = validate_canary(canary)
        print_plan(canary, plan)
        plans.append((canary, plan))

    if args.dry_run:
        print("\n[dry-run] validación OK, no se ha tocado ningún fichero.")
        return

    print("\n[EXECUTE] procediendo con la operación destructiva...")
    for canary, plan in plans:
        execute_revert(canary, plan)

    print("\n" + "=" * 78)
    print("Revert completado. Los sidecar JSON ya no contienen")
    print("DenoisingMethod=NORDIC, así que la idempotencia del chunk no los")
    print("saltará en la próxima ejecución.")
    print("=" * 78)


if __name__ == "__main__":
    sys.exit(main() or 0)
