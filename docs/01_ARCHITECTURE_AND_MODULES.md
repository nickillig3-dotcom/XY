# 01_ARCHITECTURE_AND_MODULES — Technical Design (Domino Style)

## 1. Directory Layout (Planned, Windows-Friendly)

```text
/project_root
  main.py                       # Single entry point (ON/OFF)
  /config
    config.yaml                 # Global configuration (paths, modes, engine settings)
  /docs
    00_PROJECT_OVERVIEW.md
    01_ARCHITECTURE_AND_MODULES.md
    02_RULES_CHECKLISTS_AND_TODO.md
    03_MARKETS_AND_RISK_PROFILE.md
  /src
    __init__.py
    config_loader.py            # Load and validate config + risk & market profile
    data_loader.py              # Load & preprocess perp futures data (historical + live)
    features.py                 # Build features from raw data
    strategy_blocks.py          # Building blocks for strategy rules & logic
    strategy_generator.py       # Automatic strategy generation & intelligent search
    backtest.py                 # Backtesting engine (historical)
    forward_test.py             # Walk-forward / out-of-sample testing
    evaluation.py               # Metrics & strategy-level selection logic
    portfolio_engine.py         # Portfolio construction from strategy candidates
    risk.py                     # Risk rules, stop-loss, position sizing, leverage caps
    execution.py                # Paper & live trading layer (portfolio-based order handling)
    storage.py                  # Save/load strategies, portfolios, results, logs, SearchState
    logging_utils.py            # Central logging helpers
  /data
    /raw                        # Raw exchange data (downloaded)
    /processed                  # Cleaned/normalized data
  /results
    /backtests        # metrics.csv, accepted_strategies.json
    /forward_tests    # metrics.csv, accepted_strategies.json
    /portfolios       # selection.json (weights), accepted_intersection.json, portfolio_equity.parquet
    /paper_trading    # paper_equity.parquet, trades.csv, trade_summary.csv, trades_by_bucket.csv
    /live_trading               # Live trading logs & reports
    /logs                       # General logs
