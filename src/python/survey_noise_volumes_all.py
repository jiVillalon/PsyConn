"""QC ds006072 — barrido sistemático de noise volumes en todos los BOLDREST.

Diagnóstico complementario a detect_noise_volumes.py. Aquel se limitaba
a 4 runs anómalos y 2 referencias sanas (P6/P7). Este script recorre
TODOS los runs BOLDREST de TODOS los sujetos para verificar la hipótesis
pipeline §sec-nordic-magonly de que P1–P3 (mag-only) también llevan los
3 noise volumes terminales del protocolo NORDICME52mm — hipótesis
invalidada por sub-P2 ses-16 canary (ratio last3/analytic = 0.999).

Lee solo 4 frames por run (central + 3 últimos) vía img.dataobj para
memoria constante. Redirige sub-P2 ses-16 y sub-P4 ses-6 run-1 a sus
respectivos .pre-nordic (post-NORDIC overwriteó el original).

Reporta por run:
  Q, ratio_last3 (intensidad cerebral últimos 3 / central),
  veredicto: NOISE-OK (ratio<0.2) | NO-NOISE (ratio>0.5) | PARTIAL.

Uso:
    python D:/ProfessionalProyects/PsyLSD/src/python/survey_noise_volumes_all.py
"""

from __future__ import annotations

import functools
import glob
import gzip
import re
from collections import defaultdict
from pathlib import Path

import nibabel as nib
import numpy as np

print = functools.partial(print, flush=True)

BIDS = Path("D:/ProfessionalProyects/PsyLSD/data/openneuro/ds006072")
SUBJECTS = ["sub-P1", "sub-P2", "sub-P3", "sub-P4",
            "sub-P5", "sub-P6", "sub-P7"]

# Runs ya procesados con NORDIC (leer el .pre-nordic en su lugar)
FORCE_PRE_NORDIC_KEYS = {
    ("sub-P2", "ses-16", "BOLDREST1", "run-1"),
    ("sub-P4", "ses-6",  "BOLDREST1", "run-1"),
}

# Veredicto
NOISE_THR  = 0.20   # ratio < 0.20  → hay noise volumes al final
NOSIGN_THR = 0.50   # ratio > 0.50  → NO hay noise (frames son señal)


def parse_path(p: Path):
    """Extrae (subj, ses, task, run, echo) del nombre BIDS."""
    name = p.name
    subj = re.search(r"(sub-P\d+)", name).group(1)
    ses  = re.search(r"(ses-\d+)", name).group(1)
    task = re.search(r"task-([A-Za-z0-9]+)", name).group(1)
    run  = re.search(r"(run-\d+)", name).group(1)
    echo = re.search(r"echo-(\d+)", name).group(1)
    return subj, ses, task, run, echo


def load_any_gz(path: Path):
    """Carga NIfTI gzipped con sufijo arbitrario (.nii.gz o .pre-nordic)."""
    if str(path).endswith(".pre-nordic"):
        with open(path, "rb") as f:
            data = gzip.decompress(f.read())
        return nib.Nifti1Image.from_bytes(data)
    return nib.load(str(path))


