[README](../README.md) › docs index › 00 Reproduce this demo

# 00 — Reproduce this demo

<p>
<img src="./assets/icons/dev-console.svg" width="40" alt="Workstation tooling"/>&nbsp;
<img src="./assets/icons/entra-id.svg" width="40" alt="Microsoft Entra ID"/>&nbsp;
<img src="./assets/icons/foundry.svg" width="40" alt="Microsoft Foundry"/>&nbsp;
<img src="./assets/icons/speech.svg" width="40" alt="Voice Live API"/>&nbsp;
<img src="./assets/icons/users.svg" width="40" alt="Real-time avatar"/>&nbsp;
<img src="./assets/icons/foundry-models.svg" width="40" alt="gpt-realtime-2.1"/>
</p>

![azd up](./assets/badges/azd-up.svg) ![GA](./assets/badges/ga.svg) ![Opt-in](./assets/badges/opt-in.svg) ![Static only](./assets/badges/static-only.svg) ![Version](./assets/badges/version.svg)

A single-page orchestrator for someone with zero context: install the tools, provision Azure with one command, run the app, see the avatar talk, then (optionally) add the on-prem fallback. Each part ends with a checkpoint. It threads together [03 — Deployment](./03-deployment.md), [04 — Testing](./04-testing.md) and [05 — Troubleshooting](./05-troubleshooting.md); read those for the canonical, phased detail. Every snippet is PowerShell 7 and runs on Windows, macOS and Linux.

## At a glance

| | Scope | What works | Time (first run, indicative) |
|---|---|---|---|
| <img src="./assets/icons/users.svg" width="24" alt=""/> | **A–E: cloud demo** | Avatar, HD voices, semantic VAD, function calling | 30–45 min |
| <img src="./assets/icons/foundry.svg" width="24" alt=""/> | **+ F: hybrid fallback** ![Opt-in](./assets/badges/opt-in.svg) | Voice-only conversation when the cloud is unreachable | + 90–120 min (image pulls, Foundry Local, model download) |
| <img src="./assets/icons/dev-console.svg" width="24" alt=""/> | **Repeat stand-up** | Same as above with tools installed | 10–15 min (`azd up` + `python app.py`) |

## What you'll end up with

[![Reference architecture](./assets/ai-voice-live-avatar-architecture.png)](./assets/ai-voice-live-avatar-architecture.png)

<sub>Editable source: [`assets/ai-voice-live-avatar-architecture.drawio`](./assets/ai-voice-live-avatar-architecture.drawio). Terminal-friendly sketch:</sub>

```
┌─────────────────────────────────────────────────────────────────────┐
│ Your machine                                                        │
│   Browser  →  http://localhost:8000  ──┐                            │
│   python app.py  (FastAPI on :8000) ────┤                           │
│                                         ▼                           │
│                                Microsoft Foundry resource (Azure)   │
│                                  ├─ Voice Live API (gpt-realtime-2.1)│
│                                  ├─ Real-time avatar (WebRTC)       │
│                                  └─ HD voices, semantic VAD, AEC    │
│   (Optional, Part F) Speech STT + NTTS containers + Foundry Local   │
└─────────────────────────────────────────────────────────────────────┘
```

## Part A — Install local tools

