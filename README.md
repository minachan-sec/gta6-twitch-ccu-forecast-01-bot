# GTA VI Twitch CCU Forecaster

Forecasts how many people watch Grand Theft Auto VI live on Twitch in each
hour (2–24) of its release day, 2026-11-19 UTC, as five quantiles per hour
(5%, 25%, 50%, 75%, 95%). Scored by mean pinball loss on the log scale.

## Method: kernel-weighted comparable shapes

The shape of a launch day depends on how much of the launch has already
happened by hour 1. A launch whose hour-1 print is already huge follows the
day's diurnal cycle (night dip, rise into US prime time); a launch whose
hour 1 is still pre-unlock explodes when the unlock lands. So each hour's
forecast is built from the 38–42 comparable past launches in the case file,
weighted by similarity to this case:

- **Kernel on log hour-1 size** (bandwidth 1.0): comparables whose hour-1
  print is near this case's count most.
- **Unlock-pattern boost ×3**: comparables whose unlock text matches this
  case's notes (rolling midnight local vs simultaneous global vs other),
  because the unlock pattern sets when the day's surge arrives.

Per hour, the weighted median log-ratio across comparables is the median
forecast; the weighted 5/25/75/95% quantiles set the spread, shrunk 70/30
toward a random-walk floor (σ 0.15·√(h−1)) so thin hours stay honest.

## Validation

- Leave-one-out backtest over the kit's 37 usable comparables: mean pinball
  loss **0.39** vs the house baseline's **0.93**; on big hour-1 launches
  (the GTA VI regime) **0.20** vs **0.26**.
- Local practice score on the 4 real practice cases (actuals from
  SullyGnome's public hourly averages, validated to match the cases'
  hour-1 prints exactly): **0.22** vs the house baseline's **0.39**
  (the house figure is confirmed by the kit's own RULES.txt).

  | Practice case | Hour-1 viewers | House baseline | This model |
  |---|---|---|---|
  | Marvel's Wolverine (2026) | 23,357 | 0.744 | 0.369 |
  | Red Dead Redemption 2 (2018) | 116,550 | 0.287 | 0.180 |
  | God of War Ragnarök (2022) | 269,517 | 0.215 | 0.136 |
  | Marvel's Spider-Man 2 (2023) | 119,087 | 0.303 | 0.202 |
  | **Mean** | | **0.387** | **0.222** |

## Files

- `main.py` — entrypoint: reads every `*.in` from the input directory,
  writes one `*.out` per case. A malformed case still gets a valid
  fallback forecast (flat at hour 1, widening spread) instead of no file.
- `model.py` — the forecaster (pure functions of the case file; no network,
  no randomness, deterministic output). Malformed comparables are skipped
  instead of crashing the run.
- `.makefun/owner.json` — payout wallet for this wallet-only account.

## Runtime checks (all verified locally)

- Two runs on the same cases write **byte-identical** output.
- Runtime: **0.2 s for all 4 practice cases** (limit: 8 s per case).
- Output: 23 rows, hours 2–24, five non-decreasing quantiles per row, all
  in (0, 1e9], ~1.5 KB per file (limit: 65,536 bytes).
- Synthetic end-to-end cases built from comparables (leave-one-out through
  the actual program): Elden Ring 0.115, Cyberpunk 2077 0.156, Call of
  Duty: Black Ops 7 0.142, Modern Warfare III 0.131. Tiny hour-1 launches
  (Silksong, Kingdom Come: Deliverance II) score ~0.8 — that regime is
  intrinsically unpredictable, and GTA VI will not be in it.
- Edge case (hour-1 print of 1, zero comparables): falls back cleanly to
  the flat baseline, no crash.

## Run locally

```sh
mkdir -p out && MAKEFUN_INPUT_DIR=<kit>/input MAKEFUN_OUTPUT_DIR=out python3 main.py
```
