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
                    (±0.014 °C).  In field conditions the
                    WaveGlider moves at 1–2 kt, reducing τ further.

DEPLOYMENT
----------
  Platform        : WaveGlider SV3-271
  Survey          : NCSZO GNSS-A 2024
  Site            : GNSSA-03, Northern Cascadia subduction zone
  Start (UTC)     : 2024-09-06T15:51:00Z
  End   (UTC)     : 2024-10-06T15:24:00Z
  Duration        : 30.0 days
  Sampling period : 60 s
  Raw timezone    : PDT (UTC-7); converted to UTC in processed file

PRE-DEPLOYMENT PERIOD
---------------------
  The WaveGlider was released into the water on 2024-09-06 at 10:10 UTC.
  The HOBO logger was activated at 15:51 UTC while still on the ship, and
  was transferred to the WaveGlider and deployed into the ocean at ~17:22 UTC
  (5.5 hours after the WaveGlider was released).

  The first 91 records (15:51–17:21 UTC) carry
  deployment_state = "pre_water".  They reflect air/deck temperature
  (~21–11 °C, cooling as the HOBO was moved toward the water) rather than
  sea surface temperature.  latitude_deg and longitude_deg are NaN for
  these rows: the telemetry gives the WaveGlider's position (already at
  sea), which is not the HOBO's location while it was on the ship.

  Detection thresholds used:
    temp_c_raw > 17.0 °C  (above max plausible Sep SST at GNSSA-03)
    OR 5-min smoothed |dT/dt| > 0.05 °C/min (still equilibrating)

CALIBRATION
-----------
  Date            : 2024-11-05 to 2024-11-07 (post-deployment)
  Facility        : ONC Marine Technology Centre, Victoria BC
                    (48.6495 N, 123.4455 W)
  Reference       : Sea-Bird SeaCAT SBE19plus V2, S/N 7036
                    Permanently deployed at ONC Integration Testing
                    (1 Hz, UTC timestamps, ARGO QC flags 1-2 retained)
  Method          : HOBO immersed alongside reference CTD in a tank.
                    First 60 min discarded (thermal warmup transient).
                    Offset computed from 2452 equilibrated minute-pairs.
                    Note: the tank had an active temperature cycle (±0.7 °C
                    amplitude over ~15-hour periods), providing good coverage
                    for calibration across a temperature range.

  Calibration results:
    CTD - HOBO offset (mean)   : +0.0280 C
    CTD - HOBO offset (median) : +0.0232 C  <- applied
    CTD - HOBO offset (1 sigma): 0.0141 C
    Applied correction         : temp_calibrated = temp_raw +0.023 C

  The HOBO reads slightly cold at equilibrium.  The 1-sigma spread
  (0.0141 C) reflects tank micro-fluctuations and HOBO
  quantization noise at 1-minute resolution.

POSITION
--------
  WaveGlider lat/lon linearly interpolated from WGMS telemetry
  (~5-min sampling, raw/wgms_telemetry_2024.csv).
  NaN in two periods:
    - Pre-water (91 rows, 15:51–17:21 UTC Sep 6): HOBO was on
      the ship; telemetry gives the WaveGlider's position, not the ship's.
    - Final ~19 h: WaveGlider had returned to port; HOBO still logging.
  Full telemetry is archived in the companion NCSZO GNSS-A 2024 Raw Data
  dataset (acoustic ranging).

DATA QUALITY
------------
  All 43,174 records carry qc_flag = 1 (good).  The deployment_state column
  identifies the pre-water period; all other filtering is left to the user.
  No data gaps detected.
  Combined 1-sigma accuracy (in-water, calibrated):
    sqrt(calibration_scatter^2 + CTD_accuracy^2)
    = sqrt(0.0141^2 + 0.005^2)
    = 0.015 C

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

  figures/04_calibration_residuals.png
        HOBO minus CTD residuals vs CTD temperature, equilibrated region,
        split into heating and cooling phases to show thermal-lag bias.

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
