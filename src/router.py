from __future__ import annotations
from pathlib import Path
import json, csv
from typing import Dict, List, Tuple
import pandas as pd
from datetime import datetime, timezone, date

from src.config_loader import load_config
from src.config_extras import load_extras
from src.strategy_blocks import StrategyConfig
from src.backtest import _load_ohlcv, _resample_ohlcv
from src.signals import make_key

class DryRouter:
    def __init__(self, cfg, extras, root: Path):
        self.cfg = cfg
        self.extras = extras
        self.root = root
        self.live_dir = root / "results/live"
        self.live_dir.mkdir(parents=True, exist_ok=True)
        self.state_path = self.live_dir / "state.json"
        self.log_path = self.live_dir / "orders_log.csv"
        self.killswitch_path = Path(self.extras.get("live", {}).get("killswitch_path", "results/live/KILL"))
        self.use_weights = bool(self.extras.get("live", {}).get("use_portfolio_weights", True))
        self.daily_limit_pct = float(self.extras.get("live", {}).get("daily_loss_limit_pct", 0.02))
        self.max_notional_cfg = float(self.extras.get("live", {}).get("max_notional", 0.0))
        self.port_weights = self._load_portfolio_weights()
        self._load_state()
        self._rollover_day_if_needed()

    # ---------- utils ----------
    def _now_iso(self):
        return datetime.now(timezone.utc).isoformat(timespec="seconds")

    def _append_log(self, row: Dict):
        header = ["time","strategy_key","symbol","timeframe","event","side","price","qty","fee","pnl","equity_after","reason"]
        write_header = not self.log_path.exists()
        with self.log_path.open("a", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=header)
            if write_header: w.writeheader()
            w.writerow({k: row.get(k, "") for k in header})

    def killswitch(self) -> bool:
        return self.killswitch_path.exists()

    def _touch_killswitch(self):
        self.killswitch_path.parent.mkdir(parents=True, exist_ok=True)
        self.killswitch_path.write_text("KILL", encoding="utf-8")

    def _load_portfolio_weights(self) -> Dict[str, float]:
        sel_p = self.root / "results/portfolios/selection.json"
        if not sel_p.exists():
            return {}
        try:
            j = json.loads(sel_p.read_text(encoding="utf-8"))
            return {k: float(v) for k, v in (j.get("weights", {}) or {}).items()}
        except Exception:
            return {}

    def _load_state(self):
        if self.state_path.exists():
            try:
                self.state = json.loads(self.state_path.read_text(encoding="utf-8"))
            except Exception:
                self.state = {}
        else:
            self.state = {}
        self.state.setdefault("equity", float(self.cfg.risk.starting_capital))
        self.state.setdefault("positions", {})  # key -> {side, qty, entry_px, stop_px, opened_at, last_checked}
        self.state.setdefault("processed_signals", [])
        # Tagestracking
        utc_today = date.fromtimestamp(datetime.now(timezone.utc).timestamp())
        self.state.setdefault("day_tag", utc_today.isoformat())
        self.state.setdefault("day_start_equity", float(self.state["equity"]))
        self.state.setdefault("realized_today", 0.0)

    def _save_state(self):
        self.state_path.write_text(json.dumps(self.state, indent=2), encoding="utf-8")

    def _rollover_day_if_needed(self):
        utc_today = date.fromtimestamp(datetime.now(timezone.utc).timestamp()).isoformat()
        if self.state.get("day_tag") != utc_today:
            self.state["day_tag"] = utc_today
            self.state["day_start_equity"] = float(self.state["equity"])
            self.state["realized_today"] = 0.0
            self._append_log({
                "time": self._now_iso(), "strategy_key":"", "symbol":"", "timeframe":"",
                "event":"day_rollover","side":"", "price":"", "qty":"", "fee":"", "pnl":"", "equity_after": self.state["equity"], "reason":"NEW_DAY"
            })
            self._save_state()

    # ---------- risk & sizing ----------
    def _calc_qty(self, strat: StrategyConfig, entry_px: float, stop_px: float, equity: float, skey: str) -> float:
        dist = abs(entry_px - stop_px)
        if dist <= 0 or entry_px <= 0:
            return 0.0
        base_risk = equity * float(strat.risk_fraction)
        if self.use_weights and skey in self.port_weights:
            base_risk *= float(self.port_weights[skey])  # proportional zum Portfoliogewicht
        max_notional_by_leverage = equity * float(self.cfg.risk.max_leverage)
        notional = min(base_risk * entry_px / dist, max_notional_by_leverage)
        if self.max_notional_cfg > 0:
            notional = min(notional, self.max_notional_cfg)
        qty = notional / entry_px
        return max(0.0, float(qty))

    def _mark_to_market(self) -> float:
        """Unrealisierter PnL aller offenen Positionen (naiv: letzter Close der TF)."""
        mtm = 0.0
        for key, pos in self.state["positions"].items():
            # Config rekonstruieren
            d = self._resolve_config(key, self._load_configs_pool())
            if not d: continue
            strat = StrategyConfig(**d)
            df = _load_ohlcv(strat.symbol, Path(self.cfg.paths.processed) / "ohlcv")
            tf = _resample_ohlcv(df, strat.timeframe)
            if tf.empty: continue
            last_px = float(tf["close"].iloc[-1])
            side = int(pos["side"]); qty = float(pos["qty"]); entry = float(pos["entry_px"])
            pnl = (last_px - entry) * qty if side == 1 else (entry - last_px) * qty
            mtm += pnl
        return float(mtm)

    def _check_daily_limit(self) -> bool:
        """True = Limit gerissen und alles schließen + Kill-Switch setzen."""
        start_eq = float(self.state.get("day_start_equity", self.state["equity"]))
        realized = float(self.state.get("realized_today", 0.0))
        unreal = self._mark_to_market()
        drawdown = realized + unreal
        limit = -abs(self.daily_limit_pct) * start_eq
        if drawdown <= limit:
            # Close alles zum letzten Close der jeweiligen TF
            self._close_all_positions(reason="DAILY_LIMIT")
            self._touch_killswitch()
            self._append_log({
                "time": self._now_iso(), "strategy_key":"", "symbol":"", "timeframe":"",
                "event":"killswitch", "side":"", "price":"", "qty":"", "fee":"", "pnl":"", "equity_after": self.state["equity"], "reason":"DAILY_LIMIT"
            })
            self._save_state()
            return True
        return False

    # ---------- portfolio config lookup ----------
    def _resolve_config(self, portfolio_key: str, candidates: List[dict]) -> dict | None:
        for d in candidates:
            if make_key(d) == portfolio_key:
                return d
        base = "|".join(portfolio_key.split("|")[:4])
        for d in candidates:
            b = f"{d['symbol']}|f{int(d['fast'])}|s{int(d['slow'])}|sl{float(d['stop_loss_pct']):.4f}"
            if b == base:
                dd = dict(d); dd["timeframe"] = portfolio_key.split("|")[-1]
                return dd
        return None

    def _load_configs_pool(self) -> List[dict]:
        pool = []
        for p in [
            self.root / "results/portfolios/accepted_intersection.json",
            self.root / "results/backtests/accepted_strategies.json",
            self.root / "results/forward_tests/accepted_strategies.json",
        ]:
            if p.exists():
                try:
                    pool.extend(json.loads(p.read_text(encoding="utf-8")))
                except Exception:
                    pass
        return pool

    # ---------- stop updates & processing ----------
    def update_stops(self):
        self._rollover_day_if_needed()
        pos_keys = list(self.state["positions"].keys())
        for key in pos_keys:
            pos = self.state["positions"][key]
            confs = self._load_configs_pool()
            d = self._resolve_config(key, confs)
            if not d: continue
            strat = StrategyConfig(**d)

            df = _load_ohlcv(strat.symbol, Path(self.cfg.paths.processed) / "ohlcv")
            tf = _resample_ohlcv(df, strat.timeframe)
            last_chk = pd.Timestamp(pos.get("last_checked")) if pos.get("last_checked") else None
            bars = tf if last_chk is None else tf[tf.index > last_chk]

            for t, row in bars.iterrows():
                hi, lo, price = float(row["high"]), float(row["low"]), float(row["close"])
                side = int(pos["side"]); stop = float(pos["stop_px"])
                fee_rate = float(strat.fee_rate); slip = float(strat.slippage)
                hit = False
                if side == 1 and lo <= stop:
                    exit_px = stop * (1 - slip); hit = True
                elif side == -1 and hi >= stop:
                    exit_px = stop * (1 + slip); hit = True

                if hit:
                    qty = float(pos["qty"])
                    fee = abs(exit_px * qty) * fee_rate
                    pnl = (exit_px - float(pos["entry_px"])) * qty if side == 1 else (float(pos["entry_px"]) - exit_px) * qty
                    self.state["equity"] = float(self.state["equity"]) + pnl - fee
                    self.state["realized_today"] = float(self.state["realized_today"]) + pnl - fee
                    self._append_log({
                        "time": t.isoformat(),
                        "strategy_key": key, "symbol": strat.symbol, "timeframe": strat.timeframe,
                        "event":"close_stop","side": side, "price": exit_px, "qty": qty, "fee": fee, "pnl": pnl,
                        "equity_after": self.state["equity"], "reason":"STOP"
                    })
                    del self.state["positions"][key]
                    break
                else:
                    pos["last_checked"] = t.isoformat()

        self._save_state()
        # Nach Stop-Update ggf. Tageslimit prüfen
        self._check_daily_limit()

    def process_signals(self, signals_csv: Path):
        self._rollover_day_if_needed()
        if not signals_csv.exists():
            print(f"[WARN] signals.csv fehlt: {signals_csv}")
            return

        processed = set(self.state.get("processed_signals", []))
        new_rows = []
        with signals_csv.open("r", encoding="utf-8", newline="") as f:
            r = csv.DictReader(f)
            for row in r:
                key = f"{row.get('time','')}|{row.get('strategy_key','')}|{row.get('action','')}"
                if key not in processed:
                    new_rows.append(row)

        if not new_rows:
            print("[OK] Keine unprozessierten Signals.")
            return

        # Tageslimit/Killswitch vor Entries prüfen
        if self.killswitch() or self._check_daily_limit():
            print("[KILL] Killswitch aktiv oder Tageslimit gerissen – keine neuen Entries.")
            processed.update(f"{r['time']}|{r['strategy_key']}|{r['action']}" for r in new_rows)
            self.state["processed_signals"] = list(processed)
            self._save_state()
            return

        confs = self._load_configs_pool()
        for r in new_rows:
            skey = r["strategy_key"]
            d = self._resolve_config(skey, confs)
            if not d: 
                processed.add(f"{r['time']}|{r['strategy_key']}|{r['action']}"); 
                continue
            strat = StrategyConfig(**d)
            side = 1 if r["action"] == "entry_long" else -1
            raw_px = float(r["price"]); stop_px = float(r["stop_px"])
            slip = float(strat.slippage); fee_rate = float(strat.fee_rate)
            fill_px = raw_px * (1 + slip) if side == 1 else raw_px * (1 - slip)

            # Flip?
            if skey in self.state["positions"]:
                cur = self.state["positions"][skey]
                if int(cur["side"]) != side:
                    qty = float(cur["qty"])
                    exit_fee = abs(fill_px * qty) * fee_rate
                    pnl = (fill_px - float(cur["entry_px"])) * qty if int(cur["side"]) == 1 else (float(cur["entry_px"]) - fill_px) * qty
                    self.state["equity"] = float(self.state["equity"]) + pnl - exit_fee
                    self.state["realized_today"] = float(self.state["realized_today"]) + pnl - exit_fee
                    self._append_log({
                        "time": r["time"], "strategy_key": skey, "symbol": strat.symbol, "timeframe": strat.timeframe,
                        "event":"close_flip","side": int(cur["side"]), "price": fill_px, "qty": qty, "fee": exit_fee,
                        "pnl": pnl, "equity_after": self.state["equity"], "reason":"FLIP"
                    })
                    del self.state["positions"][skey]
                else:
                    # gleiches Vorzeichen -> nur Stop ggf. anziehen
                    if (side == 1 and stop_px > float(cur["stop_px"])) or (side == -1 and stop_px < float(cur["stop_px"])):
                        cur["stop_px"] = stop_px
                    processed.add(f"{r['time']}|{r['strategy_key']}|{r['action']}")
                    continue

            # Neue Position eröffnen (mit Portfoliogewicht-Scaling)
            qty = self._calc_qty(strat, fill_px, stop_px, float(self.state["equity"]), skey)
            if qty <= 0:
                processed.add(f"{r['time']}|{r['strategy_key']}|{r['action']}")
                continue

            fee = abs(fill_px * qty) * fee_rate
            self.state["equity"] = float(self.state["equity"]) - fee
            self.state["positions"][skey] = {
                "side": side, "qty": qty, "entry_px": fill_px, "stop_px": stop_px,
                "opened_at": r["time"], "last_checked": r["time"]
            }
            self._append_log({
                "time": r["time"], "strategy_key": skey, "symbol": strat.symbol, "timeframe": strat.timeframe,
                "event":"open","side": side, "price": fill_px, "qty": qty, "fee": fee, "pnl": 0.0,
                "equity_after": self.state["equity"], "reason":"ENTRY"
            })
            processed.add(f"{r['time']}|{r['strategy_key']}|{r['action']}")

        self.state["processed_signals"] = list(processed)
        self._save_state()

    def _close_all_positions(self, reason: str):
        """Schließt alle Positionen zum letzten Close der jeweiligen TF (naiv)."""
        keys = list(self.state["positions"].keys())
        for key in keys:
            pos = self.state["positions"][key]
            d = self._resolve_config(key, self._load_configs_pool())
            if not d: 
                del self.state["positions"][key]; 
                continue
            strat = StrategyConfig(**d)
            df = _load_ohlcv(strat.symbol, Path(self.cfg.paths.processed) / "ohlcv")
            tf = _resample_ohlcv(df, strat.timeframe)
            if tf.empty:
                del self.state["positions"][key]; 
                continue
            last_px = float(tf["close"].iloc[-1])
            side = int(pos["side"]); qty = float(pos["qty"]); entry = float(pos["entry_px"])
            fee_rate = float(strat.fee_rate)
            fee = abs(last_px * qty) * fee_rate
            pnl = (last_px - entry) * qty if side == 1 else (entry - last_px) * qty
            self.state["equity"] = float(self.state["equity"]) + pnl - fee
            self.state["realized_today"] = float(self.state["realized_today"]) + pnl - fee
            self._append_log({
                "time": self._now_iso(), "strategy_key": key, "symbol": strat.symbol, "timeframe": strat.timeframe,
                "event":"close_all","side": side, "price": last_px, "qty": qty, "fee": fee, "pnl": pnl,
                "equity_after": self.state["equity"], "reason": reason
            })
            del self.state["positions"][key]
        self._save_state()
