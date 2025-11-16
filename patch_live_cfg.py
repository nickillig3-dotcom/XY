import json, pathlib, sys
try:
    import yaml  # PyYAML wird in deinem Projekt schon genutzt
except Exception as e:
    print("PyYAML fehlt:", e); sys.exit(1)

cfg_p = pathlib.Path("config/config.yaml")
data = yaml.safe_load(cfg_p.read_text(encoding="utf-8")) or {}
live = data.setdefault("live", {})

# 👇 Werte nach Bedarf anpassen
live.setdefault("killswitch_path", "results/live/KILL")
live.setdefault("max_notional", 2000)            # z.B. 2.000 USDT Cap (0 = aus)
live.setdefault("daily_loss_limit_pct", 0.03)    # 3% Tages-Loss-Limit
live.setdefault("use_portfolio_weights", True)   # Positionsgröße nach Portfoliogewicht skalieren

cfg_p.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")

# zur Kontrolle via load_extras
from src.config_extras import load_extras
print(json.dumps(load_extras("config/config.yaml").get("live", {}), indent=2))
