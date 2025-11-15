# 00_PROJECT_OVERVIEW — Local Perp Futures Hedge Fund Engine (Windows)

## 1. Core Goal

- Build a **local, lightweight hedge-fund-style engine** running on a normal **Windows PC**.
- Focus: **perpetual futures only** on 3 core markets:
  - BTCUSDT Perpetual
  - ETHUSDT Perpetual
  - SOLUSDT Perpetual
- The system has **one main ON/OFF switch**:
  - ON  = run the full pipeline:
    - config → data → feature generation → strategy generation → backtesting → forward-testing → portfolio construction → paper/live trading.
  - OFF = stop all trading-related processes (no hidden background workers).
- The system should **automatically design trading strategies** based on available data:
  - **no manual, hand-written strategies** as the primary method.
  - Strategies are built from building blocks and searched/optimized by the engine.
- Every strategy must:
  - include a **stop-loss**,
  - be evaluated with **realistic trading conditions** (fees, funding, slippage),
  - be tested on at least one **1-minute timeframe** (core resolution).

---

## 2. Scope and Non-Scope (v1)

### 2.1 In Scope (v1)

- Instruments:
  - **Perpetual futures only**, on a small universe (BTC, ETH, SOL).
- Modes:
  - **Backtesting** (historical).
  - **Forward-testing / walk-forward** (out-of-sample simulation).
  - **Portfolio construction from strategy candidates** (strategy portfolio / ensemble).
  - **Paper trading** (signals + pseudo orders, no real exchange money).
  - Basic **live trading** capability (optional, can be enabled later).
- Strategy behaviour:
  - Strategies are **generated automatically** from configurable building blocks.
  - Both **long and short** positions allowed.
  - Position size, trade frequency, leverage use = decided by the system within risk limits.
- Portfolio behaviour:
  - The engine builds **portfolios of strategies**:
    - chooses which strategies to include,
    - assigns capital weights,
    - considers risk, drawdown, diversification, and correlation.
  - Focus on **stable, diversified profit**, not just one lucky single strategy.
- Operation:
  - Designed to run **24/7**, as long as the PC and internet are up.
  - Data resolution: **1-minute candles** as the core input; features may use higher aggregations (e.g. 5m, 15m).

### 2.2 Out of Scope (v1)

- Fancy dashboards, frontends, visual UIs.
- Complex governance, approvals, user roles, etc.
- Support for other asset classes (spot, options, stocks, FX, etc.).
- Exchange-specific edge cases beyond what is needed for basic perp trading.

---

## 3. Trading Objectives

> These are **targets**, not guarantees.

- **Primary objective (portfolio-level design target):**
  - Aim for **~3% net monthly return** at portfolio level with:
    - **hard max drawdown** around **-25% to -30%** from peak.
- **Stretch objective:**
  - Up to **5% monthly** if it can be achieved without excessive risk.
- **Secondary objectives:**
  - Control **max monthly loss** (e.g. avoid worse than ~-8% per month).
  - Keep risk per trade in a sane band (see risk profile file).
  - Avoid overfitted strategies with only a tiny number of trades.

Portfolio-level optimization:

- Combine multiple strategies to:
  - smooth the equity curve,
  - reduce drawdown via diversification across:
    - markets (BTC/ETH/SOL),
    - timeframes,
    - logic types (trend / mean-reversion / other),
  - cut or downweight strategies that stop working.

---

## 4. Strategy & Portfolio Intelligence (High-Level)

### 4.1 Strategy Generation

- No fixed manual strategies like "MA 50/200 crossover hard-coded".
- Use:
  - A library of **building blocks**:
    - entry conditions,
    - exit conditions,
    - stop-loss types,
    - position sizing rules,
    - timeframes.
  - A **search procedure** to:
    - choose which features are used,
    - define entry/exit rules,
    - set stop-loss / take-profit parameters,
    - define risk per trade and leverage.
- Each candidate strategy goes through:
  1. **Generation** → `StrategyConfig`.
  2. **Validation** → respect base risk rules (stop-loss, leverage limits).
  3. **Backtest** on historical 1-minute-based data.
  4. **Forward test / walk-forward** on unseen data segments.
  5. **Evaluation** → metrics + constraints.
  6. **Storage** → configs + results for portfolio step.

