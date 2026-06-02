"""QC ds006072 — estadísticos del noise volume usado por NIFTI_NORDIC.

Referenciado desde notebooks/PsiloConn_1.0.qmd §sec-nordic-qc como
diagnóstico de sobre-denoising en modo magnitude-only (sub-P2 canary).

Contexto:
  NIFTI_NORDIC.m línea 488 selecciona UN único volumen para estimar σ:
    KSP2_NOISE = KSP2(:,:,:,end+1-ARG.noise_volume_last)
  Con noise_volume_last=3 y Q=513 esto es el frame 511 (1-indexed) =
  frame 510 (0-indexed) = primer frame del bloque de ruido terminal.
  σ = std(KSP2_NOISE(KSP2_NOISE~=0)). En complex se divide por sqrt(2).

Hipótesis a discriminar para el sobre-denoising en sub-P2 mag-only:
  H1 (Rayleigh): ruido puro, std(|noise|) ≈ 0.655·σ_true, σ subestimada
      → umbral bajo → sobre-corte. Firma: std(brain)/std(bg)≈1 en noise
      frame, mean(brain)≈mean(bg).
  H2 (señal residual): T1/T2* recovery incompleto, std inflada por
      contraste brain-bg, σ sobreestimada → UNDER-denoising (opuesto
      al observado, descarta H2 si se cumple OVER).
  H3 (scaling): scl_slope/inter distinto entre P2 y P4 y Octave no
      lo honra igual.

Lee los backups `.pre-nordic` (gzipped .nii.gz con sufijo atípico)
generados por el chunk NORDIC con KEEP_BACKUP=True en los canarys.

Uso:
    python D:/ProfessionalProyects/PsyLSD/src/python/inspect_noise_volume_stats.py
"""

from __future__ import annotations

import functools
import glob
import gzip
from pathlib import Path

import nibabel as nib
import numpy as np

print = functools.partial(print, flush=True)

BIDS = Path("D:/ProfessionalProyects/PsyLSD/data/openneuro/ds006072")
N_NOISE = 3  # protocolo NORDICME52mm

# (etiqueta, subj, ses, task, run, echo, modo)
CASES = [
    ("sub-P2 mag-only canary  echo-1", "sub-P2", "ses-16", "BOLDREST1", "run-1", 1, "mag-only"),
    ("sub-P2 mag-only canary  echo-3", "sub-P2", "ses-16", "BOLDREST1", "run-1", 3, "mag-only"),
    ("sub-P4 complex canary   echo-1", "sub-P4", "ses-6",  "BOLDREST1", "run-1", 1, "complex"),
    ("sub-P4 complex canary   echo-3", "sub-P4", "ses-6",  "BOLDREST1", "run-1", 3, "complex"),
]


def find_pre_nordic(subj, ses, task, run, echo):
    """Localiza el backup .pre-nordic independientemente de la dirección AP/PA."""
    pattern = (f"{BIDS}/{subj}/{ses}/func/{subj}_{ses}_task-{task}_dir-*_{run}"
               f"_echo-{echo}_part-mag_bold.nii.gz.pre-nordic")
    hits = glob.glob(pattern)
    return Path(hits[0]) if hits else None


def find_post_nordic(subj, ses, task, run, echo):
    """Localiza el archivo POST-NORDIC (el que sobrevivió al os.replace)."""
    pattern = (f"{BIDS}/{subj}/{ses}/func/{subj}_{ses}_task-{task}_dir-*_{run}"
               f"_echo-{echo}_part-mag_bold.nii.gz")
    hits = [h for h in glob.glob(pattern) if not h.endswith(".pre-nordic")]
    return Path(hits[0]) if hits else None


def load_nii_any_ext(path: Path):
    """Carga un NIfTI gzipped con cualquier sufijo (incluye `.pre-nordic`)."""
    with open(path, "rb") as f:
        compressed = f.read()
    decompressed = gzip.decompress(compressed)
    return nib.Nifti1Image.from_bytes(decompressed)


def describe_header(img):
    hdr = img.header
    scl_slope = hdr["scl_slope"]
    scl_inter = hdr["scl_inter"]
    return (f"  datatype={hdr.get_data_dtype()}  "
            f"scl_slope={scl_slope}  scl_inter={scl_inter}")


def inspect_frame(data, idx, label, brain, bg):
    """Estadísticos del frame idx dentro de máscaras brain y bg."""
    vol = data[..., idx]
    nz  = vol[vol != 0]
    sigma_global = float(nz.std())
    mu_brain, sd_brain = float(vol[brain].mean()), float(vol[brain].std())
    mu_bg,    sd_bg    = float(vol[bg].mean()),    float(vol[bg].std())
    ratio_std = sd_brain / max(sd_bg, 1e-9)
    ratio_mean = mu_brain / max(mu_bg, 1e-9)
    print(f"  {label} frame idx={idx}:")
    print(f"    std(nonzero)={sigma_global:10.3f}   "
          f"[n_nonzero={nz.size}]")
    print(f"    brain: mean={mu_brain:10.2f}  std={sd_brain:9.3f}")
    print(f"    bg   : mean={mu_bg:10.2f}  std={sd_bg:9.3f}")
    print(f"    std(brain)/std(bg)={ratio_std:6.2f}   "
          f"mean(brain)/mean(bg)={ratio_mean:6.2f}")
    return sigma_global, mu_brain, sd_brain, mu_bg, sd_bg


