
# Compare the HOBO temperature sensor to a SeaBird CTD (EN-8285)

**Status:** Closed

**Project:** Engineering — Test and Development

**Created:** 05 Nov 2024
**Updated:** 19 Sep 2025
**Due:** 29 Nov 2024
**Resolved:** 15 Nov 2024

## Summary

We compared a HOBO MX TidbiT 400 autonomous temperature sensor to a reference SeaBird CTD temperature sensor to assess agreement and behaviour during a short tank test.

## Description

- HOBO MX TidbiT 400 was attached to the CTD cage and recorded temperature while hanging in the test tank at approximately the same height as the CTD's temperature sensor.
- The CTD driver was running so reference data could be retrieved from Oceans 3.0.
- This was an engineering test only; no Data Stewardship or DAQ requirements applied.

## Key Observations

- HOBO readings were lower than the reference during cooling with an accuracy around ~0.015–0.02 °C.
- During warming, the difference increased to ~0.35–0.4 °C (observed, not a formal analysis).

## Attachments (from the original ticket)

- 21732422 2024-11-07 07_37_50 PST (Data PST).xlsx
- HOBO_Reference_CTD_temperature_comparison.xlsx
- HOBO_vs_Reference_temperature_difference.xlsx
- SBECTD19p7036_Temperature_20241105T213800Z_20241107T153659Z-NaN_clean_ODV.txt
- Screenshot (106).png

## Comments / Notes

- 05 Nov 2024 — Test planned and attached to CTD cage at ~21:10 UTC.
- 07 Nov 2024 — Removed at ~15:37 UTC.
- 15 Nov 2024 — Observed the asymmetric difference when warming vs cooling (see Key Observations).
- 19 Sep 2025 — Ticket referenced again for context.

## Files

Original source file: EN-8285.doc (ticket export) located alongside this README.

Data and analysis spreadsheets are listed above in Attachments.

## Suggested next steps

- Run a proper paired analysis (time-align, resample, plot) using the attached spreadsheets.
- If systematic bias is confirmed, consider sensor-specific correction or investigate mounting/thermal lag effects.

---
Generated from ticket export: EN-8285.doc
