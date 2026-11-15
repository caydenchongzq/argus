# Argus

Local dashboard for [TradingAgents](../TradingAgents) — view your portfolio, watchlist, per-stock reports, and fund-manager plans, and trigger selective or full runs from one place.

**Decision support only. Not financial advice.**

## Requirements

- Python 3.10+.
- TradingAgents checked out beside Argus, or set `TRADINGAGENTS_ROOT` to its location.
- TradingAgents' own Python environment, prepared from its `pyproject.toml`; its Linux package requires Python 3.11 or newer.
- Provider credentials configured for the same local user when paid runs are intended.
- Set `TRADINGAGENTS_PYTHON` to another prepared interpreter only when the TradingAgents checkout is elsewhere. Argus checks required runtime imports before starting any stage and stops with setup instructions if they are missing.

Argus **never** reads or prints `.env` / API keys. It reads portfolio and report data and launches the TradingAgents Python add-on commands through `run_analysis.py`; it does not invoke Docker or PowerShell.

## Quick start

```powershell
cd "D:\software development\trading\argus"
.\start.ps1 -Install   # first time: creates .venv and installs deps
.\start.ps1            # later starts
```

Open **http://127.0.0.1:8788** (loopback by default).

On Linux, create the virtual environment, then run:

```sh
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
./start.sh
```

Prepare the separate TradingAgents runtime once from the Argus directory. This installs the checked out TradingAgents package and its declared dependencies into `TradingAgents/.venv`; it does not read or print provider credentials. Then run the isolated runtime check:

```sh
./setup_tradingagents_env.sh
./check_tradingagents_runtime.sh
```

The check imports the actual TradingAgents data modules and runs its real `preflight.py` with `--session-only` and a temporary output/data directory. It makes no market-data request, model call, or write to the real TradingAgents data folder. Analysis jobs then use the sibling `TradingAgents/.venv/bin/python` by default; an explicit `TRADINGAGENTS_PYTHON` override is also checked before stages start.

Argus starts on loopback by default. To expose it to your trusted LAN, bind to the specific bridged interface address (never `0.0.0.0`):

```sh
ARGUS_HOST=192.168.1.115 ./start.sh
```

Then open `http://192.168.1.115:8788`. LAN mode has no login or TLS: anyone on that LAN can view portfolio data and operate the dashboard. Keep it on a trusted private network. Host validation, same-origin checks, and confirmation tokens for writes and runs remain enabled.

### Run in the background on Linux

The following installs a systemd user service so Argus runs without an open terminal and restarts if it fails. Complete the Linux and TradingAgents setup above first.

1. Check the server's LAN address with `ip -br address`. The example below uses `192.168.1.115`; replace it with your server's address if different. Use `127.0.0.1` instead if only the server itself should access Argus.

2. If a temporary Argus service is already running, stop it before installing the permanent one:

   ```sh
   systemctl --user stop argus.service
   ```

   If no service exists, an error here can be ignored. Also stop any Argus instance started in a terminal so port 8788 is free.

3. Create `~/.config/systemd/user/argus.service` (create the directory if needed), replacing the paths if your checkout is elsewhere:

   ```ini
   [Unit]
   Description=Argus dashboard

   [Service]
   WorkingDirectory=/home/dev/projects/trading/argus
   Environment=ARGUS_HOST=192.168.1.115
   ExecStart=/home/dev/projects/trading/argus/start.sh
   Restart=on-failure
   RestartSec=5

   [Install]
   WantedBy=default.target
   ```

4. Load, enable, and start the service:

   ```sh
   systemctl --user daemon-reload
   systemctl --user enable --now argus.service
   systemctl --user status argus.service
   ```

5. Open `http://192.168.1.115:8788` from a device on the trusted LAN. If it doesn't connect, check the service status, the server address, and whether the firewall permits TCP port 8788. LAN mode has no login or TLS; anyone on that network can view and operate the dashboard.

The enabled service starts when your user session starts. To also start it at boot without logging in, enable lingering for your account once with `sudo loginctl enable-linger "$USER"`.

To manage it later:

```sh
systemctl --user stop argus.service       # stop
systemctl --user start argus.service      # start again
systemctl --user restart argus.service    # restart after changes
journalctl --user -u argus.service -f     # follow logs; Ctrl+C stops viewing
```

If you edit the service file, run `systemctl --user daemon-reload` and then restart the service. To disable automatic startup, run `systemctl --user disable --now argus.service`.

Analysis runs start only when requested in the dashboard; there is no cron or timer. Manual runs and theme scouting share a process lock. “No LLM” skips every model stage, including per-ticker agents, while retaining the free snapshot workflow. Cost checks use the existing estimates and ledger; provider-side limits remain the hard spending control.

Optional:

```powershell
.\start.ps1 -Port 8790
$env:TRADINGAGENTS_ROOT = "D:\path\to\TradingAgents"
.\start.ps1
```

## What you get

