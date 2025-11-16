from __future__ import annotations
from pathlib import Path
import json, textwrap, datetime
import pandas as pd

ROOT = Path(".")
RES  = ROOT / "results"
BT   = RES / "backtests"
FW   = RES / "forward_tests"
PORT = RES / "portfolios"
PAPR = RES / "paper_trading"
OUT_MD = RES / "report.md"

def _load_json(path: Path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None

def _maybe_df_csv(path: Path):
    if path.exists():
        try:
            return pd.read_csv(path)
        except Exception:
            pass
    return None

def _fmt_pct(x):
    try:
        return f"{100*float(x):.2f}%"
    except Exception:
        return "n/a"

def _to_md(df: pd.DataFrame) -> str:
    """Markdown-Tabelle: nutzt tabulate, wenn vorhanden – sonst einfacher Fallback."""
    try:
        return df.to_markdown(index=False)  # nutzt 'tabulate', falls installiert
    except Exception:
        cols = list(map(str, df.columns))
        header = "| " + " | ".join(cols) + " |"
        sep    = "| " + " | ".join(["---"]*len(cols)) + " |"
        rows = []
        for _, row in df.iterrows():
            vals = [str(v) for v in row.tolist()]
            rows.append("| " + " | ".join(vals) + " |")
        return "\n".join([header, sep, *rows])

def maybe_plot_equity():
    try:
        import matplotlib.pyplot as plt
    except Exception:
        return []
    figs = []
    for name, fpath in [
        ("Portfolio equity", PORT / "portfolio_equity.parquet"),
        ("Paper equity",     PAPR / "paper_equity.parquet"),
    ]:
        if fpath.exists():
            try:
                df = pd.read_parquet(fpath)
                if "equity" not in df.columns: continue
                plt.figure()
                df["equity"].plot(title=name)
                out_png = fpath.with_suffix(".png")
                plt.xlabel("time"); plt.ylabel("equity")
                plt.tight_layout()
                plt.savefig(out_png)
                plt.close()
                figs.append(out_png)
            except Exception:
                pass
    return figs

def main():
    now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    md = []
    md.append(f"# XY – Statusreport\n\n_Generiert: {now}_\n")

    # Backtest
    bt_metrics = _maybe_df_csv(BT / "metrics.csv")
    if bt_metrics is not None and not bt_metrics.empty:
        top = bt_metrics.sort_values("net_return", ascending=False).head(10)
        md.append("## Backtest – Top 10 (net_return)\n")
        md.append(_to_md(top[["symbol","timeframe","fast","slow","stop_loss_pct","trades","net_return","max_drawdown","avg_monthly_return","worst_month"]]))
        md.append("")

    # Evaluate Backtest
    bt_acc = _load_json(BT / "accepted_strategies.json") or []
    md.append(f"- Backtest accepted: **{len(bt_acc)}**\n")

    # Forward (aggregiert)
    fw_acc = _load_json(FW / "accepted_strategies.json") or []
    md.append(f"- Forward (aggregated) accepted: **{len(fw_acc)}**\n")
    splits = []
    for p in sorted(FW.glob("split_*")):
        df = _maybe_df_csv(p / "accepted_metrics.csv")
        if df is not None:
            cnt = int(df[df.get("is_accepted", False) == True].shape[0])
            splits.append((p.name, cnt))
    if splits:
        items = ", ".join([f"{name}:{cnt}" for name, cnt in splits])
        md.append(f"  - Per-split accepted: {items}\n")

    # Portfolio
    md.append("\n## Portfolio\n")
    sel = _load_json(PORT / "selection.json") or {}
    ws  = sel.get("weights", {})
    if ws:
        dfw = pd.DataFrame(sorted(ws.items(), key=lambda kv: kv[1], reverse=True), columns=["strategy_key","weight"])
        md.append(_to_md(dfw))
        md.append("")
        rep = _load_json(PORT / "validation_report.json")
        if rep:
            md.append(f"- Sum weights: **{rep.get('sum_weights', 'n/a')}** | ENB: **{rep.get('enb', 0):.2f}**")
            md.append(f"- Caps: per strategy ≤ **{rep.get('max_w_per_strategy')}**, per market ≤ **{rep.get('max_w_per_market')}**, corr_cap **{rep.get('correlation_cap')}**")
            viol = rep.get("violations", {})
            if any(viol.values()):
                md.append(f"- **Violations**: {viol}")
            else:
                md.append("- Violations: **none**")
            md.append("")

    # Paper
    md.append("## Paper Trading\n")
    tr_sum = _maybe_df_csv(PAPR / "trade_summary.csv")
    if tr_sum is not None and not tr_sum.empty:
        port_row = tr_sum[tr_sum["strategy_key"]=="__PORTFOLIO__"]
        if not port_row.empty:
            r = port_row.iloc[0].to_dict()
            md.append(f"- Trades: **{int(r['n_trades'])}**, Win‑Rate: **{_fmt_pct(r['win_rate'])}**, ∅R: **{r['avg_R']:.3f}**, Fees: **{r['fees_sum']:.2f}**, Funding: **{r['funding_sum']:.2f}**, Net‑PnL: **{r['net_pnl_sum']:.2f}**")
        strat_rows = tr_sum[tr_sum["strategy_key"]!="__PORTFOLIO__"][["strategy_key","symbol","timeframe","n_trades","win_rate","avg_R","net_pnl_sum"]]
        if not strat_rows.empty:
            md.append("\n**Per Strategy:**\n")
            md.append(_to_md(strat_rows.sort_values("net_pnl_sum", ascending=False)))
        md.append("")
    else:
        md.append("- Noch keine `trade_summary.csv` gefunden (Analyzer laufen lassen?)\n")

    # Plots (optional)
    figs = maybe_plot_equity()
    for f in figs:
        rel = f.relative_to(ROOT).as_posix()
        md.append(f"![{f.stem}]({rel})")

    OUT_MD.write_text("\n".join(md), encoding="utf-8")
    print(f"[OK] report -> {OUT_MD}")

if __name__ == "__main__":
    main()
