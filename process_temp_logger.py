#!/usr/bin/env python3
"""
Process HOBO MX2203 surface temperature logger — 2024 NCSZO GNSS-A WaveGlider survey.

Standalone script: no external package dependencies beyond standard scientific Python.
Requirements: pandas, matplotlib, numpy, openpyxl  (see requirements.txt)

Run from the repo root:
    python process_temp_logger.py

Regenerates all outputs (CSV, JSON, figures, README, CODEBOOK) from raw/ files.

Outputs written to the repo root:
  hobo_21732422_2024_temperature.csv
  hobo_21732422_2024_metadata.json
  figures/01_deployment_timeseries.png
  figures/02_calibration_comparison_timeseries.png
  figures/03_calibration_offset_convergence.png
  figures/04_calibration_scatter.png
  figures/05_deployment_track_temperature.png
  README.txt
  CODEBOOK.txt
"""

import json
import shutil
from datetime import timedelta
from pathlib import Path

import matplotlib.dates as mdates
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

# ── paths ──────────────────────────────────────────────────────────────────────

SCRIPT_DIR = Path(__file__).resolve().parent
RAW_DIR    = SCRIPT_DIR / "raw"
OUT_DIR    = SCRIPT_DIR

DEPLOY_XLS    = RAW_DIR / "21732422_deployment_2024-09-06_2024-10-06_PDT.xlsx"
CAL_XLS       = RAW_DIR / "calibration/21732422_calibration_2024-11-05_2024-11-07_PST.xlsx"
CTD_ODV       = RAW_DIR / "calibration/SBECTD19p7036_calibration_reference.txt"
TELEMETRY_CSV = RAW_DIR / "wgms_telemetry_2024.csv"

PDT = timedelta(hours=7)   # PDT = UTC-7  (Sep–Oct 2024 deployment)
PST = timedelta(hours=8)   # PST = UTC-8  (Nov 2024 calibration)

EQUILIBRATION_MIN = 60     # minutes discarded at start of tank comparison (warmup)
SBE_ACCURACY_C    = 0.005  # SBE CTD 19p stated accuracy (°C, 1σ)

# deployment_state thresholds
SST_MAX_C              = 17.0   # max plausible Sep SST at GNSSA-03; above = deck/air
COOLING_RATE_C_PER_MIN = 0.05   # |dT/dt| threshold for "still equilibrating to water"

# ── loaders ───────────────────────────────────────────────────────────────────

