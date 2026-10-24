"""Load phase-0 settings. The only accepted host is the Webull sandbox."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

import yaml

SANDBOX_HOST = "api.sandbox.webull.com"
PAPER_MODE = "paper"
US_REGION = "us"

_RISK_FIELDS: dict[str, tuple[type, ...]] = {
    "loss_per_trade_percent": (int, float),
    "equity_notional_percent": (int, float),
    "long_option_premium_percent": (int, float),
    "daily_loss_percent": (int, float),
    "max_open_positions": (int,),
    "max_new_orders_per_session": (int,),
    "option_contracts_per_order": (int,),
    "option_contracts_ceiling": (int,),
    "ticker_pause_minutes": (int,),
    "decision_ttl_minutes": (int,),
    "equity_limit_from_mid_percent": (int, float),
    "option_limit_from_mid_percent": (int, float),
    "max_grok_calls_per_session": (int,),
}


class StartupRefused(Exception):
    """Configuration is not safe to start. The process must exit."""


@dataclass(frozen=True)
class Settings:
    mode: str
    region: str
    host: str
    app_key: str
    app_secret: str
    token_dir: Path
    risk_path: Path


def repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def normalize_host(host: str) -> str:
    value = host.strip().lower()
    if "://" in value:
        scheme, _, rest = value.partition("://")
        if scheme not in {"http", "https"} or not rest:
            return value
        value = rest
    if value.endswith("/"):
        value = value[:-1]
    return value


def require_sandbox_host(host: str) -> str:
    """Return the sandbox host, or refuse. No other host is accepted."""
    normalized = normalize_host(host)
    if normalized != SANDBOX_HOST:
        raise StartupRefused(
            f"configured host {host!r} is not {SANDBOX_HOST}. "
            "This process only talks to the Webull sandbox. "
            "api.webull.com and every other host are refused. "
            "Live trading is not in this version."
        )
    return SANDBOX_HOST


def load_settings(environ: Mapping[str, str] | None = None) -> Settings:
    env = os.environ if environ is None else environ
    root = repo_root()
    app_config = _read_yaml(root / "config" / "app.yaml")
    mode = str(app_config.get("mode", "")).strip().lower()
    if mode != PAPER_MODE:
        raise StartupRefused(
            f"configured mode {mode!r} is not {PAPER_MODE}. "
            "Live trading is not in this version."
        )
    region = str(app_config.get("region", "")).strip().lower()
    if region != US_REGION:
        raise StartupRefused(f"phase 0 only supports region {US_REGION!r}.")

    configured_host = env["WEBULL_HOST"] if "WEBULL_HOST" in env else str(app_config.get("host", ""))
    host = require_sandbox_host(configured_host)

    app_key = _required_env(env, "WEBULL_APP_KEY")
    app_secret = _required_env(env, "WEBULL_APP_SECRET")
    token_dir = _token_dir(env.get("WEBULL_OPENAPI_TOKEN_DIR"), root)
    return Settings(
        mode=PAPER_MODE,
        region=region,
        host=host,
        app_key=app_key,
        app_secret=app_secret,
        token_dir=token_dir,
        risk_path=root / "config" / "risk.yaml",
    )


def load_risk(path: Path) -> dict[str, int | float]:
    """Read starter limits. Phase 0 does not apply them to an order."""
    data = _read_yaml(path)
    if not isinstance(data, dict):
        raise StartupRefused(f"{path} must be a mapping")
    limits: dict[str, int | float] = {}
    for name, types in _RISK_FIELDS.items():
        if name not in data:
            raise StartupRefused(f"{path} is missing {name}")
        value = data[name]
        if isinstance(value, bool) or not isinstance(value, types):
            raise StartupRefused(f"{path} field {name} has the wrong type")
        if value < 0:
            raise StartupRefused(f"{path} field {name} must be >= 0")
        limits[name] = value
    if limits["option_contracts_per_order"] > limits["option_contracts_ceiling"]:
        raise StartupRefused("option_contracts_per_order exceeds option_contracts_ceiling")
    return limits


def _read_yaml(path: Path) -> object:
    if not path.is_file():
        raise StartupRefused(f"missing config file: {path}")
    with path.open(encoding="utf-8") as handle:
        loaded = yaml.safe_load(handle)
    if loaded is None:
        raise StartupRefused(f"{path} is empty")
    return loaded


def _required_env(env: Mapping[str, str], name: str) -> str:
    value = env.get(name, "")
    if not value.strip():
        raise StartupRefused(f"{name} is required")
    return value


def _token_dir(raw: str | None, root: Path) -> Path:
    if raw is None or not raw.strip():
        raise StartupRefused(
            "WEBULL_OPENAPI_TOKEN_DIR is required and must point outside this repository. "
            "Without it the Webull SDK writes conf/token.txt in the working directory."
        )
    path = Path(raw).expanduser()
    path = path.resolve() if path.is_absolute() else (Path.cwd() / path).resolve()
    if path == root.resolve() or _is_relative_to(path, root.resolve()):
        raise StartupRefused(
            "WEBULL_OPENAPI_TOKEN_DIR must be outside the repository so tokens are not written into git."
        )
    return path


def _is_relative_to(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True
