"""GTA VI Twitch CCU forecaster: kernel-weighted comparable-shape model.

Entrypoint (Python 3.13, standard library only). The grader runs
`python3 -P -s /bot/main.py` once per case: it reads that case's file from
/input and writes one forecast file to /output.

Method (see README.md): for each hour 2..24 of release day, forecast five
quantiles of Twitch concurrent viewers. The median comes from the log-ratio
shape of comparable past launches, kernel-weighted by how close each
comparable's hour-1 print is to this case's hour-1 print (log scale) and
boosted when the comparable's unlock pattern matches this case's; the spread
comes from the weighted dispersion of those shapes, shrunk toward a
random-walk floor. Everything is a pure function of the case file, so two
runs on the same case write identical bytes.
"""

import json
import math
import os
import sys
from pathlib import Path

# The grader's -P leaves /bot off sys.path: put it back first, so `import model`
# finds the model.py shipped beside this file.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from model import forecast_case  # noqa: E402

INPUT_DIR = Path(os.environ.get("MAKEFUN_INPUT_DIR", "/input"))
OUTPUT_DIR = Path(os.environ.get("MAKEFUN_OUTPUT_DIR", "/output"))


def _fallback_forecast(case):
    """Last-resort forecast: flat at the hour-1 print with widening spread.

    Only used when the model itself raises (malformed case data); a valid
    output file with a mediocre score beats a missing file.
    """
    try:
        p1 = max(1, next(k["viewers"] for k in case["known"] if k["hour"] == 1))
    except (KeyError, StopIteration, TypeError):
        p1 = 1
    z = [-1.645, -0.674, 0.0, 0.674, 1.645]
    return {
        "hours": [
            {
                "hour": h,
                "q": [max(0.01, min(1e9, p1 * math.exp(zv * 0.15 * math.sqrt(h - 1)))) for zv in z],
            }
            for h in range(2, 25)
        ]
    }


def main() -> None:
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    # Every case file, in name order, so two runs write the same bytes.
    for path in sorted(INPUT_DIR.glob("*.in")):
        try:
            case = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, UnicodeDecodeError):
            # Unparseable input still gets a valid (flat) output file.
            forecast = _fallback_forecast({"known": []})
            (OUTPUT_DIR / f"{path.stem}.out").write_text(
                json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
            )
            continue
        try:
            forecast = forecast_case(case, path.name)
        except (KeyError, TypeError, ValueError):
            forecast = _fallback_forecast(case)
        (OUTPUT_DIR / f"{path.stem}.out").write_text(
            json.dumps(forecast, separators=(",", ":")) + "\n", encoding="utf-8"
        )


if __name__ == "__main__":
    main()
