import pandas as pd, numpy as np
from pathlib import Path

logf = Path("results/paper_trading/trades.csv")
outf = Path("results/paper_trading/trade_summary.csv")
bucketf = Path("results/paper_trading/trades_by_bucket.csv")
if not logf.exists():
    raise SystemExit("trades.csv nicht gefunden (erst paper-phase laufen lassen).")

df = pd.read_csv(logf)

# Saubere Typen
num_cols = ["price","qty","equity","entry_px","fee","stop_px","risk_amt","size","cashflow","notional","rate","exit_px","pnl","weight"]
for c in num_cols:
    if c in df.columns:
        df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0.0)
df["time"] = pd.to_datetime(df["time"], utc=True, errors="coerce")
if "entry_time" in df.columns:
    df["entry_time"] = pd.to_datetime(df["entry_time"], utc=True, errors="coerce")
else:
    df["entry_time"] = pd.NaT

rows = []
# Pro Strategie chronologisch durchlaufen und Trades „zustandsbasiert“ schließen
for key, sub in df.sort_values("time").groupby("strategy_key", dropna=False):
    state = {
        "open": 0,             # 0 / +1 long / -1 short
        "entry_time": None,
        "entry_fee": 0.0,
        "funding_acc": 0.0,
        "risk_amt": 0.0,
        "symbol": None,
        "tf": None,
    }
    for _, r in sub.iterrows():
        act = str(r.get("action",""))

        # Funding während Position akkumulieren
        if act == "funding" and r.get("pos", 0) != 0 and r.get("qty", 0) > 0:
            state["funding_acc"] += float(r.get("cashflow", 0.0))
            continue

        # Entry
        if act in ("entry_long", "entry_short"):
            state["open"] = 1 if act == "entry_long" else -1
            state["entry_time"] = r["time"]
            state["entry_fee"] = float(r.get("fee", 0.0))
            state["funding_acc"] = 0.0
            state["risk_amt"] = float(r.get("risk_amt", 0.0))
            state["symbol"] = r.get("symbol", "")
            state["tf"] = r.get("timeframe", "")
            continue

        # Exit → Trade abschließen
        if act.startswith("exit_") and state["open"] != 0:
            exit_fee = float(r.get("fee", 0.0))
            gross_pnl = float(r.get("pnl", 0.0))                   # Preis-PnL (ohne Fees/Funding)
            fees = state["entry_fee"] + exit_fee
            funding = state["funding_acc"]
            net = gross_pnl - fees + funding
            hold_min = (r["time"] - state["entry_time"]).total_seconds()/60.0 if pd.notna(state["entry_time"]) else np.nan
            R = (net / abs(state["risk_amt"])) if abs(state["risk_amt"]) > 0 else np.nan

            rows.append({
                "strategy_key": key,
                "symbol": state["symbol"],
                "timeframe": state["tf"],
                "side": "long" if state["open"]==1 else "short",
                "entry_time": state["entry_time"],
                "exit_time": r["time"],
                "hold_min": hold_min,
                "gross_pnl": gross_pnl,
                "fees": fees,
                "funding": funding,
                "net_pnl": net,
                "R_multiple": R
            })
            # Reset
            state = {"open": 0, "entry_time": None, "entry_fee": 0.0, "funding_acc": 0.0,
                     "risk_amt": 0.0, "symbol": None, "tf": None}

trades = pd.DataFrame(rows)
if trades.empty:
    print("Keine abgeschlossenen Trades rekonstruiert.")
    trades.to_csv(outf, index=False)
    raise SystemExit()

# Je-Strategie Summary
grp = trades.groupby(["strategy_key","symbol","timeframe"])
summary = grp.agg(
    n_trades=("net_pnl","size"),
    win_rate=("net_pnl", lambda x: float((x>=0).mean())),
    avg_hold_min=("hold_min","mean"),
    gross_pnl_sum=("gross_pnl","sum"),
    fees_sum=("fees","sum"),
    funding_sum=("funding","sum"),
    net_pnl_sum=("net_pnl","sum"),
    avg_net_per_trade=("net_pnl","mean"),
    avg_R=("R_multiple","mean"),
    median_R=("R_multiple","median"),
).reset_index().sort_values("net_pnl_sum", ascending=False)

# Gesamtzeile anhängen
total = pd.DataFrame([{
    "strategy_key":"__PORTFOLIO__", "symbol":"ALL", "timeframe":"-",
    "n_trades": int(trades.shape[0]),
    "win_rate": float((trades["net_pnl"]>=0).mean()),
    "avg_hold_min": float(trades["hold_min"].mean()),
    "gross_pnl_sum": float(trades["gross_pnl"].sum()),
    "fees_sum": float(trades["fees"].sum()),
    "funding_sum": float(trades["funding"].sum()),
    "net_pnl_sum": float(trades["net_pnl"].sum()),
    "avg_net_per_trade": float(trades["net_pnl"].mean()),
    "avg_R": float(trades["R_multiple"].mean()),
    "median_R": float(trades["R_multiple"].median()),
}])
out = pd.concat([summary, total], ignore_index=True)

out.to_csv(outf, index=False)
by = trades.groupby(["symbol","timeframe"]).agg(
    n_trades=("net_pnl","size"),
    net_pnl=("net_pnl","sum"),
    win_rate=("net_pnl", lambda x: float((x>=0).mean())),
    avg_R=("R_multiple","mean"),
).reset_index()
by.to_csv(bucketf, index=False)

print(out.head(10).to_string(index=False))
print(f"[OK] saved {outf} and {bucketf}")
