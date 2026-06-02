# PsyConn

[![DOI](https://zenodo.org/badge/DOI/10.5281/zenodo.20513897.svg)](https://doi.org/10.5281/zenodo.20513897)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)
[![Docs: CC BY 4.0](https://img.shields.io/badge/Docs-CC%20BY%204.0-lightgrey.svg)](https://creativecommons.org/licenses/by/4.0/)

**Pipeline reproducible multi-echo para el análisis de la conectividad funcional cerebral en estudios con psicodélicos: aplicación a la psilocibina**

Trabajo Final de Máster (TFM) — Máster Universitario en Bioinformática y
Bioestadística (UOC-UB), Área de Desarrollo de Programas y Aplicaciones.
Convocatoria 06/2026.

> Autor: Juan Ignacio Villalón Luis · Tutora: Teresa Torres Moral · PRA: Marta Gatnau Sarret.

---

## Resumen

PsyConn implementa un pipeline reproducible para el análisis de la conectividad
funcional cerebral en estudios con psicodélicos, aplicado al dataset abierto
**ds006072** (Siegel et al., 2024; $N=6$, diseño *crossover* intra-sujeto
psilocibina 25 mg vs metilfenidato, BOLD multi-echo de cinco ecos).

La cadena de procesado combina:

- **Denoising térmico** con NORDIC.
- **Preprocesamiento estructural y funcional** con fMRIPrep multi-echo.
- **Combinación óptima de ecos y limpieza ICA** con TEDANA, seguida de regresión
  de *confounds*.
- **Extracción de series temporales** con un atlas combinado Schaefer 200 +
  Tian S2 (232 ROIs cortico-subcorticales).
- **Análisis de redes funcionales** mediante métricas de teoría de grafos,
  dos formulaciones de entropía y análisis exploratorios complementarios.

Sobre los resultados se discute el alcance de la hipótesis del *cerebro
entrópico* en la modalidad de psilocibina y se evalúa la robustez del
pipeline frente a las elecciones metodológicas habituales.

## Estructura del repositorio

```
PsyConn/
├── notebooks/      Notebooks ejecutables del pipeline (PsiloData → PsiloPrep → PsyConn)
├── src/            Módulos auxiliares de soporte
├── reports/        Memoria del TFM e informes de resultados (CC BY 4.0)
├── results/        Salidas analíticas: matrices de conectividad, métricas, tablas
└── derivatives/    Subconjunto reproducible de derivados de preprocesamiento
                    (reportes fMRIPrep, reportes TEDANA, figuras de QC)
```

Los datos crudos NIfTI y los volúmenes intermedios pesados se excluyen del
repositorio por tamaño y por respetar la titularidad de OpenNeuro. El
dataset original puede descargarse libremente desde
<https://openneuro.org/datasets/ds006072>.

## Dependencias

El entorno de ejecución se define en [`environment.yml`](environment.yml) (conda).

Las herramientas externas usadas — NORDIC, fMRIPrep y TEDANA — se invocan en
sus versiones documentadas en cada notebook y en la sección de Métodos de la
memoria.

### NORDIC

El código de denoising térmico NORDIC es desarrollo de terceros (Steen Moeller,
University of Minnesota) y no se redistribuye en este repositorio. Para
reproducir el preprocesamiento, clona el repositorio oficial dentro de
`src/external/`:

```bash
git clone https://github.com/SteenMoeller/NORDIC_Raw.git src/external/NORDIC_Raw
```

La versión de NORDIC utilizada en este trabajo corresponde al commit
`0861968` ("Update NIFTI_NORDIC.m"). Para fijar exactamente la misma versión:

```bash
cd src/external/NORDIC_Raw && git checkout 0861968
```

NORDIC_Raw está distribuido bajo su propia licencia (véase el `LICENCE.md`
incluido en su repositorio); consulta la atribución y los términos allí.

## Cómo citar

Si usas este pipeline o reproduces sus resultados, por favor cita la versión
publicada en Zenodo:

> Villalón Luis, J. I. (2026). *PsyConn — Pipeline reproducible multi-echo para
> el análisis de la conectividad funcional cerebral en estudios con
> psicodélicos: aplicación a la psilocibina*. Zenodo.
> <https://doi.org/10.5281/zenodo.20513897>

El DOI anterior (`10.5281/zenodo.20513897`) es el **concept DOI**: resuelve
siempre a la última versión disponible y es el que conviene citar en general.
Cada *release* tiene además su propio *version DOI* (la versión 0.1.0
preliminar corresponde a [`10.5281/zenodo.20513898`](https://doi.org/10.5281/zenodo.20513898)).

El archivo [`CITATION.cff`](CITATION.cff) contiene los metadatos estructurados
de la cita en formato CFF.

## Licencias

- **Código** (`src/`, `notebooks/`, scripts auxiliares): MIT — ver [`LICENSE`](LICENSE).
- **Documentación** (memoria del TFM, informes y figuras de `reports/`):
  Creative Commons Attribution 4.0 International (CC BY 4.0) — ver
  [`LICENSE-docs.md`](LICENSE-docs.md).

Los materiales de terceros reproducidos o citados en la memoria (figuras,
citas literales, datasets) conservan sus licencias originales y se acreditan
en el texto correspondiente.

## Reconocimientos

A los autores del estudio original (Siegel et al., 2024) y al equipo de
OpenNeuro por la apertura de los datos; a las comunidades de fMRIPrep,
TEDANA y NORDIC por mantener herramientas científicas abiertas; y a la
tutora del TFM, Teresa Torres Moral, por su acompañamiento durante el
desarrollo del trabajo.
