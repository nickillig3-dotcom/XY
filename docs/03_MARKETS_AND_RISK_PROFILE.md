# 03_MARKETS_AND_RISK_PROFILE — Perpetual Futures Setup (BTC, ETH, SOL)

## 1. Exchanges and Markets

### 1.1 Exchanges (Initial)

- Primary exchange (placeholder): **"Binance Futures"**
  - Used as reference for typical fee structures and perp contracts.
- Secondary exchanges:
  - none in v1 (can be added later).

### 1.2 Perpetual Markets Universe (v1)

Core markets (all quoted in USDT or similar stablecoin):

- `BTCUSDT` Perpetual
- `ETHUSDT` Perpetual
- `SOLUSDT` Perpetual

For each symbol (to be filled from actual exchange docs):

- Tick size: TODO
- Contract size: TODO
- Minimum order size: TODO
- Taker/maker fee rate: TODO
- Funding rate model/source: TODO

These values will be used by:
- `data_loader.py` (for loading),
- `backtest.py` (for simulation),
- `execution.py` (for live trading).

---

## 2. Account and Margin Setup (Design Defaults)

- Collateral currency:
  - **USDT** (or equivalent stablecoin).
- Margin mode:
  - **Cross margin** (initial assumption).
- Starting capital in backtests (design default):
  - **10,000 USDT**.
- Max account leverage (system-level cap):
  - **5x** total exposure vs. equity.
- Typical per-strategy leverage:
  - **1–3x** (enforced via `risk.py` and strategy configs).
- Risk per trade:
  - Base target: **1.0%** of equity.
  - Allowed band: **0.25–1.5%**.
  - Hard cap: **2.0%** of equity at risk per trade.

These settings feed into the `RiskProfile` object.

---

## 3. Risk & Return Objectives (Numbers)

### 3.1 Monthly Targets (Portfolio Level)

- Target average **net monthly return** (portfolio level):
  - ~**3%** per month (design goal).
- Stretch target:
  - up to **5%** per month if risk remains acceptable.
- Acceptable worst month:
  - around **-8%** (beyond this = warning).
- Hard max drawdown (peak-to-trough, portfolio level):
  - around **-30%** (beyond this = unacceptable).

### 3.2 Strategy Acceptance Thresholds

A single strategy is considered "acceptable" if (configurable, used by `evaluation.py`):

- Average monthly return ≥ **2%**.
- Max drawdown ≤ **30%**.
- Worst month ≥ **-10%**.
- Trade count ≥ **50–100 trades** in the test period (exact threshold to be chosen).
- No obvious overfitting signs:
  - equity curve not dominated by a single massive outlier trade,
  - performance not completely concentrated in a tiny time window.

### 3.3 Portfolio-Level Constraints

Portfolio construction (in `portfolio_engine.py`) must respect:

- Max total leverage:
  - **≤ 5x** vs. equity (configurable).
- Max capital weight per single strategy:
  - e.g. **≤ 40%** of capital (configurable).
- Max capital weight per single market (BTC or ETH or SOL):
  - e.g. **≤ 70%** of capital (configurable).
- Target number of strategies in active portfolio:
  - e.g. **3–10 strategies**, depending on search results.
- Correlation constraints:
  - If two strategies are very highly correlated:
    - their combined weight should be limited or one excluded.

These constraints aim at **robust, diversified portfolios**, not single-strategy bets.

---

## 4. Frequency and Timeframes

- Data resolution:
  - Core data: **1-minute candles**.
- Strategy timeframes:
  - Strategies may operate on:
    - 1m bars directly,
    - or aggregated bars (e.g. 5m, 15m) built from 1m.
- Trading hours:
  - Crypto perps trade **24/7**.
  - The engine is allowed to trade at all times initially.
  - Future rule: restrict trading in illiquid periods if needed.

---

## 5. Forward-Testing, Paper & Live Usage

- **Forward-testing (walk-forward):**
  - Use out-of-sample time segments per market.
  - Strategies must pass:
    - both backtest and forward-test thresholds.
- **Paper trading:**
  - Use selected `PortfolioConfig` objects.
  - Must honour `RiskProfile` and portfolio constraints.
  - Run continuously to validate behaviour on live data without real capital.
- **Live trading:**
  - Same as paper but with real orders.
  - Requires stable performance in:
    - backtest,
    - forward-test,
    - and paper trading.

---

## 6. Search Budget (Compute Awareness)

Because the system runs on a normal Windows PC:

- There should be a **maximum search budget** per run, for example:
  - max number of strategies evaluated (e.g. N strategies per batch),
  - and/or max runtime for search.
- The intelligent search in `strategy_generator.py` is expected to:
  - use this budget efficiently,
  - shift search effort towards more promising regions of the parameter space,
  - avoid repeatedly exploring clearly unprofitable areas.

These limits should be configurable via `GlobalConfig`.

---

## 7. Domino Summary (File-Level)

- **Input:**
  - Goals & structure from `00_PROJECT_OVERVIEW.md`.
- **Output:**
  - Concrete numeric settings and constraints:
    - markets,
    - capital,
    - risk per trade,
    - strategy thresholds,
    - portfolio constraints,
    - search budget hints.

→ Used directly by:
- `config_loader.py` (to build `RiskProfile` and `MarketUniverse`),
- `risk.py` (risk enforcement),
- `evaluation.py` (strategy filtering),
- `portfolio_engine.py` (portfolio construction),
- and indirectly by `execution.py`.