| Tab | Features |
|-----|----------|
| **Portfolio** | Consolidated USD stock holdings plus per-account cash, holdings value, and snapshot time. Unknown account cash stays unknown; totals and cash percentages are unavailable when cash is incomplete. |
| **Watchlist** | View / add / remove candidates; writes `data\watchlist.json` and appends `data\watchlist_log.jsonl`; **Undo** reverses the last add or removal. Candidates retain sector and instrument classifications. |
| **Reports** | List by ticker/date, rendered Markdown, latest rating highlighted |
| **Fund manager** | Latest plan with validation status, account, requested/effective shares, estimated fee, cash effect, and reason. History includes timestamped run folders; older reports remain readable. |
| **Themes** | Latest theme-scout report and the free daily screen. Run buttons use the confirm token. The Sol call is off unless the checkbox is set |
| **Runs** | Selective runs. Cost warning is ~2.5 min/ticker plus 5 fund-manager calls (Opus for conservative, Luna for neutral). POST `/api/runs` needs `confirm: true` and the `X-Argus-Confirm` token from `GET /api/session`. Requests whose Host does not match loopback or the explicitly configured `ARGUS_HOST` are rejected |

## Layout

```
argus/
  server.py          FastAPI backend
  start.ps1          Windows launcher (127.0.0.1)
  start.sh           Linux launcher (127.0.0.1 by default)
  run_analysis.py    native TradingAgents pipeline for dashboard runs
  requirements.txt
  static/            single-page UI (no build step)
  runs/              local run metadata + logs (not TradingAgents)
  README.md
```

## Safety notes

- Binds to **127.0.0.1** by default. Optional LAN binding requires the explicit interface address in `ARGUS_HOST`; wildcard binding is rejected. In LAN mode, there is no login or TLS and anyone on the private network can access portfolio data.
- Markdown from reports is rendered with pinned local marked 15.0.12 and sanitized with DOMPurify 3.2.4. Chart.js 4.4.7 is local too.
- POST `/api/runs` requires the per-process confirm token plus `confirm: true`.
- Does **not** modify TradingAgents source files.
- Watchlist edits require the per-process confirmation token, use atomic JSON replacement, and are blocked while an analysis holds the shared data lock.
- Trade guidance estimates $3 per accepted buy or sell order and uses a $1,000 minimum order notional and a $1,000 residual-position guide. These are planning defaults, not broker quotes or profit guarantees. Smaller buys are rejected; valid risk-reducing sells remain allowed. Proposed exits are account-local and no order is routed.
- Broker import uses read-only account/position queries and refreshes only the selected account. The first broker import with a legacy book requires an explicit choice to replace it or keep it separately. Unsupported non-US-stock assets and currencies stay outside USD totals; incomplete supported stock rows block application. Each import requires a reviewed preview and stock-scope confirmation.
- Moomoo securities account cash is treated as unknown unless USD cash is verified. Buying power and other cash-like fields are not substituted for USD cash; an account with unknown cash cannot produce validated actionable trades. The dashboard may show priced holdings and known-cash subtotals while leaving total equity and cash allocation unavailable.
- Portfolio import and configuration cleanup retain backups. A cleanup preview must be reviewed and its fingerprint supplied to apply; cleanup does not rewrite historical reports or the append-only watchlist event log. To restore a backed-up JSON file on Linux, copy the matching `*.bak_<timestamp>` file over its original, for example `cp targets.json.bak_<timestamp> targets.json`, while Argus/TradingAgents are stopped.
- Do not start paid agent runs from Argus unless you mean to spend OpenRouter credits.

## Read-only broker setup

Tiger OAuth is for individual accounts and does not use the RSA private key. First enable OpenAPI for the funded account in the Tiger Developer Center. Install the optional SDK into the same Python environment that runs Argus, then authorize as the same Linux user so the token is stored in that user's local Tiger directory. The helper uses Tiger's device-code flow, so the verification page and code can be opened on Windows while Argus runs in the Linux guest:

```sh
.venv/bin/pip install -r tiger-requirements.txt
.venv/bin/python tiger_auth.py
```

Open the printed authorization link, sign in to Tiger, and grant account/position query access only; leave trading permissions disabled. Then open Argus, choose **Import broker account**, select Tiger, load the authorized account, and review the snapshot before applying. The browser sees account aliases, not raw account identifiers. Do not send RSA keys, OAuth tokens, or account exports through chat. OAuth access can expire and may need reauthorization.

If Argus currently shows `my_book.json` as missing, that is a first-import state: the Portfolio tab starts empty and the reviewed account apply creates the book. Fetching a preview does not create or modify it. Tiger's current [Python preparation guide](https://docs-en.itigerup.com/docs/prepare) documents `OAuth2SessionManager` and the authorization flow; [authentication guidance](https://docs-en.itigerup.com/docs/authentication) explains OAuth account and permission selection. The Tiger SDK is optional and is not installed by the main `requirements.txt`.

### Moomoo Singapore