| Tool | Check | Install (Windows / macOS / Linux) |
|---|---|---|
| <img src="./assets/icons/dev-console.svg" width="20" alt=""/> Python 3.10+ | `python --version` | `winget install Python.Python.3.12` / `brew install python@3.12` / `apt-get install python3.12 python3.12-venv` |
| <img src="./assets/icons/dev-console.svg" width="20" alt=""/> Azure CLI 2.60+ | `az --version` | `winget install Microsoft.AzureCLI` / `brew install azure-cli` / `curl -sL https://aka.ms/InstallAzureCLIDeb \| sudo bash` |
| <img src="./assets/icons/dev-console.svg" width="20" alt=""/> Azure Developer CLI | `azd version` | `winget install Microsoft.Azd` / `brew install azd` / `curl -fsSL https://aka.ms/install-azd.sh \| bash` |
| <img src="./assets/icons/commit.svg" width="20" alt=""/> Git | `git --version` | `winget install Git.Git` / `brew install git` / `apt-get install git` |
| <img src="./assets/icons/powershell.svg" width="20" alt=""/> PowerShell 7+ | `pwsh --version` | `winget install Microsoft.PowerShell` / `brew install --cask powershell` / `snap install powershell --classic` |
| <img src="./assets/icons/code.svg" width="20" alt=""/> Chrome or Edge 120+ | — | WebRTC + AudioWorklet; Firefox and Safari aren't tested |

**Checkpoint A** — every check command above prints a version that meets the minimum.

## Part B — Authenticate and provision Azure

