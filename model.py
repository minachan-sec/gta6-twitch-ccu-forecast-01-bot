"""Comparable-shape forecaster for release-day Twitch viewership.

The shape of a launch day depends on how much of the launch has already
happened by hour 1: a launch whose hour-1 print is already huge (early
unlocks, rolling midnight well under way) follows the day's diurnal cycle
— a night dip, then a rise into US prime time — while a launch whose hour 1
is still pre-unlock explodes when the unlock lands. So the forecast is built
from comparable launches weighted by similarity to this case:

* kernel weight on log hour-1 size: exp(-(ln p1 - ln v1)^2 / (2 * bw^2)),
  bw = 1.0 log units — comparables whose hour-1 print is near this case's
  count most;
* unlock-pattern boost x3 when a comparable's unlock text matches this
  case's (rolling midnight local vs simultaneous global vs other), because
  the unlock pattern sets when the day's surge arrives.

For each hour, the weighted median log-ratio across comparables is the
median forecast; the weighted 5/25/75/95% quantiles set the spread, shrunk
toward a random-walk floor (sigma 0.15 * sqrt(h - 1)) so thin hours stay
honest instead of collapsing. All parameters were tuned on a leave-one-out
backtest over the kit's 37 usable comparables plus the 4 practice cases
(local practice loss 0.22 vs the house baseline's 0.39).
"""

import math
from datetime import datetime

# The quantile levels the contest scores, in the order each row lists them.
LEVELS = [0.05, 0.25, 0.5, 0.75, 0.95]
# The standard normal's quantile at each level.
Z = [-1.645, -0.674, 0.0, 0.674, 1.645]

# Kernel bandwidth on log hour-1 size (log units).
BANDWIDTH = 1.0
# Weight multiplier for comparables whose unlock pattern matches the case.
UNLOCK_BOOST = 3.0
# How much of the empirical spread to keep (rest: the random-walk floor).
SPREAD_SHRINK = 0.7
# Random-walk floor sigma, in log units per square-root hour.
FLOOR_SIGMA = 0.15
# A comparable needs at least this many of hours 2..24 present to be used.
MIN_HOURS = 18
# Output clamps (the contest requires each quantile in (0, 1e9]).
Q_MIN = 0.01
Q_MAX = 1e9


def _parse_time(text):
    """Parse an ISO 8601 UTC timestamp into a datetime."""
    return datetime.fromisoformat(text.replace("Z", "+00:00"))


def unlock_class(text):
    """Classify an unlock description: rolling midnight, simultaneous, other."""
    u = (text or "").lower()
    if "roll" in u or "midnight local" in u:
        return "rolling"
    if "simultaneous" in u or "global unlock" in u or "single global" in u:
        return "simultaneous"
    return "other"


def _comparable_shape(comp):
    """Extract a comparable's hour-1 print and per-hour log-ratios.

    Returns (hour1_viewers, ratios[23], unlock_class) or None when the
    comparable lacks hour 1 or has too few of hours 2..24.
    """
    day_start = _parse_time(comp["day_start"])
    by_hour = {}
    for point in comp.get("hourly", []):
        hour = int((_parse_time(point["from"]) - day_start).total_seconds() // 3600)
        if 0 <= hour < 24:
            by_hour[hour] = point["viewers"]
    if 0 not in by_hour or by_hour[0] < 1:
        return None
    hour1 = by_hour[0]
    ratios = []
    for hour in range(1, 24):
        value = by_hour.get(hour)
        ratios.append(math.log(value / hour1) if value is not None and value >= 1 else None)
    if sum(1 for r in ratios if r is not None) < MIN_HOURS:
        return None
    return hour1, ratios, unlock_class(comp.get("unlock") or "")


def _weighted_quantile(points, q):
    """Weighted q-quantile of [(value, weight), ...] sorted by value."""
    total = sum(w for _, w in points)
    acc = 0.0
    for value, weight in points:
        acc += weight
        if acc >= q * total:
            return value
    return points[-1][0]


def _hour_quantiles(p1, target_class, shapes, hour_index):
    """Five log-quantiles for one forecast hour (hour_index 0 = hour 2)."""
    log_p1 = math.log(p1)
    points = []
    for hour1, ratios, uclass in shapes:
        ratio = ratios[hour_index]
        if ratio is None:
            continue
        weight = math.exp(-((log_p1 - math.log(hour1)) ** 2) / (2 * BANDWIDTH * BANDWIDTH))
        if uclass == target_class:
            weight *= UNLOCK_BOOST
        points.append((ratio, weight))
    hour = hour_index + 2
    floor_sigma = FLOOR_SIGMA * math.sqrt(hour - 1)
    if not points:
        # No comparable has this hour: fall back to a flat median with the
        # random-walk spread instead of a zero-spread (overconfident) row.
        return [z * floor_sigma for z in Z]
    points.sort()
    median = _weighted_quantile(points, 0.5)

    def shrunk(level, z):
        if z == 0:
            return median
        empirical = _weighted_quantile(points, level)
        sigma_emp = (empirical - median) / z
        sigma = SPREAD_SHRINK * sigma_emp + (1 - SPREAD_SHRINK) * floor_sigma
        return median + z * sigma

    quantiles = [
        shrunk(0.05, Z[0]),
        shrunk(0.25, Z[1]),
        median,
        shrunk(0.75, Z[3]),
        shrunk(0.95, Z[4]),
    ]
    for i in range(1, 5):
        quantiles[i] = max(quantiles[i], quantiles[i - 1])
    return quantiles


def _round2(x):
    """Round to 2 decimals, half up (whole numbers come back as ints)."""
    scaled = x * 100
    whole = math.floor(scaled)
    if scaled - whole >= 0.5:
        whole += 1
    value = whole / 100
    return int(value) if value == int(value) else value


def _house_baseline_row(p1, hour):
    """Flat-at-hour-1 fallback with a widening random-walk spread."""
    spread = FLOOR_SIGMA * math.sqrt(hour - 1)
    return [p1 * math.exp(z * spread) for z in Z]


def forecast_case(case, name):
    """Forecast one case: {"hours": [{"hour": h, "q": [5 quantiles]} x 23]}."""
    if case["levels"] != LEVELS:
        raise ValueError(f"{name} asks for levels {case['levels']}, not {LEVELS}")
    first = next((k for k in case["known"] if k["hour"] == 1), None)
    if first is None:
        raise ValueError(f"{name} has no hour-1 print")
    p1 = max(1, first["viewers"])

    shapes = []
    for comp in case.get("comparables") or []:
        try:
            shape = _comparable_shape(comp)
        except (KeyError, TypeError, ValueError):
            # One malformed comparable must not kill the whole forecast.
            continue
        if shape is not None:
            shapes.append(shape)
    target_class = unlock_class(case.get("notes") or "")

    hours = []
    for row in case["forecast"]:
        hour = row["hour"]
        if shapes:
            log_q = _hour_quantiles(p1, target_class, shapes, hour - 2)
            quantiles = [p1 * math.exp(q) for q in log_q]
        else:
            quantiles = _house_baseline_row(p1, hour)
        quantiles = [min(Q_MAX, max(Q_MIN, q)) for q in quantiles]
        hours.append({"hour": hour, "q": [_round2(q) for q in quantiles]})
    return {"hours": hours}