### 4.2 Strategy Portfolio Construction

- From the pool of **accepted strategies** (passed backtest + forward-test filters):
  - Build **one or more portfolios** of strategies.
- Portfolio engine may:
  - rank strategies by metrics (return, drawdown, Sharpe, stability),
  - measure correlations between strategy equity curves,
  - apply allocation rules (e.g. risk parity, volatility scaling, capped weights).
- Objectives:
  - Choose a **subset of strategies** that together:
    - respect global risk limits,
    - reduce concentration risk (not all capital on one symbol / style),
    - maximize portfolio-level metrics (monthly return, drawdown, etc.).
- The resulting `PortfolioConfig` will be used in:
  - paper trading,
  - and later live trading.
**Implementation note (current defaults):**
- All simulations include **fees, slippage and funding** costs.
- **Portfolio selection uses the intersection of Backtest-accepted AND Forward-accepted strategies** (Backtest ∩ Forward).
- The current correlation cap is **0.60** at the portfolio step; max weight per strategy **0.40**; per market **0.60**.

### 4.3 Search Intelligence (Strategy Search Layer)

- The strategy generation process should **not** blindly search the full parameter space.
- Instead, it should:
  - use a **multi-stage search** (coarse → fine):
    - coarse, cheap scans over a wide parameter space,
    - followed by more detailed search in promising regions only.
  - maintain a simple **SearchState / history** tracking:
    - which feature sets/timeframes/stop-loss types tend to work,
    - which parameter regions are consistently bad.
  - adapt over time:
    - sample more frequently from historically promising regions,
    - avoid repeatedly exploring clearly unprofitable areas.
- Goal:
  - Use limited compute **efficiently**,
  - steer the search toward areas with higher probability of profitable, robust strategies.

---

## 5. Pipeline Phases (End-to-End)

1. **Configuration & Markets**
   - Define exchange(s), markets, capital, risk limits.
   - → `03_MARKETS_AND_RISK_PROFILE.md`.

2. **Data & Features**
   - Load historical and live data.
   - Build feature sets from 1-minute data.

3. **Strategy Generation / Search**
   - Use intelligent search to generate and refine candidate strategies.

4. **Backtesting**
   - Simulate strategies historically with realistic costs.

5. **Forward-Testing (Walk-Forward)**
   - Test on unseen data segments.

6. **Strategy Evaluation & Filtering**
   - Filter out bad / unstable strategies via metrics and constraints.

7. **Portfolio Construction (Strategy-Level)**
   - Build portfolios from the remaining strategy candidates.
   - Produce `PortfolioConfig` + portfolio metrics.

8. **Paper Trading**
   - Run portfolios on live data without real money.

9. **Live Trading**
   - Use chosen portfolios and risk limits to trade real perp futures.

10. **Monitoring & Updating**
    - Monitor performance,
    - periodically re-run search/backtests/portfolio construction,
    - disable or replace underperforming strategies/portfolios.

---

## 6. Assistant / ChatGPT Behaviour (Meta-Rules)

When an AI assistant (ChatGPT) is used for this project, it should:

- be **objective and profit-oriented**,
- **never sugarcoat** results:
  - clearly point out when something looks overfitted, unstable, or unrealistic,
- show **risks and limitations** explicitly,
- prefer **simple, robust, explainable logic** if two options have similar profit,
- avoid "marketing language" – focus on data, metrics, and logic.

---

## 7. Input & Output of This File (Domino View)

- **Input to this file:**
  - Vision: "Local, slim, profit-focused perp futures hedge fund with auto strategy + portfolio intelligence + efficient search."
- **Output of this file:**
  - Clear:
    - goals,
    - scope,
    - modes,
    - performance targets,
    - pipeline (including portfolio and search intelligence),
    - assistant behaviour rules.

→ This output feeds directly into:  
`01_ARCHITECTURE_AND_MODULES.md` and `03_MARKETS_AND_RISK_PROFILE.md`.
