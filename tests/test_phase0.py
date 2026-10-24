"""Phase 0: wrong hosts refuse to start, and no order function runs."""

from __future__ import annotations

from pathlib import Path

import pytest

from paperbot.config import SANDBOX_HOST, Settings, StartupRefused, load_risk, load_settings, require_sandbox_host
from paperbot.gateway import OrderIntent, OrdersRefused, ReplayGateway, SandboxGateway
from paperbot.main import main

REPO = Path(__file__).resolve().parents[1]
PACKAGE = REPO / "paperbot"

STARTER_LIMITS = {
    "loss_per_trade_percent": 0.5,
    "equity_notional_percent": 2,
    "long_option_premium_percent": 0.5,
    "daily_loss_percent": 2,
    "max_open_positions": 5,
    "max_new_orders_per_session": 10,
    "option_contracts_per_order": 1,
    "option_contracts_ceiling": 5,
    "ticker_pause_minutes": 30,
    "decision_ttl_minutes": 15,
    "equity_limit_from_mid_percent": 1,
    "option_limit_from_mid_percent": 5,
    "max_grok_calls_per_session": 30,
}

ORDER_WORDS = (
    "place_order",
    "preview_order",
    "place_option",
    "preview_option",
    "cancel_order",
    "replace_order",
    "XAI_API_KEY",
    "api.x.ai",
)


class _Response:
    def __init__(self, status_code: int, payload: object) -> None:
        self.status_code = status_code
        self._payload = payload
        self.text = str(payload)

    def json(self) -> object:
        if isinstance(self._payload, Exception):
            raise self._payload
        return self._payload


class _Accounts:
    def __init__(self, response: _Response) -> None:
        self.response = response
        self.calls = 0

    def get_account_list(self) -> _Response:
        self.calls += 1
        return self.response


class _Trade:
    """Any attribute other than account_v2 means phase 0 touched an order API."""

    def __init__(self, response: _Response) -> None:
        self.account_v2 = _Accounts(response)

    def __getattr__(self, name: str) -> object:
        raise AssertionError(f"phase 0 touched {name}")


def _paper_env(monkeypatch: pytest.MonkeyPatch, token_dir: Path, host: str | None = None) -> None:
    monkeypatch.setenv("WEBULL_APP_KEY", "test-key")
    monkeypatch.setenv("WEBULL_APP_SECRET", "test-secret")
    monkeypatch.setenv("WEBULL_OPENAPI_TOKEN_DIR", str(token_dir))
    if host is None:
        monkeypatch.delenv("WEBULL_HOST", raising=False)
    else:
        monkeypatch.setenv("WEBULL_HOST", host)


def test_starter_limits_match_the_plan() -> None:
    assert load_risk(REPO / "config" / "risk.yaml") == STARTER_LIMITS


@pytest.mark.parametrize(
    "host",
    [
        "api.webull.com",
        "https://api.webull.com",
        "http://api.webull.com",
        "API.WEBULL.COM",
        "https://api.webull.com/",
        "events-api.sandbox.webull.com",
        "data-api.sandbox.webull.com",
        "api.sandbox.webull.com.example",
        "https://api.sandbox.webull.com/trading",
        "",
        "localhost",
    ],
)
def test_wrong_host_refuses_before_any_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, host: str, capsys: pytest.CaptureFixture[str]
) -> None:
    _paper_env(monkeypatch, tmp_path, host)
    called = False

    def factory(_settings: object) -> object:
        nonlocal called
        called = True
        raise AssertionError("gateway was built")

    assert main(gateway_factory=factory) == 2
    assert called is False
    captured = capsys.readouterr()
    assert captured.out == ""
    assert "refusing to start" in captured.err
    assert SANDBOX_HOST in captured.err


@pytest.mark.parametrize(
    "host",
    [
        "api.sandbox.webull.com",
        "https://api.sandbox.webull.com",
        "https://api.sandbox.webull.com/",
        "API.SANDBOX.WEBULL.COM",
    ],
)
def test_sandbox_host_is_accepted(host: str) -> None:
    assert require_sandbox_host(host) == SANDBOX_HOST


def test_default_config_is_paper_sandbox(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    _paper_env(monkeypatch, tmp_path)
    settings = load_settings()
    assert settings.mode == "paper"
    assert settings.region == "us"
    assert settings.host == SANDBOX_HOST
    assert settings.token_dir == tmp_path.resolve()


def test_phase0_lists_accounts_and_does_not_call_order_functions(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    _paper_env(monkeypatch, tmp_path)
    trade = _Trade(_Response(200, [{"account_id": "SANDBOX1", "account_type": "CASH"}]))
    settings = load_settings()
    gateway = SandboxGateway(settings, trade_client=trade)

    assert main(gateway_factory=lambda _settings: gateway) == 0
    assert trade.account_v2.calls == 1
    captured = capsys.readouterr()
    assert "sandbox accounts from api.sandbox.webull.com" in captured.out
    assert "SANDBOX1" in captured.out
    assert "test-secret" not in captured.out
    assert "test-key" not in captured.out


def test_sandbox_gateway_refuses_order_intent_without_touching_the_client(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _paper_env(monkeypatch, tmp_path)
    trade = _Trade(_Response(200, []))
    gateway = SandboxGateway(load_settings(), trade_client=trade)
    intent = OrderIntent(symbol="AAPL", side="BUY", quantity=1, limit_price="1.00")
    with pytest.raises(OrdersRefused):
        gateway.record_order_intent(intent)
    assert trade.account_v2.calls == 0


def test_sandbox_gateway_refuses_a_non_sandbox_host(tmp_path: Path) -> None:
    settings = Settings(
        mode="paper",
        region="us",
        host="api.webull.com",
        app_key="test-key",
        app_secret="test-secret",
        token_dir=tmp_path,
        risk_path=REPO / "config" / "risk.yaml",
    )
    with pytest.raises(StartupRefused):
        SandboxGateway(settings)


def test_failed_account_list_still_does_not_touch_orders(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    _paper_env(monkeypatch, tmp_path)
    trade = _Trade(_Response(500, {"error": "down"}))
    gateway = SandboxGateway(load_settings(), trade_client=trade)
    assert main(gateway_factory=lambda _settings: gateway) == 1
    assert trade.account_v2.calls == 1


def test_replay_gateway_records_an_intent_without_network() -> None:
    gateway = ReplayGateway(accounts=[{"account_id": "REPLAY1"}])
    intent = OrderIntent(symbol="SPY", side="BUY", quantity=1, limit_price="500.00")
    gateway.record_order_intent(intent)
    assert gateway.list_accounts() == [{"account_id": "REPLAY1"}]
    assert gateway.intents == [intent]


def test_missing_token_dir_refuses(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("WEBULL_APP_KEY", "test-key")
    monkeypatch.setenv("WEBULL_APP_SECRET", "test-secret")
    monkeypatch.delenv("WEBULL_OPENAPI_TOKEN_DIR", raising=False)
    monkeypatch.delenv("WEBULL_HOST", raising=False)
    with pytest.raises(StartupRefused, match="WEBULL_OPENAPI_TOKEN_DIR"):
        load_settings()


def test_token_dir_inside_repo_refuses(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    inside = REPO / "config"
    _paper_env(monkeypatch, inside)
    with pytest.raises(StartupRefused, match="outside the repository"):
        load_settings()
    assert not (tmp_path / "unused").exists()


def test_package_source_has_no_order_or_grok_calls() -> None:
    for path in PACKAGE.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        for word in ORDER_WORDS:
            assert word not in text, f"{path.name} contains {word}"