Argus reads Moomoo through **OpenD**, Moomoo's local API gateway. OpenD handles the Moomoo login; Argus uses the optional Python SDK to query it. This integration does not use Tiger OAuth or require you to create an API key in Argus. It uses the Singapore firm `FUTUSG` and the US-filtered `OpenSecTradeContext` supplied by the pinned SDK.

These steps run OpenD on the **same Linux machine as Argus**. `127.0.0.1` below refers to that Linux machine, not the device running your browser.

1. Install the SDK in the environment used by the running Argus service:

```sh
cd /home/dev/projects/trading/argus
.venv/bin/python -m pip install -r moomoo-requirements.txt
.venv/bin/python -c 'import moomoo; print("Moomoo SDK import OK")'
```

2. Download the Linux command-line OpenD package from the [official download page](https://www.moomoo.com/download/OpenAPI). Extract the complete archive, keeping `OpenD.xml`, `Appdata.dat` and the executable together. In a terminal, change into the extracted OpenD directory and start it:

```sh
./OpenD
```

Follow its interactive login prompts using your Moomoo Singapore account, including any first-use agreement or verification. OpenD offers a remember-password choice; that is optional. Do not put the Moomoo password in Argus configuration. Leave OpenD running. The CLI route needs no Linux desktop; the optional graphical OpenD application requires a graphical session and its documented WebSocket setup. See the [official Linux CLI instructions](https://openapi.moomoo.com/moomoo-api-doc/en/opend/opend-cmd.html).

3. Keep the local API listener at `127.0.0.1:11111`. In a second Linux terminal, check that it is reachable:

```sh
python3 -c 'import socket; s = socket.create_connection(("127.0.0.1", 11111), timeout=3); s.close(); print("OpenD listener reachable")'
```

This checks the listener only; it does not prove account authorization. Reload Argus after installing the SDK, then refresh the dashboard:

```sh
systemctl --user restart argus.service
```

4. Test the actual read-only pull at [Argus](http://192.168.1.115:8788): **Portfolio → Import broker account → Broker: Moomoo Singapore**. Selecting the broker loads authorized accounts automatically. Select your real US-authorized account and click **Fetch preview**. **Stop at preview for the first test.** No portfolio file is changed by fetching it, and this path does not place orders or run AI analysis.

5. Check the snapshot timestamp, US stock quantities, average costs and exclusions against that Moomoo account. Compare acquisition **average cost**, not Moomoo's diluted/break-even cost. Missing average cost stays unavailable. If Argus prompts about an existing legacy book and it contains your Tiger holdings, choose **Add this as a separate account and keep the legacy book**, then fetch a fresh preview. Do not replace the Tiger book with Moomoo.

6. After reconciliation, review the scope and confirmation boxes and select **Apply account snapshot**. This updates only that account and retains a backup. In **Portfolio**, use the account filter to check each broker separately, then **All accounts** to check combined quantities and compatible quantity-weighted costs. Use **Runs → Refresh snapshot → Run snapshot** for updated portfolio prices without model calls. That price refresh does not pull new broker quantities; repeat the broker preview/apply flow when those change.

Only supported US/USD stock positions are included. Non-USD balances, options and other markets are disclosed as excluded; an incomplete supported-stock query blocks application. Moomoo USD cash remains **unknown**, even when buying power or other cash-like values are returned. Holdings can be imported, but the account cannot fund validated actionable trades until its USD cash is verified; cash-dependent combined totals remain unavailable rather than becoming zero.

**Testing boundary:** the adapter, account merging, cost/cash handling, preview/apply guards and UI have passed offline fixture checks. Live OpenD connectivity and Singapore account authorization must be tested with your own signed-in gateway using the preview steps above. If SDK import fails, resolve the installation first; if the listener check fails, start/configure OpenD; if account loading fails or returns no account, check the OpenD login, first-use agreements and real-account US market authorization. Do not bypass an unsupported or incomplete preview by applying an empty account.

### Preview and apply configuration cleanup

From the TradingAgents checkout, preview the narrowly scoped cleanup against its data directory. The preview prints an expected fingerprint and changed key paths:

```sh
cd ../TradingAgents
.venv/bin/python addons/config_cleanup.py --data-root data
```

Review the paths and preserve the generated backups. Apply only with the fingerprint returned by the preview:

```sh
.venv/bin/python addons/config_cleanup.py --data-root data --apply --expected-fingerprint <fingerprint-from-preview>
```

If a restore is needed, stop Argus/TradingAgents and copy the matching backup file for each changed JSON file over its original, for example:

```sh
cp data/targets.json.bak_TIMESTAMP data/targets.json
cp data/watchlist.json.bak_TIMESTAMP data/watchlist.json
```

Replace `TIMESTAMP` with the suffix from the backup filename. Keep the backup files until you verify the dashboard and reports after migration. Do not edit `watchlist_log.jsonl` or historical reports as part of this cleanup.

## License / scope

Side project for personal use with your local TradingAgents install.