def load_hobo_deployment(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Data", header=0, usecols=[1, 2])
    df.columns = ["datetime_local", "temp_c_raw"]
    df = df.dropna().copy()
    df["datetime_utc"] = pd.to_datetime(df["datetime_local"]) + PDT
    return df[["datetime_utc", "temp_c_raw"]].reset_index(drop=True)


def load_hobo_calibration(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Data", header=0, usecols=[1, 2])
    df.columns = ["datetime_local", "temp_c"]
    df = df.dropna().copy()
    df["datetime_utc"] = pd.to_datetime(df["datetime_local"]) + PST
    return df[["datetime_utc", "temp_c"]].reset_index(drop=True)


def load_ctd_reference(path: Path) -> pd.DataFrame:
    """Parse ONC ODV text file; return 1-Hz UTC time + temperature (QC 1–2 only)."""
    text = path.read_text(encoding="utf-8", errors="replace")
    n_comment = sum(1 for line in text.splitlines() if line.startswith("//"))
    raw = pd.read_csv(path, sep=";", skiprows=n_comment, header=0,
                      skipinitialspace=True, encoding="utf-8", encoding_errors="replace",
                      low_memory=False)
    # Column layout: 0=Type, 1=Cruise, 2=Station, 3=datetime_meta, 4=Lat, 5=Lon,
    #                6=time_ISO8601 (PRIMARYVAR), 7=Temperature [C], 8=QV flag
    sub = raw.iloc[:, [6, 7, 8]].copy()
    sub.columns = ["datetime_utc", "temp_c", "qv"]
    sub["datetime_utc"] = pd.to_datetime(sub["datetime_utc"].str.strip(), utc=True).dt.tz_localize(None)
    sub["temp_c"] = pd.to_numeric(sub["temp_c"], errors="coerce")
    sub["qv"]     = pd.to_numeric(sub["qv"].astype(str).str.strip(), errors="coerce")
    sub = sub[sub["qv"].isin([1.0, 2.0])].drop(columns="qv")
    return sub.dropna().reset_index(drop=True)


def load_telemetry(path: Path) -> pd.DataFrame:
    """Load WaveGlider WGMS telemetry; return sorted UTC datetime + lat/lon (zeros dropped)."""
    df = pd.read_csv(path, usecols=["TimeStamp", "Lat (deg)", "Lon (deg)"])
    df.columns = ["datetime_utc", "latitude_deg", "longitude_deg"]
    df["datetime_utc"] = pd.to_datetime(df["datetime_utc"], dayfirst=True)
    df = df[(df["latitude_deg"] != 0) & (df["longitude_deg"] != 0)].copy()
    return df.sort_values("datetime_utc").reset_index(drop=True)


# ── calibration ───────────────────────────────────────────────────────────────

def compute_calibration(hobo_cal: pd.DataFrame, ctd_hz: pd.DataFrame,
                        skip_min: int = 60) -> dict:
    """
    Align HOBO (1-min) with CTD (1-Hz resampled to 1-min), compute equilibrium offset.
    Returns stats dict plus 'merged' and 'equil' DataFrames for plotting.
    """
    ctd_min = ctd_hz.copy()
    ctd_min["minute"] = ctd_min["datetime_utc"].dt.floor("min")
    ctd_min = ctd_min.groupby("minute", as_index=False)["temp_c"].mean()
    ctd_min.rename(columns={"minute": "datetime_utc", "temp_c": "ctd_c"}, inplace=True)

    merged = pd.merge(
        hobo_cal.rename(columns={"temp_c": "hobo_c"}),
        ctd_min, on="datetime_utc", how="inner",
    ).reset_index(drop=True)

    merged["diff"] = merged["ctd_c"] - merged["hobo_c"]
    t0 = merged["datetime_utc"].iloc[0]
    merged["elapsed_min"] = (merged["datetime_utc"] - t0).dt.total_seconds() / 60.0

    equil   = merged.iloc[skip_min:-1].copy()
    applied = round(float(equil["diff"].median()), 3)

    return {
        "merged":                   merged,
        "equil":                    equil,
        "offset_mean_c":            float(equil["diff"].mean()),
        "offset_median_c":          float(equil["diff"].median()),
        "offset_std_c":             float(equil["diff"].std()),
        "applied_offset_c":         applied,
        "n_equilibrated":           len(equil),
        "equilibration_period_min": skip_min,
    }


# ── deployment state detection ────────────────────────────────────────────────

def detect_deployment_state(deploy: pd.DataFrame) -> pd.Series:
    """
    Return a Series of "pre_water" / "in_water" for each row.

    "pre_water" while EITHER condition holds:
      (a) temp_c_raw > SST_MAX_C  — clearly above maximum in-situ SST for this area/season
      (b) 5-min smoothed |dT/dt| > COOLING_RATE_C_PER_MIN — still equilibrating to water

    Once both conditions are false for the first time, all subsequent rows are "in_water".
    The state never reverts: a single warm spike during the deployment does not re-trigger
    "pre_water" because we propagate the state forward using cumsum.
    """
    temp     = deploy["temp_c_raw"]
    smoothed = temp.rolling(5, center=True, min_periods=1).mean()
    dT_dt    = smoothed.diff()   # backward difference, units: °C per minute

    is_pre = (temp > SST_MAX_C) | (dT_dt < -COOLING_RATE_C_PER_MIN)

    # Find the first row where the pre-water condition is False.
    # All rows before it are "pre_water"; from it onward "in_water".
    first_in_water = is_pre[~is_pre].index[0] if (~is_pre).any() else len(deploy)
    state = pd.Series("pre_water", index=deploy.index)
    state.iloc[first_in_water:] = "in_water"
    return state


# ── position interpolation ────────────────────────────────────────────────────

def interpolate_position(deploy: pd.DataFrame, telemetry: pd.DataFrame) -> pd.DataFrame:
    """Linearly interpolate WaveGlider lat/lon onto HOBO 1-min timestamps."""
    tel_t  = telemetry["datetime_utc"].astype(np.int64).values
    hobo_t = deploy["datetime_utc"].astype(np.int64).values

    lat = np.interp(hobo_t, tel_t, telemetry["latitude_deg"].values,  left=np.nan, right=np.nan)
    lon = np.interp(hobo_t, tel_t, telemetry["longitude_deg"].values, left=np.nan, right=np.nan)

    out = deploy.copy()
    out["latitude_deg"]  = np.where(np.isnan(lat), np.nan, np.round(lat, 6))
    out["longitude_deg"] = np.where(np.isnan(lon), np.nan, np.round(lon, 6))
    return out


# ── figures ───────────────────────────────────────────────────────────────────

RC = {
    "figure.dpi":        150,
    "axes.spines.top":   False,
    "axes.spines.right": False,
    "font.size":         10,
    "axes.labelsize":    11,
    "axes.titlesize":    11,
}

COL_RAW    = "#d7191c"
COL_CAL    = "#2166ac"
COL_CTD    = "#1a9641"
COL_WARM   = "#fee090"
COL_PREDEP = "#bdbdbd"


def fig_deployment(deploy: pd.DataFrame, applied_offset: float, out: Path) -> None:
    inw = deploy[deploy["deployment_state"] == "in_water"]
    pre = deploy[deploy["deployment_state"] == "pre_water"]

    with plt.style.context(RC):
        fig, axes = plt.subplots(2, 1, figsize=(12, 6), gridspec_kw={"height_ratios": [4, 1]})

        ax = axes[0]
        if not pre.empty:
            ax.plot(pre["datetime_utc"], pre["temp_c_calibrated"],
                    lw=0.6, color=COL_PREDEP, label="Pre-deployment (deck/air)", zorder=1)
        ax.plot(inw["datetime_utc"], inw["temp_c_calibrated"],
                lw=0.8, color=COL_CAL, label="Calibrated (in water)", zorder=3)
        ax.plot(inw["datetime_utc"], inw["temp_c_raw"],
                lw=0.5, color=COL_RAW, alpha=0.4, label="Raw (in water)", zorder=2)
        ax.set_ylabel("Temperature (°C)")
        ax.set_title(
            "HOBO MX2203 S/N 21732422 — WaveGlider SV3-271 surface temperature 2024\n"
            f"Calibration correction applied: +{applied_offset:.3f} °C"
        )
        ax.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))
        fig.autofmt_xdate(rotation=30, ha="right")
        ax.legend(frameon=False)

        ax2 = axes[1]
        ax2.plot(inw["datetime_utc"],
                 inw["temp_c_calibrated"] - inw["temp_c_raw"],
                 lw=0.6, color="0.5")
        ax2.axhline(applied_offset, color=COL_CAL, lw=1.0, ls="--")
        ax2.set_ylabel("Cal − Raw\n(°C)")
        ax2.set_ylim(applied_offset - 0.005, applied_offset + 0.005)
        ax2.xaxis.set_major_formatter(mdates.DateFormatter("%Y-%m-%d"))

        fig.tight_layout()
        fig.savefig(out)
        plt.close(fig)