def analyze(label: str, subj, ses, task, run, echo, mode) -> None:
    print("\n" + "=" * 78)
    print(label)

    pre = find_pre_nordic(subj, ses, task, run, echo)
    post = find_post_nordic(subj, ses, task, run, echo)
    if pre is None:
        print(f"  !! No existe backup .pre-nordic para {subj} {ses} {task} {run} echo-{echo}")
        return
    print(f"  PRE : {pre.name}")
    if post is not None:
        print(f"  POST: {post.name}")

    img_pre = load_nii_any_ext(pre)
    data_pre = img_pre.get_fdata(dtype=np.float32, caching="unchanged")
    nx, ny, nz_, nt_pre = data_pre.shape
    print("-" * 78)
    print("  --- PRE-NORDIC ---")
    print(describe_header(img_pre))
    print(f"  shape: {data_pre.shape}")

    mid = data_pre[..., nt_pre // 2]
    brain = mid > 0.20 * mid.max()
    bg    = mid < 0.03 * mid.max()
    print(f"  brain voxels: {brain.sum():>7d}   bg voxels: {bg.sum():>7d}   "
          f"(mid_max={mid.max():.0f})")

    # Serie cerebral: identifica el bloque de ruido
    bts = np.median(data_pre[brain], axis=0)
    sig_ref = float(np.median(bts[: nt_pre - N_NOISE]))
    print(f"  mediana cerebral analítica    : {sig_ref:9.2f}")
    print(f"  mediana cerebral últimos 3    : "
          f"{[f'{v:9.2f}' for v in bts[-N_NOISE:]]}")
    print(f"  ratio last3/analytic-median   : "
          f"{bts[-N_NOISE:].mean()/sig_ref:8.4f}  "
          f"(→0.03–0.05 = noise OK)")

    # Frame que NIFTI_NORDIC usa para σ
    idx_noise = nt_pre - N_NOISE  # 0-idx, primer frame del bloque
    sigma_nordic, *_ = inspect_frame(
        data_pre, idx_noise, "NOISE (NORDIC σ source)", brain, bg)
    # Frame de señal de referencia (mitad del scan)
    _, mu_s_brain, sd_s_brain, *_ = inspect_frame(
        data_pre, nt_pre // 2, "SIGNAL (reference)", brain, bg)

    # σ efectiva según el modo
    if mode == "complex":
        sigma_used = sigma_nordic / np.sqrt(2)
        print(f"  σ efectiva (complex, /√2)                 : {sigma_used:10.3f}")
    else:
        sigma_used = sigma_nordic
        sigma_if_rayleigh = sigma_used / np.sqrt((4 - np.pi) / 2)
        print(f"  σ efectiva (mag-only, sin /√2)            : {sigma_used:10.3f}")
        print(f"  σ_true si |noise| fuese Rayleigh puro     : {sigma_if_rayleigh:10.3f}")
        print(f"    (factor 1/0.655 = 1.526 para ARG.factor_error)")

    # Ratio σ / señal cerebral (comparable entre sujetos)
    ratio_sig = sigma_used / sd_s_brain
    print(f"  σ_used / std(signal brain)               : {ratio_sig:8.4f}")
    print(f"  σ_used / mean(signal brain)              : "
          f"{sigma_used / mu_s_brain:8.4f}  "
          f"(proxy de 1/SNR por vóxel)")

    # --- POST-NORDIC (si existe) ---
    if post is not None:
        img_post = load_nii_any_ext(post)
        data_post = img_post.get_fdata(dtype=np.float32, caching="unchanged")
        print("\n  --- POST-NORDIC ---")
        print(describe_header(img_post))
        print(f"  shape: {data_post.shape}  "
              f"(esperado {nt_pre - N_NOISE} tras trim de 3 noise)")
        mid_p = data_post[..., data_post.shape[3] // 2]
        brain_p = mid_p > 0.20 * mid_p.max()
        mu_sig_post = float(data_post[..., data_post.shape[3] // 2][brain_p].mean())
        sd_sig_post = float(data_post[..., data_post.shape[3] // 2][brain_p].std())
        print(f"  signal frame brain: mean={mu_sig_post:9.2f}  "
              f"std={sd_sig_post:8.3f}")
        print(f"  ratio std_post / std_pre (signal frame)   : "
              f"{sd_sig_post / sd_s_brain:6.4f}  "
              f"(<1 → denoising; <<0.5 → sobre-corte)")


def main():
    print("=" * 78)
    print("Diagnóstico σ_NORDIC: sub-P2 mag-only vs sub-P4 complex (desde PRE-NORDIC)")
    print("=" * 78)
    for label, subj, ses, task, run, echo, mode in CASES:
        try:
            analyze(label, subj, ses, task, run, echo, mode)
        except Exception as e:
            print(f"  ERROR: {type(e).__name__}: {e}")

    print("\n" + "=" * 78)
    print("Lectura:")
    print("  * ratio last3/analytic ≈ 0.03-0.05: bloque de ruido presente (OK).")
    print("  * std(brain)/std(bg) en NOISE frame:")
    print("      ≈ 1.0 con mean(brain)≈mean(bg) → ruido Rayleigh puro (H1).")
    print("      >> 1  con mean(brain)>>mean(bg) → señal residual (H2).")
    print("  * σ_used / std(signal_brain): para threshold MP, valores")
    print("    similares entre P2 y P4 indicarían tratamiento equivalente.")
    print("    Si P2 << P4, el umbral mag-only cae bajo el BOLD real.")
    print("  * ratio std_post/std_pre en signal: P4 ~0.7-0.85 (sano);")
    print("    P2 ~0.1-0.2 confirma sobre-corte a nivel de voxel.")
    print("=" * 78)


if __name__ == "__main__":
    main()
