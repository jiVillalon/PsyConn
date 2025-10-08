# PsyConnectome & PsyPlasticity

**Neuroimagen fMRI + RNA-seq para entender el efecto de los psicodélicos (LSD/psilocibina) en el cerebro**

> Proyecto de portfolio orientado a industria (biotech/neurotech/health data science) que combina neurociencia computacional (conectividad funcional, grafos) y bioinformática (RNA-seq, pathways de plasticidad).

---

## ✨ Objetivos

* **fMRI**: cuantificar cómo cambia la **conectividad funcional** y la **organización de redes** cerebrales bajo LSD frente a placebo (dataset OpenNeuro).
* **RNA-seq**: identificar **firmas transcriptómicas de plasticidad** (BDNF/mTOR/sinaptogénesis) inducidas por psicodélicos en modelos animales (datasets GEO) y derivar un **psy-plasticity score** aplicable a nuevas muestras.

---

## 🧩 Resultados esperados

* Matrices de conectividad y **connectome plots** antes/después del estímulo.
* Métricas de red (modularidad, eficiencia global, *participation coefficient*) y comparaciones LSD vs placebo.
* **Informe reproducible** con figuras clave y pruebas estadísticas (permutation tests, FDR).
* Conjunto de **genes y vías** (GSEA) que caracterizan la plasticidad pro-terapéutica, más un **score** calculable desde un pequeño paquete.

---

## 📂 Estructura del repositorio

```
psyconnectome-psyplasticity/
├─ README.md
├─ environment.yml          # entorno conda para Python
├─ renv.lock                # (opcional) snapshot de R con renv
├─ data/                    # (gitignored) datos locales
│  ├─ openneuro/            # BIDS fMRI (ds003059)
│  └─ geo/                  # conteos/expresión
├─ notebooks/
│  ├─ 01_fmri_qc_preproc.ipynb
│  ├─ 02_connectivity.ipynb
│  ├─ 03_network_analysis.ipynb
│  ├─ 04_rnaseq_QC_normalization.Rmd
│  ├─ 05_DE_GSEA_WGCNA.Rmd
│  └─ 06_signature_score.Rmd
├─ src/
│  ├─ python/
│  │  ├─ io_bids.py
│  │  ├─ connectivity.py
│  │  ├─ network_metrics.py
│  │  └─ viz.py
│  └─ R/
│     ├─ rnaseq_io.R
│     ├─ de_gsea.R
│     └─ wgcna_modules.R
├─ reports/                 # figuras y html/pdf
└─ psyplasticity/           # (opcional) mini-paquete del score (R o Python)
```

---

## 🗂️ Datos abiertos

* **fMRI (OpenNeuro)**: *ds003059* — sesiones LSD vs placebo con resting-state. Descarga con `openneuro-py`/`datalad`.
* **RNA-seq (GEO)**: conjuntos con psilocibina/LSD/relacionados; usaremos 1–2 estudios con bulk RNA-seq (y opcionalmente scRNA-seq) para construir y validar la firma.

> ⚠️ Este repo no redistribuye datos. Provee scripts para descargarlos y reproducir el análisis localmente.

---

## 🛠️ Instalación

### Requisitos

* **Conda/mamba** (recomendado).
* **Docker o Apptainer/Singularity** si vas a correr *fMRIPrep* localmente (paso pesado). Alternativa: usar derivados ya preprocesados si están disponibles.
* **R (≥4.2)** y **RStudio** (recomendado) o `VS Code + R extension`.

### Entorno Python (neuroimagen)

`environment.yml`

```yaml
name: psyconnectome
channels:
  - conda-forge
  - defaults
dependencies:
  - python=3.11
  - numpy
  - pandas
  - scipy
  - scikit-learn
  - matplotlib
  - plotly
  - networkx
  - nibabel
  - nilearn
  - jupyterlab
  - ipykernel
  - datalad
  - openneuro-py
```

Instalación:

```bash
mamba env create -f environment.yml
mamba activate psyconnectome
python -m ipykernel install --user --name psyconnectome --display-name "Python (psyconnectome)"
```

### Entorno R (bioinformática)

Instala paquetes (primera vez):

```r
install.packages(c("tidyverse","data.table","patchwork","pheatmap"))
if (!requireNamespace("BiocManager", quietly=TRUE)) install.packages("BiocManager")
BiocManager::install(c(
  "DESeq2","edgeR","tximport","limma",
  "clusterProfiler","org.Mm.eg.db","msigdbr",
  "GSVA","WGCNA"
))
```

*(Opcional)* congela dependencias con `{renv}`:

```r
install.packages("renv"); renv::init()
```

---

## 🚦 Flujo de trabajo (resumen)

### A) fMRI — Conectividad y redes

