import gzip, pickle, sys
from pathlib import Path
import numpy as np
import nibabel as nib

ECHO_TIMES = np.array([14.2, 38.93, 63.66, 88.39, 113.12])  # ms
CHUNK_SIZE = 30_000

def main(t2smap_wf_dir):
    t2smap_wf = Path(t2smap_wf_dir)
    bold_native = t2smap_wf.parent

    echo_paths = []
    for i in range(5):
        cands = list((bold_native / f"_echoidx_{i}" / "boldref_bold").glob("*.nii.gz"))
        if not cands: sys.exit(f"Falta echo en _echoidx_{i}")
        echo_paths.append(cands[0])

    mask_path = t2smap_wf / "dilate_mask" / "dilated_mask.nii.gz"
    out_dir = t2smap_wf / "t2smap_node"
    out_dir.mkdir(exist_ok=True)

    mask_img = nib.load(mask_path)
    mask = mask_img.get_fdata().astype(bool)
    affine = mask_img.affine
    shape3d = mask.shape

    n_tr = nib.load(echo_paths[0]).shape[3]
    n_echos = 5
    print(f"shape={shape3d}  n_TR={n_tr}  mask_vox={mask.sum()}")

    coords = np.argwhere(mask)
    n_vox = len(coords)

    t2s_4d = np.zeros(shape3d + (n_tr,), dtype=np.float32)
    s0_4d  = np.zeros(shape3d + (n_tr,), dtype=np.float32)
    opt_4d = np.zeros(shape3d + (n_tr,), dtype=np.float32)

    imgs = [nib.load(p) for p in echo_paths]
    A = np.column_stack([np.ones(n_echos), -ECHO_TIMES])

    for s in range(0, n_vox, CHUNK_SIZE):
        e = min(s + CHUNK_SIZE, n_vox)
        x, y, z = coords[s:e].T
        cn = len(x)

        data = np.empty((cn, n_echos, n_tr), dtype=np.float64)
        for k, im in enumerate(imgs):
            data[:, k, :] = np.asanyarray(im.dataobj[x, y, z, :])

        log_d = np.log(data + 1.0)
        Y = log_d.transpose(1, 0, 2).reshape(n_echos, -1)
        beta, *_ = np.linalg.lstsq(A, Y, rcond=None)
        log_s0 = beta[0].reshape(cn, n_tr)
        inv_t2s = beta[1].reshape(cn, n_tr)

        with np.errstate(divide='ignore', invalid='ignore'):
            t2s = 1.0 / inv_t2s
        t2s = np.where(np.isfinite(t2s) & (t2s > 0) & (t2s < 500), t2s, 0)
        s0  = np.exp(np.clip(log_s0, -20, 30))

        safe_t2s = np.where(t2s > 0, t2s, 1e6)
        w = ECHO_TIMES[None, :, None] * np.exp(-ECHO_TIMES[None, :, None] / safe_t2s[:, None, :])
        ws = w.sum(axis=1, keepdims=True)
        w = np.divide(w, ws, out=np.zeros_like(w), where=ws > 0)
        opt = (data * w).sum(axis=1)

        t2s_4d[x, y, z, :] = t2s.astype(np.float32)
        s0_4d[x, y, z, :]  = s0.astype(np.float32)
        opt_4d[x, y, z, :] = opt.astype(np.float32)
        print(f"  {s:>7}-{e:>7} / {n_vox}")

    nib.save(nib.Nifti1Image(t2s_4d, affine), out_dir / "T2starmap.nii.gz")
    nib.save(nib.Nifti1Image(s0_4d,  affine), out_dir / "S0map.nii.gz")
    nib.save(nib.Nifti1Image(opt_4d, affine), out_dir / "desc-optcom_bold.nii.gz")
    print("[ok] outputs escritos")

    rp = out_dir / "result_t2smap_node.pklz"
    if rp.exists():
        with gzip.open(rp, "rb") as f: r = pickle.load(f)
        r.runtime.returncode = 0
        r.outputs.t2star_map  = str(out_dir / "T2starmap.nii.gz")
        r.outputs.s0_map      = str(out_dir / "S0map.nii.gz")
        r.outputs.optimal_comb = str(out_dir / "desc-optcom_bold.nii.gz")
        with gzip.open(rp, "wb") as f: pickle.dump(r, f)
        print("[ok] result_t2smap_node.pklz parcheado")

if __name__ == "__main__":
    main(sys.argv[1])