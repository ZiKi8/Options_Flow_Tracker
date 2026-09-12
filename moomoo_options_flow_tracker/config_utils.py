import json
from pathlib import Path

CONFIG_PATH = Path("config.json")

def load_config():
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))

def save_config(cfg):
    CONFIG_PATH.write_text(json.dumps(cfg, indent=2), encoding="utf-8")

def normalize_ticker(t):
    return t.strip().upper().replace("US.", "")

def add_ticker(ticker):
    cfg = load_config()
    t = normalize_ticker(ticker)
    if t and t not in cfg["tickers"]:
        cfg["tickers"].append(t)
        cfg["tickers"] = sorted(set(cfg["tickers"]))
        save_config(cfg)
    return cfg

def remove_ticker(ticker):
    cfg = load_config()
    t = normalize_ticker(ticker)
    cfg["tickers"] = [x for x in cfg["tickers"] if x != t]
    save_config(cfg)
    return cfg
