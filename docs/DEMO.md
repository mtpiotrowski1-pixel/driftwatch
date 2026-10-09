# Offline demonstration

After [source installation](INSTALL.md), run the demo from the repository root
using the interpreter in the installer's `.venv`. The installer does not activate
your shell; these commands work without activation.

On Windows (PowerShell):

```powershell
.\.venv\Scripts\python.exe -m driftwatch.demo
```

On Linux:

```sh
.venv/bin/python -m driftwatch.demo
```

For automation-friendly JSON, append `--json` to either command. For example,
on Windows:

```powershell
.\.venv\Scripts\python.exe -m driftwatch.demo --json
```

This is a **scripted demonstration**, labelled in both human and JSON output. It does not launch Chromium, contact OpenAI, send email, or load the application's `.env`. It uses a new temporary SQLite database on each run and removes it afterward. Existing application databases and monitored sites are untouched. DNS and network connections are denied while the scenario runs; an unexpected connection fails the command.

The capture, AI and delivery adapters are deliberately scripted. The monitoring pipeline, `SiteRunner`, database transactions, analysis ownership and notification outbox are the application's actual implementations. The temporary schema is created from the ORM models; this demonstration does **not** verify Alembic installation or upgrades.

| Stage | Observed behavior |
| --- | --- |
| `baseline` | First capture stores one snapshot and creates no change event. |
| `noise_ignored` | A different request ID is ignored; snapshot and event counts stay unchanged. |
| `ai_failed` | A Basic price change creates an event. A scripted AI failure leaves it unresolved and sends nothing. |
| `partial_delivery` | Retrying analysis succeeds. One destination accepts delivery; the other fails once. The change remains incomplete. |
| `delivery_recovered` | A manual delivery retry completes the remaining destination. It reuses the verdict and does not repeat the already accepted destination. |
| `ai_disabled_delivery` | A later price change is delivered with AI disabled. It consumes no additional AI analysis or quota. |

The command checks these outcomes before reporting success. A contract failure exits with an error. JSON includes real persisted state after each stage, snapshot/event/history counts, scripted AI calls and accepted-delivery counts. It contains no timestamps or generated credentials, so successive runs produce the same report.

The sample addresses use `example.invalid` and the watched URL uses `demo.invalid`. Provider IDs and summaries explicitly say `demo` or `scripted`; none is evidence of a real provider integration or a billed model call. The two quota reservations illustrate the application's accounting, while the scripted cost is zero.

With development dependencies installed (`.\install.ps1 -Dev` on Windows or
`sh install.sh --dev` on Linux), inspect the real browser capture path separately.

On Windows (PowerShell):

```powershell
.\.venv\Scripts\python.exe -m playwright install chromium
.\.venv\Scripts\python.exe -m pytest -q tests/test_capture_browser.py tests/test_capture_worker.py
```

On Linux:

```sh
.venv/bin/python -m playwright install chromium
.venv/bin/python -m pytest -q tests/test_capture_browser.py tests/test_capture_worker.py
```

`test_capture_browser.py` launches a real browser against a test-owned local HTTP server. An injected validator permits only that fixture, including its intentional redirect. The tests exercise short selected elements, redirects and document base URLs, HTTP failure pages, request-specific timing and origin-bound fills. The remote-browser test exercises authenticated HTTP/ASGI serialization and a real browser. Separate deployment tests must still verify the actual worker service, production egress policy and any external provider that will be used.