Pick a Tier-1 region (`eastus2`, `westus2`, `swedencentral`, `southeastasia`, `centralindia`, `eastus` — [02 §1.3](./02-prerequisites.md#13-regional-availability-matrix)).

| Step | | Action | Gate |
|---|---|---|---|
| **B1** | <img src="./assets/icons/entra-id.svg" width="28" alt=""/> | Sign in to the **intended** tenant with both CLIs | ☐ `az account show` shows the right tenant + subscription |
| **B2** | <img src="./assets/icons/gear.svg" width="28" alt=""/> | Create an azd environment and set tenant, subscription, region | ☐ `azd env get-values` |
| **B3** | <img src="./assets/icons/foundry.svg" width="28" alt=""/> | `azd up` | ☐ `Preprovision checks passed` … `Provisioned. Next:` |

```pwsh
$TenantId       = "<tenant-id>"
$SubscriptionId = "<subscription-id>"
az login --tenant $TenantId
az account set --subscription $SubscriptionId
azd auth login --tenant-id $TenantId

git clone <your-repo-url> ai-voice-live-avatar
cd ai-voice-live-avatar
azd env new voice-avatar-dev
azd env set AZURE_TENANT_ID $TenantId
azd env set AZURE_SUBSCRIPTION_ID $SubscriptionId
azd env set AZURE_LOCATION eastus2
azd up
```

`azd up` creates the resource group, the Foundry resource (`AIServices`, S0, custom domain, system identity) and grants **you** Cognitive Services User + Foundry User. The `postprovision` hook writes `AZURE_AI_ENDPOINT` into `.env` and the IDs into `demo-ids.local.json` (both gitignored).

> [!WARNING]
> No bare `az login` / `azd up`: the `preprovision` hook stops if the Azure CLI points at a different tenant or subscription than the azd environment. Can't use IaC? Follow [03b — Manual deployment](./03b-manual-deployment.md) for the same resources in the portal, then continue at Part C.

**Checkpoint B**

```pwsh
azd env get-values | Select-String "AZURE_AI_ENDPOINT|FOUNDRY_NAME"
curl.exe -sS -I ((azd env get-value AZURE_AI_ENDPOINT)) | Select-Object -First 1   # any HTTP status = DNS + TLS OK
```

Role propagation can take **up to 5 minutes**; if Part D fails with an auth error, wait and retry.

## Part C — Install and configure the app

```pwsh
python -m venv .venv
. .\.venv\Scripts\Activate.ps1          # macOS/Linux: . ./.venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
Get-Content .env | Select-String AZURE_AI_ENDPOINT   # written by azd; otherwise copy .env.example and set it
```

`VOICE_LIVE_MODEL` defaults to `gpt-realtime-2.1`, built into Voice Live — no model deployment needed. Other options: [`hybrid/model-selection.md`](./hybrid/model-selection.md).

**Checkpoint C**

```pwsh
python -c "from config import settings; print('Missing:', settings.validate(), 'Model:', settings.VOICE_LIVE_MODEL)"
# → Missing: []  Model: gpt-realtime-2.1
```

## Part D — Run the cloud demo

```pwsh
az account show -o table                 # still the right tenant?
python app.py                            # Uvicorn running on http://0.0.0.0:8000
curl.exe -sS http://localhost:8000/api/health        # {"status":"ok","missing_keys":[]}
curl.exe -sS http://localhost:8000/api/avatars       # video + photo avatars
```

| Step | | Browser action | Expected |
|---|---|---|---|
| **D1** | <img src="./assets/icons/code.svg" width="28" alt=""/> | Open <http://localhost:8000> | Sidebar + empty avatar pane |
| **D2** | <img src="./assets/icons/users.svg" width="28" alt=""/> | Character `Lisa`, style `casual-sitting`, voice `Ava HD (US, F)`, **Enable Avatar** on → **Start Avatar** | Avatar appears and greets you within 5–10 s |
| **D3** | <img src="./assets/icons/speech.svg" width="28" alt=""/> | Click the mic, ask "What can you do?" | Your transcript, then a spoken reply |

**Checkpoint D (this is the demo)**

- [ ] Status dot green ("Connected"); avatar video and greeting audio play.
- [ ] The mic turns red when clicked and your speech is transcribed.
- [ ] The assistant replies with text + audio.

## Part E — Try voice-only and a few extras

| Try this | Why |
|---|---|
| Untick **Enable Avatar**, then Start | Voice-only mode: same conversation, no WebRTC video, faster start |
| Voice `Ada HD (UK, F)`, restart | HD voice swap |
| Voice `Jenny (US, F)` (standard), restart | The voice the local fallback also uses |
| `ENABLE_WEATHER_TOOL=true` in `.env`, restart, ask "What's the weather in Seattle?" | Function calling; say "near me" to use browser geolocation |
| `VOICE_LIVE_MODEL=gpt-realtime-2.1-mini` (or `gpt-realtime-1.5`), restart | Model swap with no code change (check the region offers it) |

**Checkpoint E** — each variation works, or you know which region/model limitation stopped it ([05](./05-troubleshooting.md)). Only need the cloud demo? Jump to [Cleanup](#cleanup).

## Part F — (Optional) Add the hybrid local fallback

Worth it when sites have unreliable internet, when you want to show a conversation with no Azure round-trip, or when you're scoping an offline-tolerant production deployment. Design: [06 — Hybrid local fallback](./06-hybrid-local-fallback.md).

| Step | | Action | Detail |
|---|---|---|---|
| **F1** | <img src="./assets/icons/dev-console.svg" width="28" alt=""/> | Use a branch with the hybrid code; prepare an edge host (16+ vCPU, 32+ GB, GPU recommended, Docker) | [03 §4.1–4.2](./03-deployment.md#41-use-a-branch-that-contains-the-hybrid-code) |
| **F2** | <img src="./assets/icons/speech.svg" width="28" alt=""/> | Start the STT + NTTS containers (`SPEECH_BILLING`, `SPEECH_API_KEY`) | [03 §4.3](./03-deployment.md#43-start-the-speech-containers) |
| **F3** | <img src="./assets/icons/foundry.svg" width="28" alt=""/> | Install Foundry Local (Windows, macOS or Linux), download `qwen2.5-7b-instruct` | [03 §4.4](./03-deployment.md#44-install-foundry-local-and-download-a-model) |
| **F4** | <img src="./assets/icons/gear.svg" width="28" alt=""/> | Set `ENABLE_LOCAL_FALLBACK=true` and the `LOCAL_*` values; restart | [03 §4.5](./03-deployment.md#45-wire-the-app-to-the-local-stack) |
| **F5** | <img src="./assets/icons/code.svg" width="28" alt=""/> | Verify cloud, forced-local and simulated-outage modes | below |

<details><summary><b>Show the three browser checks</b></summary>

1. **Cloud mode (default).** Start Avatar — a blue **CLOUD** badge appears next to the status dot; everything works as in Part D.
2. **Forced local mode.** Stop the app, set `FORCE_LOCAL_MODE=true`, restart, Start Avatar. The badge turns orange **LOCAL**, a banner appears, the avatar pane stays hidden, and the conversation flows through the local stack.
3. **Simulated outage.** Stop the app, set `AZURE_AI_ENDPOINT=https://does-not-exist.invalid`, unset `FORCE_LOCAL_MODE`, restart. After about 30 seconds `/api/hybrid/status` shows `reachable: false`; a new session opens in LOCAL mode with `cloud-unreachable: ...` in the banner.

</details>

**Checkpoint F** — `/api/hybrid/status` shows `enableLocalFallback: true`, populated `localStack`, `missingLocalConfig: []`, and the full matrix in [04 §3](./04-testing.md#3-hybrid-test-matrix-phase-4-only) passes.

> [!TIP]
> Running truly offline needs Microsoft approval and a commitment tier for disconnected containers ([03 §5.4](./03-deployment.md#54-switch-container-metering-to-disconnected-offline-tolerant-sites)); tune VAD for the room with [03 §5.5](./03-deployment.md#55-tune-vad-for-the-sites-acoustic-environment).

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `Missing env vars: AZURE_AI_ENDPOINT` | `.env` not in the repo root, or `WRITE_DOTENV=false` — copy the value from `azd env get-values` |
| `preprovision` refuses to continue | CLI on the wrong tenant/subscription — re-run B1 ([05 §4.1](./05-troubleshooting.md#41-preprovision-refuses-to-continue)) |
| Stuck on "Connecting…" | Model not offered in the region, or expired token ([05 §2.3–2.4](./05-troubleshooting.md#23-session-error-mentions-quota-429-or-the-model)) |
| `403` / `AuthorizationFailed` | Wait 5 minutes for RBAC; check both roles ([05 §2.2](./05-troubleshooting.md#22-session-error-403--authorizationfailed)) |
| Avatar fails, voice works | Region without the real-time avatar — use Tier 1 or voice-only |
| No mic popup | Use `http://localhost:8000`, not a LAN IP |
| Part F: NTTS 404 | `LOCAL_TTS_VOICE` doesn't match the image tag (`…-en-us-jennyneural` ⇒ `en-US-JennyNeural`) |

## Cleanup

```pwsh
# Ctrl-C the running python process
docker compose -f docker-compose.local.yml down -v     # Part F only
azd down --purge                                        # deletes the RG and purges the Foundry account
```

> [!CAUTION]
> `azd down --purge` deletes everything in the resource group. On the manual path use `az group delete --name <rg> --yes`, then `az cognitiveservices account purge --location <region> --resource-group <rg> --name <foundry-name>` to free the name immediately.

## Reference

| Doc | Purpose |
|---|---|
| [01 — Architecture](./01-architecture.md) | Design, request path, decisions |
| [02 — Prerequisites](./02-prerequisites.md) | Roles, regions, cost, hardware |
| [03 — Deployment](./03-deployment.md) · [03b — Manual](./03b-manual-deployment.md) | Canonical phases and gates |
| [04 — Testing](./04-testing.md) · [05 — Troubleshooting](./05-troubleshooting.md) | Test matrix · fixes |
| [06 — Hybrid local fallback](./06-hybrid-local-fallback.md) · [07 — Configuration](./07-configuration-reference.md) | On-prem path · every setting |
| Microsoft Learn | [Voice Live](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live) · [Text to speech avatar](https://learn.microsoft.com/azure/ai-services/speech-service/text-to-speech-avatar/what-is-text-to-speech-avatar) · [Speech containers](https://learn.microsoft.com/azure/ai-services/speech-service/speech-container-overview) · [Foundry Local](https://learn.microsoft.com/azure/foundry-local/what-is-foundry-local) |

---

Next: [01 — Architecture](./01-architecture.md) →

*Last updated: 2026-10-07*
