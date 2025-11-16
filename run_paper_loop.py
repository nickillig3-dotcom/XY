from __future__ import annotations
from pathlib import Path
import time, json, subprocess
from datetime import datetime, timezone
from src.config_extras import load_extras
from src.execution import run_paper

def main():
    ex = load_extras("config/config.yaml")
    lb_days   = int(ex["paper"].get("lookback_days", 14))
    interval  = int(ex["paper"].get("poll_seconds", 300))
    do_analyze = bool(ex["paper"].get("analyze_trades", True))

    print(f"[loop] lookback_days={lb_days} | interval={interval}s | analyze_trades={do_analyze}")
    try:
        while True:
            ts = datetime.now(timezone.utc).isoformat(timespec="seconds")
            out = run_paper(lookback_days=lb_days)
            print(f"[{ts}] Paper run -> {out}")
            if do_analyze:
                try:
                    subprocess.run(["python", "analyze_trades.py"], check=False)
                except Exception as e:
                    print(f"[WARN] analyze_trades failed: {e}")
            time.sleep(interval)
    except KeyboardInterrupt:
        print("[loop] interrupted, exiting.")

if __name__ == "__main__":
    main()