def analyze_run(path: Path) -> dict | None:
    try:
        img = load_any_gz(path)
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}

    shape = img.shape
    if len(shape) != 4:
        return {"error": f"not 4D: {shape}"}
    nt = shape[3]

    dataobj = img.dataobj
    # Frame central para máscara cerebral rápida
    mid = np.asarray(dataobj[..., nt // 2], dtype=np.float32)
    mid_max = float(mid.max())
    brain = mid > (0.20 * mid_max)
    n_brain = int(brain.sum())
    if n_brain < 1000:
        return {"error": f"brain mask too small: {n_brain}"}

    analytic_intensity = float(mid[brain].mean())

    # Media cerebral por frame en los últimos 3
    last3_means = []
    for k in (3, 2, 1):
        vol = np.asarray(dataobj[..., nt - k], dtype=np.float32)
        last3_means.append(float(vol[brain].mean()))

    ratio_last3 = float(np.mean(last3_means) / analytic_intensity)

    if ratio_last3 < NOISE_THR:
        verdict = "NOISE-OK"
    elif ratio_last3 > NOSIGN_THR:
        verdict = "NO-NOISE"
    else:
        verdict = "PARTIAL"

    return {
        "nt": nt,
        "analytic_intensity": analytic_intensity,
        "last3_means": last3_means,
        "ratio_last3": ratio_last3,
        "verdict": verdict,
    }


def resolve_path(subj, ses, task, run, echo) -> Path | None:
    """Localiza el fichero a analizar, con redirect a .pre-nordic si aplica."""
    base_glob = (f"{BIDS}/{subj}/{ses}/func/{subj}_{ses}_"
                 f"task-{task}_dir-*_{run}_echo-{echo}_part-mag_bold.nii.gz")
    key = (subj, ses, task, run)
    if key in FORCE_PRE_NORDIC_KEYS:
        hits = glob.glob(base_glob + ".pre-nordic")
    else:
        hits = [h for h in glob.glob(base_glob) if not h.endswith(".pre-nordic")]
    return Path(hits[0]) if hits else None


def discover_runs(subj: str):
    """Enumera (ses, task, run) únicos del sujeto analizando echo-1."""
    pattern = f"{BIDS}/{subj}/*/func/{subj}_*_task-BOLDREST*_echo-1_part-mag_bold.nii.gz*"
    files = glob.glob(pattern)
    seen = set()
    out = []
    for f in files:
        p = Path(f.replace(".pre-nordic", ""))
        try:
            s, se, ta, ru, _ = parse_path(p)
        except AttributeError:
            continue
        key = (s, se, ta, ru)
        if key in seen:
            continue
        seen.add(key)
        out.append(key)
    out.sort()
    return out


def main():
    print("=" * 98)
    print("Barrido de noise volumes — todos los BOLDREST* runs (solo echo-1)")
    print("=" * 98)
    print(f"{'subj':6} {'ses':8} {'task':11} {'run':6} "
          f"{'Q':>4}  {'med_brain':>9}  {'last3_mean':>10}  "
          f"{'ratio':>7}  {'verdict':11}")
    print("-" * 98)

    summary = defaultdict(lambda: defaultdict(int))  # subj → verdict → count
    all_runs_by_subj = defaultdict(list)

    for subj in SUBJECTS:
        runs = discover_runs(subj)
        if not runs:
            print(f"{subj}  (sin runs)")
            continue
        for (s, se, ta, ru) in runs:
            p = resolve_path(s, se, ta, ru, echo="1")
            if p is None:
                print(f"{s:6} {se:8} {ta:11} {ru:6}  (no path)")
                continue
            res = analyze_run(p)
            if res is None or "error" in res:
                err = res.get("error", "unknown") if res else "None"
                print(f"{s:6} {se:8} {ta:11} {ru:6}  ERROR: {err}")
                summary[s]["ERROR"] += 1
                continue
            tag = res["verdict"]
            summary[s][tag] += 1
            all_runs_by_subj[s].append((se, ta, ru, res))
            l3_mean_str = f"{np.mean(res['last3_means']):.1f}"
            print(f"{s:6} {se:8} {ta:11} {ru:6} "
                  f"{res['nt']:>4}  {res['analytic_intensity']:>9.1f}  "
                  f"{l3_mean_str:>10}  {res['ratio_last3']:>7.4f}  "
                  f"{tag:11}")

    print("-" * 98)
    print("\nResumen por sujeto:")
    print(f"{'subj':6}  {'NOISE-OK':>10}  {'PARTIAL':>10}  "
          f"{'NO-NOISE':>10}  {'ERROR':>6}  {'total':>6}")
    print("-" * 65)
    grand = defaultdict(int)
    for subj in SUBJECTS:
        row = summary.get(subj, {})
        nok  = row.get("NOISE-OK", 0)
        par  = row.get("PARTIAL", 0)
        non  = row.get("NO-NOISE", 0)
        err  = row.get("ERROR", 0)
        total = nok + par + non + err
        print(f"{subj:6}  {nok:>10d}  {par:>10d}  {non:>10d}  "
              f"{err:>6d}  {total:>6d}")
        grand["NOISE-OK"] += nok
        grand["PARTIAL"]  += par
        grand["NO-NOISE"] += non
        grand["ERROR"]    += err

    print("-" * 65)
    total_all = sum(grand.values())
    print(f"{'TOTAL':6}  {grand['NOISE-OK']:>10d}  {grand['PARTIAL']:>10d}  "
          f"{grand['NO-NOISE']:>10d}  {grand['ERROR']:>6d}  {total_all:>6d}")

    print("\n" + "=" * 98)
    print("Implicación:")
    print("  * NO-NOISE runs en P1-P3 → pipeline §sec-nordic-magonly asumía")
    print("    incorrectamente que todos los sujetos tienen 3 noise volumes.")
    print("  * Si NO-NOISE es sistemático en P1-P3 → NORDIC inválido con")
    print("    noise_volume_last=3: σ se estima de un frame de señal, el")
    print("    umbral se infla ~20× y se corta BOLD.")
    print("  * Estrategia alternativa necesaria para P1-P3 (p. ej. σ desde")
    print("    residuos tras tedana o desde ROI CSF, o skip de NORDIC).")
    print("=" * 98)


if __name__ == "__main__":
    main()
