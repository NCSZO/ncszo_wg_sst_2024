# Claude Code Context — NCSZO WaveGlider SST 2024

## What This Repo Is

Standalone data publication repo for the 2024 NCSZO GNSS-A WaveGlider surface
temperature dataset. HOBO MX2203 logger (S/N 21732422) mounted on WaveGlider
SV3-271; deployed Sep 6 – Oct 6, 2024; calibrated post-deployment against a
Sea-Bird SBE19plus CTD (S/N 7036) at the ONC Marine Technology Centre.

Intended publication: Borealis Dataverse, `ncszo-gnssa` sub-dataverse.
GitHub: https://github.com/NCSZO/ncszo_wg_sst_2024

This repo has no package structure — it is a data repo, not a Python package.
There is no `pyproject.toml`. Run with any Python ≥ 3.11 env that has the
four packages in `requirements.txt` (pandas, matplotlib, numpy, openpyxl).

## How to Run

    python process_temp_logger.py

Run from the repo root. Reads everything from `raw/`, writes all outputs to
the repo root and `figures/`. Nothing else needed; no network access.

## Deployment Timeline (Confirmed)

- 2024-09-06 15:51 UTC  HOBO activated — on the ship, showing ~21 °C (air)
- 2024-09-06 17:10 UTC  WaveGlider released into water (10:10 PDT)
- 2024-09-06 17:22 UTC  HOBO enters water, temperature drops to ~11 °C  (12 min after WG release)
- 2024-10-06 15:24 UTC  Last HOBO record (WaveGlider already back at port ~19 h earlier)

The first 91 rows (`deployment_state = "pre_water"`) are air/deck temperature.
Their `latitude_deg` / `longitude_deg` are NaN: the WGMS telemetry gives the
WaveGlider's position (at sea), not the ship's position.

## GNSS-A Station Visits During Deployment

Computed from telemetry proximity (6 km radius to array centroid):

| Site      | Approx. period         | Duration |
|-----------|------------------------|----------|
| GNSSA-04  | Sep  7 19:00 – Sep 11  | 99.8 h   |
| GNSSA-01  | Sep 12 12:00 – Sep 18  | 150.6 h  |
| GNSSA-02  | Sep 19 05:00 – Sep 23  | 102.4 h  |
| GNSSA-03  | Sep 23 19:00 – Sep 26  | 65.5 h   |
| GNSSA-06  | Sep 27 09:00 – Sep 30  | 86.1 h   |

Two brief GNSSA-02 returns (~3–4 h each) at Sep 26-27 and Oct 5. Centroids
in `GNSSA_SITES_2024` dict in the script; update if re-running for other years.

## Calibration — Key Numbers and Known Bias

Applied offset: **+0.023 °C** (HOBO reads cold; `temp_c_calibrated = temp_c_raw + 0.023`)

- Computed as the median of 2,452 equilibrated minute-pairs (rows 60 to -1
  of the merged HOBO × CTD comparison; first 60 min discarded as warmup).
- Combined 1σ accuracy (in-water): **±0.014 °C** (calibration scatter +
  CTD stated accuracy in quadrature).

**Known bias from thermal cycling:** The ONC tank was actively temperature-
cycling (~±0.7 °C, ~15 h period). HOBO thermal lag (τ ≈ 5 min) means HOBO
trails CTD on both heat-up and cool-down. The applied median is therefore
slightly biased toward whichever phase dominates the equilibrated region. Fig 4
shows the warming/cooling residuals split — the two clusters are separated by
~0.01–0.02 °C. No correction has been applied; the bias is within the stated
±0.014 °C uncertainty.

**No response-function correction:** τ ≈ 5 min (still-water estimate from
calibration cross-correlation). Error at tidal timescales (12.4 h) is ~0.001 °C,
14× smaller than calibration uncertainty. Field τ is smaller still (WaveGlider
moves at 1–2 kt).

## Outputs

| File | Description |
|------|-------------|
| `hobo_21732422_2024_temperature.csv` | 43,174 rows × 7 cols, 1-min UTC |
| `hobo_21732422_2024_temperature.geojson` | 41,913 positioned points (WGS-84) |
| `hobo_21732422_2024_metadata.json` | Machine-readable calibration + deployment stats |
| `figures/01_deployment_timeseries.png` | Full time series; station-visit bands shaded |
| `figures/02_calibration_comparison_timeseries.png` | HOBO vs CTD; heat/cool phase shading |
| `figures/03_calibration_offset_convergence.png` | CTD−HOBO vs time; y-axis clipped to equilibrated range |
| `figures/04_calibration_residuals.png` | HOBO−CTD residuals vs temperature, warming/cooling split |
| `figures/05_deployment_track_temperature.png` | WaveGlider track coloured by SST |
| `README.txt` | Human-readable dataset documentation |
| `CODEBOOK.txt` | Column definitions and flag scheme |

`raw/` contains original files and must not be modified.

## Relationship to Sibling Repos

- **`ncszo_gnssa_model`**: Bayesian GNSS-A positioning pipeline. Uses this SST
  to constrain the 0–50 m sound-speed layer (V_Ave prior). See
  `docs/notes/concepts/in-situ-sound-speed-data.md` there.
- **`ncszo_gnssa_data`**: Borealis upload tooling and raw acoustic data archive.
  This repo was extracted from its development scaffolding; the dev version of
  `process_temp_logger.py` was removed from `ncszo_gnssa_data` when this repo
  was created (2026-05-26).

## If You Need to Change the Calibration

The only number to change is `applied_offset_c` — it is computed dynamically
in `compute_calibration()` and propagates automatically to the CSV, GeoJSON,
metadata JSON, README, and CODEBOOK. Do not hardcode it anywhere else.

To adjust the equilibration cutoff (currently 60 min), change `EQUILIBRATION_MIN`.
To adjust the pre-water detection thresholds, change `SST_MAX_C` and/or
`COOLING_RATE_C_PER_MIN`. Both constants are at the top of the script.
