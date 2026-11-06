"""Generate a 365-day-calendar QuantStats report from recorded paper equity."""
import io
import os
from pathlib import Path
import httpx


def main():
    import pandas as pd
    import quantstats as qs
    url = os.environ.get("TINA_CONTROL_URL", "http://control:8081")
    with httpx.Client(timeout=30, trust_env=False) as client:
        result = client.get(url + "/v1/equity.csv", headers={"Authorization": "Bearer " + os.environ["TINA_READ_TOKEN"]})
        result.raise_for_status()
    frame = pd.read_csv(io.StringIO(result.text), parse_dates=["timestamp"])
    if frame.empty:
        raise SystemExit("No equity observations recorded yet")
    series = frame.set_index("timestamp")["equity"].sort_index().resample("1D").last()
    if series.isna().any() or len(series) < 31:
        raise SystemExit("Need 31 consecutive UTC daily equity observations; missing days are not filled")
    returns = series.pct_change(fill_method=None).dropna()
    returns.index = returns.index.tz_localize(None)
    Path("reports").mkdir(exist_ok=True)
    qs.reports.html(returns, output="reports/paper-performance.html", periods_per_year=365,
                    title="TINA paper performance (simulated fills; not a live track record)")
    print("Wrote reports/paper-performance.html")


if __name__ == "__main__":
    main()
