"""QC dataset ds006072 — detección empírica de noise volumes NORDIC.

Referenciado desde notebooks/PsiloConn_1.0.qmd §sec-nordic-excluded, paso 2
(detección de noise volumes por intensidad media). Complementa al script
inspect_nordic_anomalies.py: una vez descartada la corrupción de descarga,
determina si los 3 volúmenes de ruido del protocolo NORDIC están presentes
al final de cada run anómalo.

Lógica: los volúmenes de ruido NORDIC se adquieren sin pulso RF, por lo que
su intensidad media cerebral cae ~1-2 órdenes de magnitud respecto a
volúmenes con excitación. Para cada run calcula la serie temporal de
intensidad media dentro de una máscara cerebral rápida (umbral 0.2·max del
frame central) y reporta el ratio de los primeros y últimos 3 frames frente
a la mediana global.

Criterios de decisión:
  * ratio últimos 3 << 0.5  → 3 noise volumes al FINAL (protocolo normal).
  * ratio últimos 3 ≈ 1.0   → scan abortado antes del bloque de ruido; el
                              run NO es válido para NORDIC.
  * ratio primeros 3 << 0.5 → noise al INICIO (raro; no observado).

Incluye dos referencias sanas (P6 ses-5 y P7 ses-11, ambas n=513) para
validar el método sobre runs con los 3 noise volumes presentes.

Uso:
    python D:/ProfessionalProyects/PsyLSD/src/python/detect_noise_volumes.py
"""

from __future__ import annotations

import functools
from pathlib import Path

import nibabel as nib
import numpy as np

print = functools.partial(print, flush=True)

BIDS = Path("D:/ProfessionalProyects/PsyLSD/data/openneuro/ds006072")

RUNS = [
    # etiqueta, subj, ses, task, run, direction
    ("P6 ses-9  BOLDREST1 (n=208)", "sub-P6", "ses-9",  "BOLDREST1", "run-1", "PA"),
    ("P6 ses-9  BOLDREST2 (n=135)", "sub-P6", "ses-9",  "BOLDREST2", "run-1", "PA"),
    ("P7 ses-7  BOLDREST1 (n=516)", "sub-P7", "ses-7",  "BOLDREST1", "run-1", "PA"),
    ("P7 ses-7  BOLDREST2 (n=516)", "sub-P7", "ses-7",  "BOLDREST2", "run-1", "PA"),
    # Referencias sanas para calibrar (deben tener 3 noise al final)
    ("REF P6 ses-5 BOLDREST1 (n=513)", "sub-P6", "ses-5", "BOLDREST1", "run-1", "PA"),
    ("REF P7 ses-11 BOLDREST1 (n=513)", "sub-P7", "ses-11", "BOLDREST1", "run-1", "PA"),
]


def path_for(subj: str, ses: str, task: str, run: str, direction: str) -> Path:
    base = f"{subj}_{ses}_task-{task}_dir-{direction}_{run}_echo-1_part-mag_bold.nii.gz"
    return BIDS / subj / ses / "func" / base


def analyze(nii_path: Path, label: str) -> None:
    print("\n" + "-" * 70)
    print(f"{label}")
    print(f"  path: {nii_path.name}")
    img = nib.load(str(nii_path))
    data = img.get_fdata(dtype=np.float32, caching="unchanged")
    T = data.shape[3]
    print(f"  shape: {data.shape}")

    # Máscara cerebral rápida: umbral = 20% del max del frame medio
    mid_frame = data[..., T // 2]
    thresh = 0.2 * np.max(mid_frame)
    mask = mid_frame > thresh
    n_mask = int(mask.sum())
    print(f"  voxeles en máscara: {n_mask} (umbral={thresh:.1f})")

    # Serie temporal: media dentro de la máscara
    ts = data[mask].mean(axis=0)
    median_ts = float(np.median(ts))

    # Detección: frames con intensidad < 20% de la mediana
    low_frames = np.where(ts < 0.2 * median_ts)[0]

    print(f"  mediana intensidad (cerebro): {median_ts:.1f}")
    print(f"  frames con intensidad < 20% mediana: {low_frames.tolist()}")
    if len(low_frames) > 0:
        contiguous_end = T - 1 in low_frames and np.all(
            np.diff(low_frames[-3:]) == 1) if len(low_frames) >= 3 else False
        contiguous_start = 0 in low_frames and np.all(
            np.diff(low_frames[:3]) == 1) if len(low_frames) >= 3 else False
        print(f"  ¿bloque contiguo al FINAL? {contiguous_end}")
        print(f"  ¿bloque contiguo al INICIO? {contiguous_start}")

    # Muestra los últimos 10 y primeros 10 frames explícitamente
    print(f"  primeros 10 frames: "
          f"{[f'{v:.0f}' for v in ts[:10]]}")
    print(f"  últimos 10 frames:  "
          f"{[f'{v:.0f}' for v in ts[-10:]]}")
    # Ratio primeros/últimos contra mediana
    ratio_first3 = ts[:3].mean() / median_ts
    ratio_last3  = ts[-3:].mean() / median_ts
    print(f"  <intensidad primeros 3> / mediana = {ratio_first3:.3f}  "
          f"(ruido si << 0.5)")
    print(f"  <intensidad últimos  3> / mediana = {ratio_last3:.3f}  "
          f"(ruido si << 0.5)")


def main():
    print("=" * 70)
    print("Detección empírica de noise volumes por intensidad media")
    print("=" * 70)
    for label, subj, ses, task, run, direction in RUNS:
        p = path_for(subj, ses, task, run, direction)
        if not p.exists():
            print(f"\n!! No existe: {p}")
            continue
        try:
            analyze(p, label)
        except Exception as e:
            print(f"  ERROR analizando: {type(e).__name__}: {e}")

    print("\n" + "=" * 70)
    print("Interpretación:")
    print("  - <ratio_últimos_3> << 0.5 → hay 3 noise volumes al FINAL (normal).")
    print("  - <ratio_primeros_3> << 0.5 → hay noise al INICIO (raro).")
    print("  - Si NINGUNO de los dos es < 0.5, el scan probablemente se abortó")
    print("    antes del bloque de ruido → excluir ese run de NORDIC.")
    print("=" * 70)


if __name__ == "__main__":
    main()