1. **Descarga BIDS** (ds003059) con `openneuro-py` o `datalad`.
2. **Preprocesamiento** con *fMRIPrep* (Docker/Apptainer): corrección de movimiento, MNI, *confounds*.
3. **Parcellado** (p.ej., Schaefer-200) y extracción de señales ROI con `NiftiLabelsMasker` (nilearn).
4. **Matrices de conectividad** (correlación Fisher-z) y **métricas de red** (modularidad, eficiencia, *participation coefficient*).
5. **Estadística**: comparación LSD vs placebo (permutation tests; control FDR; covariables: edad, sexo, *motion* medio).
6. **Visualización**: heatmaps, connectome plots, curvas y tablas resumen.

### B) RNA-seq — Firma de plasticidad

1. **Descarga GEO** (conteos o FASTQ → cuantificación) y **QC** (PCA/outliers, library size).
2. **Normalización y DE** con `DESeq2`/`edgeR` (diseño ~ tratamiento + tiempo + batch).
3. **Pathways** con `clusterProfiler`/`msigdbr` (vías sinápticas, BDNF/mTOR).
4. **WGCNA** para módulos coexpresados asociados a tratamiento.
5. **Firma y score**: selecciona genes robustos (consenso entre estudios) y calcula **ssGSEA/GSVA score**.
6. **Validación** cruzada entre datasets.

---

## ▶️ Ejemplos de código (extractos mínimos)

### Python — extracción de series temporales y matriz de conectividad

```python
from nilearn.maskers import NiftiLabelsMasker
from nilearn.connectome import ConnectivityMeasure
from nilearn import plotting
import numpy as np, pandas as pd

# rutas de ejemplo (derivados fMRIPrep)
func_img = "data/openneuro/derivatives/fmriprep/sub-01/func/sub-01_task-rest_space-MNI152NLin2009cAsym_desc-preproc_bold.nii.gz"
confounds = "data/openneuro/derivatives/fmriprep/sub-01/func/sub-01_task-rest_desc-confounds_timeseries.tsv"
atlas_img = "atlases/Schaefer2018_200Parcels_17Networks_order_FSLMNI152_2mm.nii.gz"

masker = NiftiLabelsMasker(labels_img=atlas_img, standardize=True, detrend=True, low_pass=0.1, high_pass=0.01, t_r=2.0)
X = masker.fit_transform(func_img, confounds=confounds)

conn = ConnectivityMeasure(kind='correlation')
mat = conn.fit_transform([X])[0]
mat_z = np.arctanh(mat)  # Fisher z

pd.DataFrame(mat_z).to_csv("reports/sub-01_connectivity_lsd.csv", index=False)
plotting.plot_matrix(mat_z, figure=(8, 8), colorbar=True)
```

### R — DESeq2 + GSEA (bosquejo)

```r
library(DESeq2); library(clusterProfiler); library(msigdbr); library(org.Mm.eg.db)
# counts: matriz genes x muestras; coldata: DataFrame con tratamiento, tiempo, batch
dds <- DESeqDataSetFromMatrix(countData=counts, colData=coldata, design=~ batch + tratamiento)
dds <- DESeq(dds)
res <- lfcShrink(dds, coef="tratamiento_LSD_vs_control", type="apeglm")

# GSEA con ranking por estadístico
ranked <- res$stat; names(ranked) <- rownames(res); ranked <- sort(ranked, decreasing=TRUE)
msig <- msigdbr(species="Mus musculus", category="C2", subcategory="CP:KEGG")
msig_list <- split(msig$gene_symbol, msig$gs_name)
fgsea_res <- GSEA(ranked, TERM2GENE=msig_list)
```

---

## 📊 Métricas de calidad

* **fMRI**: control de *motion* (FD medio), varianza explicada por confounds, estabilidad de métricas ante re-parcelado.
* **Redes**: diferencias de modularidad/eficiencia con *p* ajustado (FDR).
* **RNA-seq**: FDR<0.05 en vías relevantes; concordancia entre datasets (ρ Spearman, *π1*).

---

## 🔒 Ética y cumplimiento

* Datos humanos: seguir licencias y guías de OpenNeuro; anonimización ya provista por los autores.
* Este proyecto es **educativo**; no sustituye guía clínica.
* Evitar *data leakage* y respetar estándares FAIR (documentación, versionado, seeds).

---

## 🧪 Reproducibilidad

* Scripts idempotentes; semillas fijadas.
* `Makefile` (opcional) o `snakemake` para orquestar pasos.
* CI mínima (pytest para utilidades; R CMD check para scripts R si empaquetas el score).

---

## 📈 Roadmap (hitos)

* [ ] H1: Descarga y QC de un sujeto (placebo/LSD) + primera matriz y connectome plot.
* [ ] H2: Métricas de red y comparación estadística (≥10 sujetos si disponibles).
* [ ] H3: RNA-seq: DE + GSEA en un dataset.
* [ ] H4: Construcción del **psy-plasticity score** y validación cruzada.
* [ ] H5: Informe HTML (Quarto) con resultados integrados.

---

## 🧾 Licencia

MIT (código). Ver licencias de datos originales en cada repositorio fuente.

---

## 👤 Autor

Tu Nombre — Biología | Bioestadística | Bioinformática · Contacto · LinkedIn
