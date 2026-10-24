"""Broker surface for phase 0.

SandboxGateway lists sandbox accounts. ReplayGateway stores an order intent
locally. Neither submits an order.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from paperbot.client import build_trade_client
from paperbot.config import Settings, StartupRefused, require_sandbox_host


class AccountListError(Exception):
    """The account list could not be read. No order was sent."""


class OrdersRefused(Exception):
    """This gateway does not submit orders."""


@dataclass(frozen=True)
class OrderIntent:
    """A local note that an order was considered. It is not an order."""

    symbol: str
    side: str
    quantity: int
    limit_price: str


class Broker(Protocol):
    def list_accounts(self) -> list[dict[str, Any]]: ...

    def record_order_intent(self, intent: OrderIntent) -> None: ...


class SandboxGateway:
    """List accounts on the Webull sandbox. Phase 0 never sends an order."""

    def __init__(self, settings: Settings, trade_client: Any | None = None) -> None:
        require_sandbox_host(settings.host)
        if settings.mode != "paper":
            raise StartupRefused("SandboxGateway only starts in paper mode.")
        self._settings = settings
        self._trade_client = trade_client

    def list_accounts(self) -> list[dict[str, Any]]:
        client = self._trade_client
        if client is None:
            client = build_trade_client(self._settings)
        try:
            response = client.account_v2.get_account_list()
        except AccountListError:
            raise
        except Exception as exc:
            raise AccountListError(f"sandbox account list failed: {exc}") from exc
        return _accounts_from_response(response)

    def record_order_intent(self, intent: OrderIntent) -> None:
        del intent
        raise OrdersRefused("SandboxGateway only lists accounts and does not accept order intents.")


class ReplayGateway:
    """Record order intents in memory. This object never uses the network."""

    def __init__(self, accounts: list[dict[str, Any]] | None = None) -> None:
        self._accounts = [dict(account) for account in (accounts or [])]
        self.intents: list[OrderIntent] = []

    def list_accounts(self) -> list[dict[str, Any]]:
        return [dict(account) for account in self._accounts]

    def record_order_intent(self, intent: OrderIntent) -> None:
        if not isinstance(intent, OrderIntent):
            raise TypeError("intent must be an OrderIntent")
        if intent.quantity <= 0:
            raise ValueError("quantity must be positive")
        if not intent.symbol.strip() or not intent.side.strip() or not intent.limit_price.strip():
            raise ValueError("symbol, side, and limit_price are required")
        self.intents.append(intent)


def _accounts_from_response(response: Any) -> list[dict[str, Any]]:
    status = getattr(response, "status_code", None)
    if status != 200:
        body = getattr(response, "text", "")
        raise AccountListError(f"sandbox account list returned status {status}: {body}")
    try:
        payload = response.json()
    except Exception as exc:
        raise AccountListError(f"sandbox account list was not JSON: {exc}") from exc
    if not isinstance(payload, list):
        raise AccountListError("sandbox account list was not a list")
    return payload
