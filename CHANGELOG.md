# Changelog

## 1.1.4 — 2026-11-26

First public release.

- Week program sensor with blocks, per-day grouping, durations and preset
  temperatures as attributes.
- Recurring weekly calendar of the program, with preset and temperature in the
  event title.
- Five preset temperature `number` entities (5–30 °C, step 0.5).
- Sensors for the active preset, its temperature, the next preset and the next
  change.
- Services `set_schedule`, `set_day`, `create_backup` and `restore_backup`.
- Automatic backup before every write, manual backup button, retention of the
  20 newest backups per kind, and restore with a Toon-identity check.
- Config flow with reconfigure and poll-interval options, English and Dutch
  translations.
- Diagnostics with the host redacted.
- Lovelace card: week overview, per-day editor with add/remove/copy, preset
  temperature panel, and a responsive layout that keeps time, preset,
  temperature and delete on one row whenever the labels fit.