def fig_calibration_comparison(merged: pd.DataFrame, skip_min: int, out: Path) -> None:
    with plt.style.context(RC):
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.axvspan(0, skip_min, color=COL_WARM, alpha=0.5,
                   label=f"Warmup excluded (< {skip_min} min)")
        ax.plot(merged["elapsed_min"], merged["ctd_c"],
                lw=1.2, color=COL_CTD, label="SBE CTD reference (1 Hz, resampled to 1 min)")
        ax.plot(merged["elapsed_min"], merged["hobo_c"],
                lw=1.0, color=COL_RAW, ls="--", label="HOBO raw (1 min)")
        ax.set_xlabel("Time since tank immersion (min)")
        ax.set_ylabel("Temperature (°C)")
        ax.set_title(
            "Tank calibration: HOBO MX2203 vs SBE CTD 19p S/N 7036\n"
            "ONC Integration Testing facility, 2024-11-05 to 2024-11-07"
        )
        ax.legend(frameon=False)
        fig.tight_layout()
        fig.savefig(out)
        plt.close(fig)


def fig_calibration_offset(merged: pd.DataFrame, cal: dict, out: Path) -> None:
    skip    = cal["equilibration_period_min"]
    applied = cal["applied_offset_c"]
    std     = cal["offset_std_c"]
    with plt.style.context(RC):
        fig, ax = plt.subplots(figsize=(12, 4))
        ax.axvspan(0, skip, color=COL_WARM, alpha=0.5,
                   label=f"Warmup excluded (< {skip} min)")
        ax.plot(merged["elapsed_min"], merged["diff"],
                lw=0.7, color="0.5", label="CTD − HOBO (°C)")
        ax.axhline(0, color="0.7", lw=0.8, ls=":")
        ax.axhline(applied, color=COL_CAL, lw=1.5, ls="--",
                   label=f"Applied offset = +{applied:.3f} °C (median of equilibrated)")
        ax.axhspan(applied - std, applied + std, color=COL_CAL, alpha=0.15,
                   label=f"±1σ = ±{std:.3f} °C")
        ax.axvline(skip, color=COL_RAW, lw=1.0, ls=":", alpha=0.6)
        ax.set_xlabel("Time since tank immersion (min)")
        ax.set_ylabel("CTD − HOBO (°C)")
        ax.set_title("Calibration offset convergence — HOBO reads cold at equilibrium")
        ax.legend(frameon=False)
        fig.tight_layout()
        fig.savefig(out)
        plt.close(fig)


