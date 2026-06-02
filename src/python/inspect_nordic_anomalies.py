"""QC dataset ds006072 — inspección de integridad y sesiones anómalas.

Referenciado desde notebooks/PsiloConn_1.0.qmd §sec-nordic-excluded, paso 1
(descartar corrupción de descarga). Inspecciona los runs detectados por el
dry-run de NORDIC con n_frames ≠ 513:
  - sub-P6 ses-9  (n=208 y n=135): scans potencialmente abortados.
  - sub-P7 ses-7  (n=516):         3 frames extra vs protocolo nominal.

Para cada run anómalo:
  1. Lee los campos BIDS relevantes del JSON sidecar.
  2. Carga profundamente el NIfTI (gzip íntegro + header + array completo).
     Si cualquiera de los tres falla → descarga corrupta.
  3. Calcula el ratio de tamaño del fichero frente a un run sano del mismo
     sujeto; si el ratio no escala con el ratio de frames → truncado.
  4. Lee CHANGES y scans.tsv del dataset por si la anomalía está documentada.

No modifica nada; sólo imprime el informe a stdout.

Uso:
    python D:/ProfessionalProyects/PsyLSD/src/python/inspect_nordic_anomalies.py
"""

from __future__ import annotations

import functools
import glob
import gzip
import json
import os
import traceback
from pathlib import Path
from typing import Any

import nibabel as nib
import numpy as np

print = functools.partial(print, flush=True)

BIDS = Path("D:/ProfessionalProyects/PsyLSD/data/openneuro/ds006072")

# Runs anómalos detectados en el dry-run
ANOMALIES = [
    ("sub-P6", "ses-9",  "BOLDREST1", "run-1", 208, "PA"),
    ("sub-P6", "ses-9",  "BOLDREST2", "run-1", 135, "PA"),
    ("sub-P7", "ses-7",  "BOLDREST1", "run-1", 516, "PA"),
    ("sub-P7", "ses-7",  "BOLDREST2", "run-1", 516, "PA"),
]

# Campos BIDS relevantes para el diagnóstico
RELEVANT_JSON_FIELDS = [
    "RepetitionTime",
    "NumberOfVolumesDiscardedByScanner",
    "NumberOfVolumesDiscardedByUser",
    "DelayAfterTrigger",
    "AcquisitionDuration",
    "TaskName",
    "PhaseEncodingDirection",
    "SliceTiming",
    "EchoTime",
    "PartialFourier",
    "MultibandAccelerationFactor",
]


def short_json(meta: dict[str, Any]) -> dict[str, Any]:
    """Devuelve sólo los campos relevantes, acortando SliceTiming."""
    out = {k: meta.get(k) for k in RELEVANT_JSON_FIELDS if k in meta}
    if "SliceTiming" in out and isinstance(out["SliceTiming"], list):
        st = out["SliceTiming"]
        out["SliceTiming"] = f"<list len={len(st)}, min={min(st):.4f}, max={max(st):.4f}>"
    # también añadimos cualquier clave que contenga 'NonSteadyState'
    for k, v in meta.items():
        if "NonSteadyState" in k or "Discarded" in k:
            out.setdefault(k, v)
    return out


def load_nifti_deeply(path: Path) -> dict[str, Any]:
    """Carga header + data (completo) y detecta si el fichero está corrupto.

    Si el .nii.gz está truncado en disco (download incompleto) la carga del
    array o la descompresión gzip fallará — lo capturamos aquí.
    """
    report: dict[str, Any] = {"path": str(path), "exists": path.exists()}
    if not path.exists():
        return report
    report["filesize_bytes"] = path.stat().st_size
    report["filesize_MB"] = round(path.stat().st_size / (1024 * 1024), 2)

    # Prueba 1: leer el gzip entero a memoria (detecta truncado)
    try:
        with gzip.open(path, "rb") as f:
            raw = f.read()
        report["gzip_ok"] = True
        report["uncompressed_bytes"] = len(raw)
    except Exception as e:
        report["gzip_ok"] = False
        report["gzip_error"] = f"{type(e).__name__}: {e}"
        return report  # no sigas si el gzip no abre

    # Prueba 2: header y forma
    try:
        img = nib.load(str(path))
        report["shape"] = tuple(img.shape)
        report["zooms"] = tuple(float(z) for z in img.header.get_zooms())
        report["dtype"] = str(img.header.get_data_dtype())
    except Exception as e:
        report["header_error"] = f"{type(e).__name__}: {e}"
        return report

    # Prueba 3: cargar el array completo (detecta datos incompletos aunque
    # el gzip en sí esté cerrado limpiamente)
    try:
        data = img.get_fdata(dtype=np.float32)
        report["data_ok"] = True
        report["data_shape"] = tuple(data.shape)
        # sanity: shape header vs data
        if tuple(data.shape) != tuple(img.shape):
            report["data_shape_mismatch"] = True
    except Exception as e:
        report["data_ok"] = False
        report["data_error"] = f"{type(e).__name__}: {e}"
    return report


def find_reference_run(subj: str, exclude_ses: str) -> Path | None:
    """Devuelve un part-mag de otra sesión del mismo sujeto, como referencia
    de 'run sano' (n_in=513)."""
    pattern = str(BIDS / subj / "ses-*" / "func" /
                  f"{subj}_ses-*_task-BOLDREST1_*_run-1_echo-1_part-mag_bold.nii.gz")
    for p in sorted(glob.glob(pattern)):
        if f"_{exclude_ses}_" not in p and f"/{exclude_ses}/" not in p.replace("\\", "/"):
            return Path(p)
    return None


