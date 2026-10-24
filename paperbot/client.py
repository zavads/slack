"""Build a Webull client that can only reach the sandbox host."""

from __future__ import annotations

import logging
import sys

from paperbot.config import SANDBOX_HOST, Settings, StartupRefused, require_sandbox_host


def build_trade_client(settings: Settings):
    """Connect to the sandbox. Order methods are never called from this package."""
    require_sandbox_host(settings.host)
    if settings.mode != "paper" or settings.region != "us":
        raise StartupRefused("phase 0 only starts in paper mode for region us.")

    from webull.core.client import ApiClient
    from webull.trade.trade_client import TradeClient

    api_client = ApiClient(settings.app_key, settings.app_secret, settings.region)
    api_client.add_endpoint(settings.region, SANDBOX_HOST)
    api_client.set_token_dir(str(settings.token_dir))
    # A stream handler stops TradeClient from also creating webull_trade_sdk.log here.
    api_client.set_stream_logger(stream=sys.stderr, log_level=logging.WARNING)
    return TradeClient(api_client)