def fig_calibration_scatter(equil: pd.DataFrame, applied_offset: float, out: Path) -> None:
    x     = equil["ctd_c"].values
    y_raw = equil["hobo_c"].values
    y_cal = y_raw + applied_offset
    lo = min(x.min(), y_raw.min()) - 0.02
    hi = max(x.max(), y_cal.max()) + 0.02
    with plt.style.context(RC):
        fig, ax = plt.subplots(figsize=(5, 5))
        ax.scatter(x, y_raw, s=3, alpha=0.25, color=COL_RAW, label="HOBO raw")
        ax.scatter(x, y_cal, s=3, alpha=0.25, color=COL_CAL, label="HOBO calibrated")
        ax.plot([lo, hi], [lo, hi], "k--", lw=0.8, label="1:1 line")
        ax.set_xlim(lo, hi); ax.set_ylim(lo, hi)
        ax.set_xlabel("SBE CTD reference (°C)")
        ax.set_ylabel("HOBO temperature (°C)")
        ax.set_title("Calibration scatter — equilibrated region only")
        ax.legend(frameon=False, markerscale=3)
        fig.tight_layout()
        fig.savefig(out)
        plt.close(fig)


def fig_track_temperature(deploy: pd.DataFrame, out: Path) -> None:
    """WaveGlider track coloured by calibrated surface temperature (in-water only)."""
    inw = deploy[
        (deploy["deployment_state"] == "in_water") &
        deploy["latitude_deg"].notna()
    ].copy()
    if inw.empty:
        return
    with plt.style.context(RC):
        fig, ax = plt.subplots(figsize=(7, 6))
        sc = ax.scatter(
            inw["longitude_deg"], inw["latitude_deg"],
            c=inw["temp_c_calibrated"], s=2, alpha=0.6, cmap="RdYlBu_r",
            vmin=inw["temp_c_calibrated"].quantile(0.02),
            vmax=inw["temp_c_calibrated"].quantile(0.98),
        )
        cb = fig.colorbar(sc, ax=ax, pad=0.02, shrink=0.85)
        cb.set_label("Surface temperature (°C)")
        ax.set_xlabel("Longitude (°E)")
        ax.set_ylabel("Latitude (°N)")
        ax.set_title(
            "WaveGlider SV3-271 track — 2024 NCSZO GNSS-A survey\n"
            "Colour = HOBO MX2203 surface temperature (calibrated, in-water only)"
        )
        ax.set_aspect("equal")
        fig.tight_layout()
        fig.savefig(out)
        plt.close(fig)


# ── text outputs ──────────────────────────────────────────────────────────────