def inspect_session_metadata(subj: str, ses: str) -> None:
    """Lee scans.tsv y CHANGES del dataset buscando menciones a esta sesión."""
    scans_tsv = BIDS / subj / ses / f"{subj}_{ses}_scans.tsv"
    print(f"\n  -- Metadatos de sesión --")
    print(f"  scans.tsv: {scans_tsv}  (exists={scans_tsv.exists()})")
    if scans_tsv.exists():
        with open(scans_tsv, encoding="utf-8") as f:
            content = f.read()
        print("  Contenido de scans.tsv:")
        for line in content.splitlines():
            print(f"    {line}")


def inspect_dataset_changes() -> None:
    """Lee el CHANGES del dataset por si hay una entrada relevante."""
    for candidate in ["CHANGES", "CHANGES.md", "README"]:
        p = BIDS / candidate
        if p.exists():
            print(f"\n--- {p} (primeras 40 líneas) ---")
            with open(p, encoding="utf-8", errors="replace") as f:
                for i, line in enumerate(f):
                    if i >= 40:
                        print("    ...")
                        break
                    print(f"  {line.rstrip()}")


def run_name(subj: str, ses: str, task: str, run: str, direction: str) -> str:
    return f"{subj}_{ses}_task-{task}_dir-{direction}_{run}_echo-1_part-mag_bold"


def main():
    print("=" * 70)
    print("Inspección de anomalías NORDIC dry-run")
    print("=" * 70)
    print(f"BIDS: {BIDS}")

    inspect_dataset_changes()

    for subj, ses, task, run, expected_n, direction in ANOMALIES:
        base = run_name(subj, ses, task, run, direction)
        mag_nii  = BIDS / subj / ses / "func" / f"{base}.nii.gz"
        mag_json = BIDS / subj / ses / "func" / f"{base}.json"
        phase_nii = BIDS / subj / ses / "func" / (
            base.replace("_part-mag_", "_part-phase_") + ".nii.gz"
        )

        print("\n" + "=" * 70)
        print(f"Anómalo: {subj} / {ses} / task-{task} / {run}   (dry-run reportó n={expected_n})")
        print("=" * 70)

        # --- JSON sidecar del run anómalo ---
        print("\n-- JSON sidecar (campos relevantes) --")
        if mag_json.exists():
            try:
                with open(mag_json, encoding="utf-8") as f:
                    meta = json.load(f)
                for k, v in short_json(meta).items():
                    print(f"  {k}: {v}")
                tr = meta.get("RepetitionTime")
                if tr:
                    print(f"  Duración esperada si n={expected_n}: {tr * expected_n:.1f} s")
                    print(f"  Duración esperada si n=513:          {tr * 513:.1f} s")
            except Exception:
                traceback.print_exc()
        else:
            print(f"  !! JSON no encontrado: {mag_json}")

        # --- NIfTI de magnitud: carga profunda ---
        print("\n-- NIfTI magnitud (integridad + shape) --")
        rep = load_nifti_deeply(mag_nii)
        for k, v in rep.items():
            print(f"  {k}: {v}")

        # --- NIfTI de fase (si existe, para complex mode) ---
        if phase_nii.exists():
            print("\n-- NIfTI fase (integridad + shape) --")
            rep_ph = load_nifti_deeply(phase_nii)
            for k, v in rep_ph.items():
                print(f"  {k}: {v}")

        # --- Referencia: otro run del mismo sujeto ---
        ref = find_reference_run(subj, ses)
        if ref:
            print(f"\n-- Referencia (run sano del mismo sujeto): {ref.name} --")
            rep_ref = load_nifti_deeply(ref)
            for k in ("filesize_MB", "shape", "dtype"):
                if k in rep_ref:
                    print(f"  ref.{k}: {rep_ref[k]}")

            # Ratio de tamaño esperado vs real (detecta truncado)
            if ("filesize_bytes" in rep and "filesize_bytes" in rep_ref
                    and "shape" in rep and "shape" in rep_ref):
                ref_frames = rep_ref["shape"][3] if len(rep_ref["shape"]) == 4 else None
                ano_frames = rep["shape"][3]    if len(rep["shape"])    == 4 else None
                if ref_frames and ano_frames:
                    ratio_expected = ano_frames / ref_frames
                    ratio_actual = rep["filesize_bytes"] / rep_ref["filesize_bytes"]
                    print(f"  ratio frames (ano/ref):   {ratio_expected:.3f}  "
                          f"({ano_frames}/{ref_frames})")
                    print(f"  ratio filesize (ano/ref): {ratio_actual:.3f}")
                    delta = abs(ratio_actual - ratio_expected)
                    if delta > 0.10:
                        print(f"  !! DISCREPANCIA GRANDE ({delta:.2f}) — posible truncado de descarga")
                    else:
                        print(f"  OK: tamaño coherente con número de frames declarado")

        # --- scans.tsv / CHANGES ---
        inspect_session_metadata(subj, ses)

    print("\n" + "=" * 70)
    print("Inspección terminada.")
    print("=" * 70)


if __name__ == "__main__":
    main()
