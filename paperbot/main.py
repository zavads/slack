"""Phase 0 entrypoint: print the sandbox account list and exit."""

from __future__ import annotations

import json
import sys
from collections.abc import Callable

from paperbot.config import Settings, StartupRefused, load_risk, load_settings
from paperbot.gateway import AccountListError, Broker, SandboxGateway


def main(
    argv: list[str] | None = None,
    gateway_factory: Callable[[Settings], Broker] | None = None,
) -> int:
    del argv  # phase 0 takes no command-line arguments
    try:
        settings = load_settings()
        load_risk(settings.risk_path)
        gateway = (gateway_factory or SandboxGateway)(settings)
        accounts = gateway.list_accounts()
    except StartupRefused as exc:
        print(f"refusing to start: {exc}", file=sys.stderr)
        return 2
    except AccountListError as exc:
        print(str(exc), file=sys.stderr)
        return 1

    print(f"sandbox accounts from {settings.host}")
    print(json.dumps(accounts, indent=2, sort_keys=True))
    return 0


if __name__ == "__main__":
    sys.exit(main())