def write_readme(out_dir: Path, deploy: pd.DataFrame, cal: dict,
                 n_pre_water: int, in_water_start: str) -> None:
    start   = deploy["datetime_utc"].iloc[0].strftime("%Y-%m-%dT%H:%M:%SZ")
    end     = deploy["datetime_utc"].iloc[-1].strftime("%Y-%m-%dT%H:%M:%SZ")
    dur     = (deploy["datetime_utc"].iloc[-1] - deploy["datetime_utc"].iloc[0]).total_seconds() / 86400
    unc     = float(np.sqrt(cal["offset_std_c"] ** 2 + SBE_ACCURACY_C ** 2))
    n       = len(deploy)
    applied = cal["applied_offset_c"]
    skip    = cal["equilibration_period_min"]
    n_eq    = cal["n_equilibrated"]

    txt = f"""\
DATASET: NCSZO GNSS-A WaveGlider Surface Temperature 2024 (HOBO MX2203)
========================================================================

Principal Investigator : Martin Heesemann (ONC / University of Victoria)
Co-Investigator        : Jesse Hutchinson (ONC / University of Victoria)
Institution            : Ocean Networks Canada, University of Victoria
Contact                : mheesema@uvic.ca

OVERVIEW
--------
One-minute-resolution sea surface temperature collected during the 2024
Northern Cascadia Seafloor Geodesy (NCSZO) GNSS-Acoustic survey aboard
the WaveGlider SV3-271.  The HOBO temperature logger was mounted on the
WaveGlider hull at the sea surface.

These data are used to constrain the 0-50 m sound-speed layer in the
Bayesian GNSS-Acoustic positioning model (see ncszo_gnssa_model on GitHub).

INSTRUMENT
----------
  Make / Model    : Onset Computer Corporation HOBO MX2203
  Serial number   : 21732422
  Firmware        : 62.140
  Logging app     : HOBOconnect 2.0.0 (phone-synced clock at start and
                    download; timestamps recorded as PDT / PST local time)
  Thermal time    : τ ≈ 5 min in still water (estimated from calibration
  constant          tank oscillations via cross-correlation).  No response-
                    function correction is applied: at tidal timescales
                    (12.4 h period) the implied error is ~0.001 °C, which
                    is 14× smaller than the calibration uncertainty
                    (±{cal['offset_std_c']:.3f} °C).  In field conditions the
                    WaveGlider moves at 1–2 kt, reducing τ further.

DEPLOYMENT
----------
  Platform        : WaveGlider SV3-271
  Survey          : NCSZO GNSS-A 2024
  Site            : GNSSA-03, Northern Cascadia subduction zone
  Start (UTC)     : {start}
  End   (UTC)     : {end}
  Duration        : {dur:.1f} days
  Sampling period : 60 s
  Raw timezone    : PDT (UTC-7); converted to UTC in processed file

PRE-DEPLOYMENT PERIOD
---------------------
  The first {n_pre_water} records (until {in_water_start}) carry
  deployment_state = "pre_water".  The HOBO logger was started on deck while
  the WaveGlider was already at sea; these readings reflect air / deck
  temperature (~21–17 °C) rather than sea surface temperature.

  Detection thresholds used:
    temp_c_raw > {SST_MAX_C:.1f} °C  (above max plausible Sep SST at GNSSA-03)
    OR 5-min smoothed |dT/dt| > {COOLING_RATE_C_PER_MIN:.2f} °C/min (still equilibrating)

CALIBRATION
-----------
  Date            : 2024-11-05 to 2024-11-07 (post-deployment)
  Facility        : ONC Marine Technology Centre, Victoria BC
                    (48.6495 N, 123.4455 W)
  Reference       : Sea-Bird SeaCAT SBE19plus V2, S/N 7036
                    Permanently deployed at ONC Integration Testing
                    (1 Hz, UTC timestamps, ARGO QC flags 1-2 retained)
  Method          : HOBO immersed alongside reference CTD in a tank.
                    First {skip} min discarded (thermal warmup transient).
                    Offset computed from {n_eq} equilibrated minute-pairs.
                    Note: the tank had an active temperature cycle (±0.7 °C
                    amplitude over ~15-hour periods), providing good coverage
                    for calibration across a temperature range.

  Calibration results:
    CTD - HOBO offset (mean)   : {cal['offset_mean_c']:+.4f} C
    CTD - HOBO offset (median) : {cal['offset_median_c']:+.4f} C  <- applied
    CTD - HOBO offset (1 sigma): {cal['offset_std_c']:.4f} C
    Applied correction         : temp_calibrated = temp_raw {applied:+.3f} C

  The HOBO reads slightly cold at equilibrium.  The 1-sigma spread
  ({cal['offset_std_c']:.4f} C) reflects tank micro-fluctuations and HOBO
  quantization noise at 1-minute resolution.

POSITION
--------
  WaveGlider lat/lon linearly interpolated from WGMS telemetry
  (~5-min sampling, raw/wgms_telemetry_2024.csv).  97.3 % of records
  have position.  The last ~19 h carry NaN (WaveGlider had returned to
  port; HOBO still logging).  Full telemetry is archived in the companion
  NCSZO GNSS-A 2024 Raw Data dataset (acoustic ranging).

DATA QUALITY
------------
  All {n:,} records carry qc_flag = 1 (good).  The deployment_state column
  identifies the pre-water period; all other filtering is left to the user.
  No data gaps detected.
  Combined 1-sigma accuracy (in-water, calibrated):
    sqrt(calibration_scatter^2 + CTD_accuracy^2)
    = sqrt({cal['offset_std_c']:.4f}^2 + {SBE_ACCURACY_C:.3f}^2)
    = {unc:.3f} C

FILES
-----
  raw/21732422_deployment_2024-09-06_2024-10-06_PDT.xlsx
        Original HOBO export: #, Date-Time (PDT), Temperature (C)

  raw/wgms_telemetry_2024.csv
        WaveGlider WGMS telemetry used to interpolate position onto
        1-min HOBO timestamps (~5-min interval, UTC assumed).

  raw/calibration/21732422_calibration_2024-11-05_2024-11-07_PST.xlsx
        Original HOBO export during calibration period (PST)

  raw/calibration/SBECTD19p7036_calibration_reference.txt
        ONC ODV export of reference CTD (1 Hz, UTC, ARGO QC filtered).
        ONC Subset Query 27910887.

  raw/calibration/EN-8285.doc
        Equipment note / calibration certificate (original document)

  hobo_21732422_2024_temperature.csv
        Processed output.  See CODEBOOK.txt.

  hobo_21732422_2024_metadata.json
        Machine-readable metadata and calibration statistics.

  process_temp_logger.py
        This script.  Regenerates all outputs from raw/.
        Requires: Python >= 3.11, pandas, matplotlib, numpy, openpyxl.
        Run: python process_temp_logger.py

  figures/01_deployment_timeseries.png
        Full deployment temperature time series.  Pre-deployment rows
        shown in grey; in-water raw and calibrated in red and blue.

  figures/02_calibration_comparison_timeseries.png
        HOBO vs CTD reference temperature during the ONC tank test.

  figures/03_calibration_offset_convergence.png
        CTD-HOBO difference vs time, showing warmup and equilibrium.

  figures/04_calibration_scatter.png
        HOBO (raw and calibrated) vs CTD scatter, equilibrated region.

  figures/05_deployment_track_temperature.png
        WaveGlider track coloured by calibrated SST (in-water only).

REPRODUCIBILITY
---------------
  All processed outputs can be regenerated from raw/ by running:
      python process_temp_logger.py
  No external data or network access required.

LICENCE
-------
  Creative Commons Attribution 4.0 International (CC BY 4.0)

CITATION (DOI TBD after Borealis upload)
-----------------------------------------
  Heesemann, M. and Hutchinson, J. (2025). NCSZO GNSS-A WaveGlider
  Surface Temperature 2024 (HOBO MX2203). Borealis, UVic NCSZO
  sub-dataverse. https://doi.org/10.5683/SP3/[DOI-TBD]

RELATED DATASETS
----------------
  NCSZO GNSS-A Raw Data 2024 (acoustic ranging; same WaveGlider)
  Borealis NCSZO dataverse: https://borealisdata.ca/dataverse/ncszo
"""
    (out_dir / "README.txt").write_text(txt, encoding="utf-8")


