# Paper bot, phase 0

This process lists Webull **sandbox** accounts and exits. It does not place orders, call Grok, or trade live. Live mode is not in this version. A later live phase would be a separate change with different keys.

The only HTTP host it accepts is `api.sandbox.webull.com`. `api.webull.com` and every other host make it refuse to start. Config defaults to paper and that sandbox host.

## Run

Use Python 3.11 or newer. Sandbox app key and app secret come from Webull **Using OpenAPI service in Paper Trading**. Do not generate live keys for this app.

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e .

export WEBULL_APP_KEY="sandbox-app-key"
export WEBULL_APP_SECRET="sandbox-app-secret"
export WEBULL_OPENAPI_TOKEN_DIR="$HOME/.config/paperbot/token"

python -m paperbot
```

`WEBULL_OPENAPI_TOKEN_DIR` must be a directory outside this repository. The SDK would otherwise write `conf/token.txt` in the working directory. Nothing secret belongs in git.

The process uses `SandboxGateway`, which only lists accounts. `ReplayGateway` can record an order intent in memory and does not use the network. Neither gateway places an order.

Stdout prints the sandbox account list as JSON, then the process exits. Limits live in `config/risk.yaml` and are loaded at startup. Phase 0 does not use them to send an order.

## Checks

```bash
pip install -e ".[dev]"
pytest
```

Tests do not use the network.
