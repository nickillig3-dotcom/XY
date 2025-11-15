
---

## 3️⃣ `02_RULES_CHECKLISTS_AND_TODO.md`

```md
# 02_RULES_CHECKLISTS_AND_TODO — Rules, Invariants, and Tasks

## 1. Coding & Project Rules

- Language:
  - Code & comments: **English**
  - Chat / discussion: **German** (unless English is needed).
- Style:
  - Follow **PEP8** where reasonable.
  - Use **type hints** for public functions and important internals.
  - Use **docstrings** for:
    - modules,
    - classes,
    - non-trivial functions.
- Structure:
  - `main.py`:
    - orchestration only (no trading/strategy logic).
  - Strategy generation:
    - `strategy_blocks.py` + `strategy_generator.py`.
  - Backtest & forward test:
    - `backtest.py` + `forward_test.py`.
  - Strategy evaluation:
    - `evaluation.py`.
  - Portfolio construction:
    - `portfolio_engine.py`.
  - Risk logic:
    - `risk.py`.
  - Data:
    - `data_loader.py`, `features.py`.
  - Execution:
    - `execution.py`.
  - Storage:
    - `storage.py`.

---

## 2. Trading & Risk Invariants (Strategy & Portfolio Level)

### 2.1 Strategy-Level Invariants

- **Perpetual only** in v1:
  - BTCUSDT, ETHUSDT, SOLUSDT perps (configurable but perp-only).
- **Time resolution:**
  - Base: **1-minute bars** for both backtesting and live decisions.
- **Stop-loss mandatory:**
  - Every `StrategyConfig` must define a valid stop-loss rule.
  - Strategies without valid stop-loss are **invalid and discarded**.
- **Realistic costs:**
  - All backtests and forward tests must include:
    - trading fees,
    - funding payments/receipts,
    - slippage/spread approximation.
- **Risk per trade (default design):**
  - Target: ~**1.0% of equity** at risk per trade (via stop-loss).
  - Allowed band: **0.25–1.5%**.
  - Hard max: **2.0%** of equity at risk per trade.

### 2.2 Portfolio-Level Invariants

- **Global leverage cap (system-level):**
  - Approx. **5x** total exposure vs. equity (configurable).
- **Diversification:**
  - No single strategy should dominate:
    - e.g. max **30–40%** of capital to any single strategy (exact value configurable).
  - No single market should carry all risk:
    - e.g. max **~70%** of capital in any one market (BTC, ETH, or SOL).
- **Correlation awareness:**
  - If two strategies are highly correlated:
    - their combined weight must be constrained or one excluded.
- **Portfolio risk limits:**
  - Target portfolio-level max drawdown: approx. **30%**.
  - Portfolios violating this after evaluation should:
    - be rejected or
    - downscaled (lower weights/leverage).
- **Dynamic adaptation (future extension):**
  - Portfolio may:
    - downweight recent underperformers,
    - temporarily disable strategies that break risk rules.

### 2.3 Search Efficiency & Intelligence (Strategy Search)

- The search process in `strategy_generator.py` should:
  - **avoid wasting compute** on clearly bad parameter regions,
  - use at least a basic **coarse → fine** search:
    - coarse stage for broad exploration,
    - fine stage focused on promising regions.
  - maintain a lightweight **SearchState** structure:
    - stats about which parameter areas produce accepted strategies,
    - stats about consistently poor areas.
  - enforce a **search budget**, e.g.:
    - max strategies per run,
    - and/or max runtime.
- It is **allowed and encouraged** to add:
  - early filters that quickly reject obviously bad candidates before full backtesting,
  - heuristics that bias sampling towards historically promising regions.
- Search logic should remain:
  - **transparent and maintainable**,
  - favour **robustness** over overly complex black-box behaviour.

---

## 3. Assistant / ChatGPT Behaviour Rules

Whenever ChatGPT is used to design or modify this system:

- **Objectivity:**
  - Must be strictly **objective**, not optimistic by default.
  - Must explicitly call out:
    - when results look too good to be true,
    - when overfitting is likely,
    - when sample size is weak or misleading.
- **Profit orientation:**
  - Recommendations should be **profit- and risk-focused**:
    - fewer "nice-to-have" features,
    - more emphasis on robustness and realistic assumptions.
- **No sugarcoating:**
  - Do not label a weak or unstable idea as "good" just to be positive.
  - Prefer clear language:
    - "This looks unstable",
    - "This is likely overfitted",
    - "Risk is too high for the benefit."
- **Transparency:**
  - Always state assumptions and limitations (data quality, unseen risks, etc.).
- **Simplicity preference:**
  - If two approaches have similar performance, prefer the simpler / more interpretable one.

These rules are part of the prompting environment for any future ChatGPT usage in this project.

---

## 4. Process Checklists (Domino)

### 4.1 Configuration & Risk

1. [ ] `03_MARKETS_AND_RISK_PROFILE.md` defines:
   - markets (BTC, ETH, SOL perps),
   - starting capital,
   - risk per trade,
   - drawdown limits,
   - portfolio-related thresholds (max strategies, max concentration, etc.).
2. [ ] `config.yaml` matches these values (markets, paths, risk).

**Output:** `GlobalConfig`, `RiskProfile`, `MarketUniverse`.

---

### 4.2 Data & Features

1. [ ] Raw data exists in `/data/raw` or a download mechanism is in place.
2. [ ] `data_loader.py` correctly loads 1-minute candles (+ funding if used).
3. [ ] `features.py` produces reasonable base feature sets.

**Output:** `DataBundle`, `FeatureBundle`.

---

### 4.3 Strategy Generation & Testing

1. [ ] `strategy_blocks.py` defines:
   - entry & exit blocks,
   - stop-loss variants,
   - position sizing templates.
2. [ ] `strategy_generator.py`:
   - enforces mandatory stop-loss,
   - respects risk & leverage caps,
   - implements coarse → fine search and maintains `SearchState`.
3. [ ] `backtest.py` / `forward_test.py`:
   - simulate trades with fees, funding, slippage.

**Output:** `BacktestRawResult`, `ForwardTestResult` for each strategy.

---

### 4.4 Strategy Evaluation

1. [ ] `evaluation.py` computes:
   - monthly returns & volatility,
   - max drawdown,
   - worst month,
   - Sharpe/Sortino,
   - profit factor,
   - trade count.
2. [ ] Each strategy is:
   - evaluated vs thresholds from `03_MARKETS_AND_RISK_PROFILE.md`,
   - flagged accepted/rejected.

**Output:** `BacktestResult` objects (with `is_accepted` flag).

---

### 4.5 Portfolio Construction

1. [ ] `portfolio_engine.py` reads all accepted `BacktestResult` objects.
2. [ ] Respects portfolio-level constraints:
   - total leverage,
   - concentration per strategy,
   - concentration per market,
   - correlation constraints.
3. [ ] Builds at least one valid `PortfolioConfig` and computes `PortfolioResult`.

**Output:** Portfolio configs and metrics under `/results/portfolios`.
- Forward testing uses an OOS share of **~60%** of the available window for acceptance checks.
- Portfolio is built from **Backtest ∩ Forward** accepted strategies.
- Paper trading aggregates **weighted returns** on the union of bar timestamps to avoid alignment artefacts; logs per-trade events to `trades.csv` and writes summaries.

---

### 4.6 Paper & Live Trading

1. [ ] `execution.py` can:
   - run a selected `PortfolioConfig` in **paper** mode,
   - log trades and portfolio equity to `/results/paper_trading`.
2. [ ] Live mode (later) uses:
   - real API keys (safely),
   - the same `RiskProfile` and portfolio constraints.

**Output:** `ExecutionLog` and real-time state (positions, PnL).

---

## 5. TODO List (Initial)

> To be updated continuously.

- [ ] Choose Python version and create `requirements.txt` (pandas, numpy, etc.).
- [ ] Implement `config_loader.py`.
- [ ] Implement basic `data_loader.py` for 1-minute perp data.
- [ ] Implement minimal `features.py` with core features.
- [ ] Implement `strategy_blocks.py` (core building blocks).
- [ ] Implement `strategy_generator.py` with:
  - coarse → fine search,
  - `SearchState`,
  - early filters.
- [ ] Implement core `backtest.py` for 1-minute bars.
- [ ] Implement `forward_test.py` (walk-forward splits).
- [ ] Implement `evaluation.py` with monthly metrics & thresholds.
- [ ] Implement initial `portfolio_engine.py`:
  - simple ranking + diversification + weights.
- [ ] Implement minimal `execution.py` in paper mode.
- [ ] Wire everything via `main.py`.

---

## 6. Domino Summary (File-Level)

- **Input:** architecture & goals from `01_ARCHITECTURE_AND_MODULES.md` and `00_PROJECT_OVERVIEW.md`.  
- **Output:** rules, invariants, and checklists, including:
  - strategy & portfolio risk rules,
  - search intelligence requirements,
  - AI behaviour rules.


→ Used by all implementations and by any ChatGPT prompt relating to this project.
- Correlation cap (portfolio): default **0.60** (configurable).
- Market cap (per market): default **0.60** (configurable); Strategy cap: **0.40**.