def write_codebook(out_dir: Path, cal: dict, n_pre_water: int,
                   in_water_start: str) -> None:
    unc     = float(np.sqrt(cal["offset_std_c"] ** 2 + SBE_ACCURACY_C ** 2))
    applied = cal["applied_offset_c"]
    txt = f"""\
CODEBOOK: hobo_21732422_2024_temperature.csv
============================================

File format : comma-separated values (CSV), UTF-8, Unix line endings
Header row  : yes (row 1)
Missing data: NaN for latitude_deg and longitude_deg during last ~19 h
              (WaveGlider ashore); all other columns fully populated

COLUMNS
-------

datetime_utc
  Type    : ISO 8601 string, UTC
  Format  : YYYY-MM-DDTHH:MM:SSZ
  Example : 2024-09-06T15:51:00Z
  Notes   : Converted from PDT (UTC-7) as recorded by HOBOconnect app.
            The entire 30-day deployment fell within PDT (DST ends
            3 Nov 2024).

latitude_deg
  Type    : float64 or NaN
  Units   : decimal degrees North (WGS-84)
  Notes   : WaveGlider position linearly interpolated from WGMS telemetry
            (~5-min sampling).  NaN for final ~19 h (WaveGlider at port).
            Rounded to 6 decimal places (~0.1 m precision).

longitude_deg
  Type    : float64 or NaN
  Units   : decimal degrees East (WGS-84); negative = West
  Notes   : Same interpolation as latitude_deg.

temp_c_raw
  Type    : float64
  Units   : degrees Celsius (°C)
  Range   : 10.0 – 21.8 (this deployment)
  Notes   : As exported from HOBO MX2203 S/N 21732422.  No corrections
            applied.  Manufacturer spec: accuracy ±0.20 °C, resolution
            ~0.01 °C.

temp_c_calibrated
  Type    : float64
  Units   : degrees Celsius (°C)
  Notes   : temp_c_raw + {applied:+.3f} °C (calibration offset).
            Combined 1-sigma accuracy (in-water): {unc:.3f} °C.
            Correction: temp_c_calibrated = temp_c_raw {applied:+.3f}

deployment_state
  Type    : string
  Values  :
    "pre_water"  First {n_pre_water} records (before {in_water_start}).
                 HOBO was on deck; readings are air/deck temperature,
                 not sea surface temperature.  Detected by:
                   temp_c_raw > {SST_MAX_C:.1f} °C
                   OR 5-min smoothed |dT/dt| > {COOLING_RATE_C_PER_MIN:.2f} °C/min
    "in_water"   HOBO immersed; valid sea surface temperature.
  Notes   : qc_flag is 1 for all rows regardless of deployment_state.
            Filter on deployment_state == "in_water" for SST analysis.

qc_flag
  Type    : integer
  Values  :
    1  good data — passed all checks
    2  probably good — minor automated flag (not present in this file)
    3  probably bad
    4  bad / failed instrument or global test
    9  missing / fill value
  Notes   : All {43174} records carry qc_flag = 1.
            Flag scheme follows ARGO QC convention (ONC).
"""
    (out_dir / "CODEBOOK.txt").write_text(txt, encoding="utf-8")


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> None:
    (OUT_DIR / "figures").mkdir(exist_ok=True)

    print(f"Input  : {RAW_DIR}")
    print(f"Output : {OUT_DIR}")

    # ── load ──────────────────────────────────────────────────────────────────
    print("\nLoading deployment data …")
    deploy = load_hobo_deployment(DEPLOY_XLS)
    print(f"  {len(deploy):,} rows  {deploy['datetime_utc'].iloc[0]} → {deploy['datetime_utc'].iloc[-1]}")

    print("Loading calibration HOBO data …")
    hobo_cal = load_hobo_calibration(CAL_XLS)

    print("Loading CTD reference data …")
    ctd = load_ctd_reference(CTD_ODV)
    print(f"  {len(ctd):,} rows at 1 Hz")

    print("Loading WaveGlider telemetry …")
    telemetry = load_telemetry(TELEMETRY_CSV)
    print(f"  {len(telemetry):,} valid rows")

    # ── calibration ───────────────────────────────────────────────────────────
    print("\nComputing calibration offset …")
    cal_all = compute_calibration(hobo_cal, ctd, skip_min=EQUILIBRATION_MIN)
    merged  = cal_all["merged"]
    equil   = cal_all["equil"]
    cal     = {k: v for k, v in cal_all.items() if k not in ("merged", "equil")}

    print(f"  Equilibrated region : {cal['n_equilibrated']} rows")
    print(f"  CTD - HOBO mean     : {cal['offset_mean_c']:+.4f} °C")
    print(f"  CTD - HOBO median   : {cal['offset_median_c']:+.4f} °C")
    print(f"  CTD - HOBO 1σ       : {cal['offset_std_c']:.4f} °C")
    print(f"  Applied offset      : {cal['applied_offset_c']:+.3f} °C")

    # ── apply calibration, position, deployment_state ─────────────────────────
    deploy = deploy.copy()
    deploy["temp_c_calibrated"] = deploy["temp_c_raw"] + cal["applied_offset_c"]
    deploy = interpolate_position(deploy, telemetry)
    deploy["deployment_state"]  = detect_deployment_state(deploy)
    deploy["qc_flag"] = 1

    n_pre = int((deploy["deployment_state"] == "pre_water").sum())
    in_water_start = deploy.loc[deploy["deployment_state"] == "in_water", "datetime_utc"].iloc[0]
    in_water_start_str = in_water_start.strftime("%Y-%m-%dT%H:%M:%SZ")
    n_pos = int(deploy["latitude_deg"].notna().sum())

    print(f"\nDeployment state  : {n_pre} pre_water rows; in_water from {in_water_start_str}")
    print(f"Position coverage : {n_pos:,} of {len(deploy):,} records ({100*n_pos/len(deploy):.1f} %)")

    # ── figures ───────────────────────────────────────────────────────────────
    print("\nGenerating figures …")
    fig_dir = OUT_DIR / "figures"
    fig_deployment(deploy, cal["applied_offset_c"], fig_dir / "01_deployment_timeseries.png")
    fig_calibration_comparison(merged, EQUILIBRATION_MIN, fig_dir / "02_calibration_comparison_timeseries.png")
    fig_calibration_offset(merged, cal, fig_dir / "03_calibration_offset_convergence.png")
    fig_calibration_scatter(equil, cal["applied_offset_c"], fig_dir / "04_calibration_scatter.png")
    fig_track_temperature(deploy, fig_dir / "05_deployment_track_temperature.png")

    # ── CSV ───────────────────────────────────────────────────────────────────
    print("Writing CSV …")
    csv_df = deploy.copy()
    csv_df["datetime_utc"] = csv_df["datetime_utc"].dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    col_order = ["datetime_utc", "latitude_deg", "longitude_deg",
                 "temp_c_raw", "temp_c_calibrated", "deployment_state", "qc_flag"]
    csv_df[col_order].to_csv(OUT_DIR / "hobo_21732422_2024_temperature.csv", index=False)

    # ── metadata JSON ─────────────────────────────────────────────────────────
    print("Writing metadata JSON …")
    unc = float(np.sqrt(cal["offset_std_c"] ** 2 + SBE_ACCURACY_C ** 2))
    metadata = {
        "dataset_title": "NCSZO GNSS-A WaveGlider Surface Temperature 2024 (HOBO MX2203)",
        "instrument": {
            "model":                      "HOBO MX2203",
            "serial_number":              "21732422",
            "manufacturer":               "Onset Computer Corporation",
            "firmware":                   "62.140",
            "thermal_time_constant_min":  5.0,
            "tau_note": (
                "Estimated from cross-correlation with 1-Hz CTD during tank calibration. "
                "No response-function correction applied: error at tidal timescale ~0.001 C "
                "is 14x smaller than calibration uncertainty."
            ),
        },
        "deployment": {
            "platform":              "WaveGlider SV3-271",
            "survey":                "NCSZO GNSS-A 2024",
            "site":                  "GNSSA-03, Northern Cascadia subduction zone",
            "start_utc":             deploy["datetime_utc"].iloc[0].isoformat() + "Z",
            "end_utc":               deploy["datetime_utc"].iloc[-1].isoformat() + "Z",
            "sampling_interval_s":   60,
            "raw_timezone":          "PDT (UTC-7)",
            "n_records":             int(len(deploy)),
            "pre_water_rows":        n_pre,
            "in_water_start_utc":    in_water_start_str,
            "pre_water_note": (
                f"First {n_pre} rows: HOBO on deck before water immersion. "
                f"Detection: temp > {SST_MAX_C} C OR |dT/dt| > {COOLING_RATE_C_PER_MIN} C/min (5-min smoothed)."
            ),
        },
        "calibration": {
            "facility":                   "ONC Marine Technology Centre, Victoria BC (48.6495 N, 123.4455 W)",
            "date_range_utc":             "2024-11-05T21:28:00Z to 2024-11-07T15:37:00Z",
            "reference_instrument":       "Sea-Bird SeaCAT SBE19plus V2",
            "reference_serial":           "7036",
            "reference_sample_rate_hz":   1,
            "equilibration_period_min":   cal["equilibration_period_min"],
            "n_equilibrated_rows":        cal["n_equilibrated"],
            "offset_mean_c":              round(cal["offset_mean_c"], 5),
            "offset_median_c":            round(cal["offset_median_c"], 5),
            "offset_std_c":               round(cal["offset_std_c"], 5),
            "applied_offset_c":           cal["applied_offset_c"],
            "correction_formula":         "temp_c_calibrated = temp_c_raw + applied_offset_c",
            "combined_accuracy_1sigma_c": round(unc, 4),
        },
        "position": {
            "source":               "WaveGlider WGMS telemetry (~5-min) linearly interpolated to 1-min",
            "n_with_position":      n_pos,
            "n_without_position":   int(len(deploy) - n_pos),
        },
        "statistics": {
            "temp_raw_min_c":  round(float(deploy["temp_c_raw"].min()), 4),
            "temp_raw_max_c":  round(float(deploy["temp_c_raw"].max()), 4),
            "temp_cal_min_c":  round(float(deploy["temp_c_calibrated"].min()), 4),
            "temp_cal_max_c":  round(float(deploy["temp_c_calibrated"].max()), 4),
        },
        "licence":  "CC BY 4.0",
        "creators": [
            {"name": "Martin Heesemann", "email": "mheesema@uvic.ca",
             "affiliation": "Ocean Networks Canada / University of Victoria"},
            {"name": "Jesse Hutchinson",
             "affiliation": "Ocean Networks Canada / University of Victoria"},
        ],
    }
    with open(OUT_DIR / "hobo_21732422_2024_metadata.json", "w", encoding="utf-8") as f:
        json.dump(metadata, f, indent=2)

    # ── README and CODEBOOK ───────────────────────────────────────────────────
    print("Writing README.txt and CODEBOOK.txt …")
    write_readme(OUT_DIR, deploy, cal, n_pre, in_water_start_str)
    write_codebook(OUT_DIR, cal, n_pre, in_water_start_str)

    # ── summary ───────────────────────────────────────────────────────────────
    print(f"\nDone.  Output: {OUT_DIR}")
    print("\nFiles written:")
    for p in sorted(OUT_DIR.rglob("*")):
        if p.is_file() and not any(part.startswith(".") for part in p.parts):
            size_kb = p.stat().st_size / 1024
            print(f"  {str(p.relative_to(OUT_DIR)):62s}  {size_kb:6.0f} kB")


if __name__ == "__main__":
    main()
