# 03 — Deployment

> Phased deployment with a validation gate at the end of each phase. Each
> phase is a discrete checkpoint — do not start the next phase until the gate
> passes.
>
> Phases 1–3 are **required** for any deployment.
> Phases 4–5 are **optional** — enable them only if the on-prem hybrid
> fallback or production hardening matters for your site.
>
> Time budget (first-time): **30–45 min** Phases 1–3, plus **90–120 min**
> for Phases 4–5.

If you're standing this up for the first time, use the orchestrator at
[`00-reproduce-this-demo.md`](./00-reproduce-this-demo.md) — it threads
this document together with the install + browser-test steps in one place.
This document is the canonical phased reference.

---

## Phase 1 — Provision the Azure surface

### 1.1 Authenticate and pick a subscription

```pwsh
az login
az account show -o table
# If you have multiple subscriptions:
# az account set --subscription "<name-or-id>"
```

### 1.2 Variables (customize)

```pwsh
$Region      = "eastus2"
$RgName      = "rg-aitts-dev-$Region"
$FoundryName = "aif-aitts-dev-$Region-$(Get-Random -Maximum 999)"
```

### 1.3 Create the resource group

```pwsh
az group create --name $RgName --location $Region -o table
```

### 1.4 Create the Foundry resource (`kind=AIServices`)

```pwsh
az cognitiveservices account create `
    --name $FoundryName `
    --resource-group $RgName `
    --location $Region `
    --kind AIServices `
    --sku S0 `
    --custom-domain $FoundryName `
    --assign-identity `
    --yes -o table
```

> No model deployment is needed for the built-in `gpt-realtime` family —
> Voice Live serves them directly. Deploy a model only when you need BYOM
> (see [`hybrid/model-selection.md`](./hybrid/model-selection.md)).

### 1.5 Verify region supports your feature set

```pwsh
# Confirm the resource shows the expected kind + region
az cognitiveservices account show --name $FoundryName --resource-group $RgName `
    --query "{name:name, kind:kind, location:location, sku:sku.name, endpoint:properties.endpoint}" -o table

# Confirm the chosen Voice Live model is available in the region
$model = "gpt-realtime"   # or gpt-realtime-2, gpt-realtime-1.5
az cognitiveservices model list --location $Region `
    --query "[?model.name=='$model' || contains(model.name, '$model')].{name:model.name, version:model.version, format:model.format}" `
    -o table
```

### 1.6 Grant yourself RBAC

```pwsh
$Me = az ad signed-in-user show --query id -o tsv
$Scope = az cognitiveservices account show `
    --name $FoundryName --resource-group $RgName --query id -o tsv

az role assignment create --assignee-object-id $Me --assignee-principal-type User `
    --role "Cognitive Services User" --scope $Scope -o table

az role assignment create --assignee-object-id $Me --assignee-principal-type User `
    --role "Azure AI User" --scope $Scope -o table
```

> Role propagation can take up to 5 minutes. If Phase 3 fails with `403 / AuthorizationFailed`, wait and retry.

### ✅ Validation gate — Phase 1

```pwsh
az role assignment list --assignee $Me --scope $Scope `
    --query "[].roleDefinitionName" -o tsv
# Expect both: Cognitive Services User, Azure AI User

$endpoint = "https://$FoundryName.services.ai.azure.com"
curl.exe -sS -I $endpoint | Select-Object -First 1
# Expect any response (200/401/404) — proves DNS + TLS work
```

---

## Phase 2 — Install and configure the app

### 2.1 Clone and install dependencies

```pwsh
git clone <your-repo-url> ai-tts-avatar
cd ai-tts-avatar
git checkout main                       # or feature/hybrid-local-fallback for Phase 4

python -m venv .venv
. .\.venv\Scripts\Activate.ps1          # macOS/Linux: . ./.venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### 2.2 Configure `.env`

```pwsh
Copy-Item .env.example .env
notepad .env                            # or: code .env
```

Edit two lines:

```env
AZURE_AI_ENDPOINT=https://aif-aitts-dev-eastus2-123.services.ai.azure.com   # from Phase 1.5
VOICE_LIVE_MODEL=gpt-realtime                                                # or gpt-realtime-2 / gpt-realtime-1.5
```

Leave everything else at defaults. The Voice Live model list lives in
[`hybrid/model-selection.md`](./hybrid/model-selection.md); the env vars are
documented in `.env.example`.

### ✅ Validation gate — Phase 2

```pwsh
python -c "from config import settings; print('Missing:', settings.validate(), 'Model:', settings.VOICE_LIVE_MODEL)"
# Expect: Missing: []  Model: gpt-realtime (or your chosen variant)
```

---

## Phase 3 — Run and validate the cloud path

### 3.1 Boot the app

```pwsh
az account show -o table      # make sure your token is still good
python app.py
# → Uvicorn running on http://0.0.0.0:8000
```

In a second terminal:

```pwsh
curl.exe -sS http://localhost:8000/api/health
# → {"status":"ok","missing_keys":[]}
```

### 3.2 Smoke test in the browser

1. Open <http://localhost:8000>.
2. Sidebar: Character `Lisa`, Style `casual-sitting`, Voice `Ava HD (US, F)` (default).
3. Make sure **Enable Avatar** is checked.
4. Click **Start Avatar**.
5. Within 5–10 seconds Lisa appears and greets you.
6. Click the mic, ask "What can you do?" — she should respond.

### ✅ Validation gate — Phase 3

- [ ] Status dot turns green ("Connected").
- [ ] Avatar video plays.
- [ ] Greeting audio plays.
- [ ] Mic icon turns red when clicked; your speech is transcribed in the chat panel.
- [ ] Assistant replies with text + audio.

If anything fails, see [`05-troubleshooting.md`](./05-troubleshooting.md) before continuing.

**At this point the cloud demo is complete.** Stop here unless you want the
optional hybrid path (Phase 4) or production hardening (Phase 5).

---

## Phase 4 — (Optional) Enable the on-prem hybrid fallback

Skip this phase unless you need a usable experience when the cloud is
unreachable. Background: [`hybrid/customer-report.md`](./hybrid/customer-report.md)
explains the approach, [`hybrid/azure-vs-onprem-responsibility.md`](./hybrid/azure-vs-onprem-responsibility.md)
spells out exactly what stays in Azure vs runs on-prem.

### 4.1 Switch to the hybrid branch (until merged to main)

```pwsh
git fetch
git checkout feature/hybrid-local-fallback
pip install -r requirements.txt        # adds the openai SDK for Foundry Local
```

### 4.2 Prepare the edge host

Refer to [`02-prerequisites.md §2.1`](./02-prerequisites.md#21-edge-host-hardware-per-site) for sizing. For a single dev box you can run everything on the same machine you used for Phases 1–3. For production, put the app + containers + Foundry Local on the same edge host so all hops are loopback.

### 4.3 Start the Speech containers

```pwsh
$env:SPEECH_BILLING = "https://$FoundryName.cognitiveservices.azure.com/"
$env:SPEECH_API_KEY = az cognitiveservices account keys list `
    --name $FoundryName --resource-group $RgName --query key1 -o tsv

docker compose -f docker-compose.local.yml pull          # ~6 GB first time
docker compose -f docker-compose.local.yml up -d
docker compose -f docker-compose.local.yml ps             # both services Up
```

### 4.4 Install Foundry Local and download a model

```pwsh
# Windows
winget install Microsoft.FoundryLocal
# macOS
# brew install foundrylocal

foundry model download qwen2.5-7b-instruct       # ~5 GB; or phi-4
foundry service start
foundry service status                            # prints port, usually http://localhost:5273
```

> **Linux substitute** (Foundry Local doesn't officially ship on Linux yet):
> `pip install "vllm>=0.6"` then `vllm serve Qwen/Qwen2.5-7B-Instruct --port 5273 --served-model-name qwen2.5-7b-instruct`. See [`hybrid/model-selection.md`](./hybrid/model-selection.md).

### 4.5 Wire the app to the local stack

Edit `.env`:

```env
ENABLE_LOCAL_FALLBACK=true
LOCAL_STT_ENDPOINT=http://localhost:5001
LOCAL_TTS_ENDPOINT=http://localhost:5002
LOCAL_TTS_VOICE=en-US-JennyNeural        # must match the NTTS container tag
LOCAL_LLM_ENDPOINT=http://localhost:5273/v1
LOCAL_LLM_MODEL=qwen2.5-7b-instruct      # must match the Foundry Local alias
```

Restart `python app.py`.

### ✅ Validation gate — Phase 4

```bash
# STT — empty POST proves routing works (returns error envelope)
curl -sS -X POST \
  "http://localhost:5001/speech/recognition/conversation/cognitiveservices/v1?language=en-US" \
  -H "Content-Type: audio/wav; codecs=audio/pcm; samplerate=16000" \
  --data-binary "@/dev/null" | head -c 200 ; echo

# NTTS — synth "Hello" to WAV
curl -sS -X POST "http://localhost:5002/cognitiveservices/v1" \
  -H "Content-Type: application/ssml+xml" \
  -H "X-Microsoft-OutputFormat: riff-24khz-16bit-mono-pcm" \
  -H "User-Agent: setup-test" \
  -o /tmp/hello.wav \
  --data '<speak version="1.0" xml:lang="en-US"><voice name="en-US-JennyNeural">Hello.</voice></speak>'
file /tmp/hello.wav   # → RIFF (little-endian) data, WAVE audio, ...

# Foundry Local
curl -sS http://localhost:5273/v1/models | head -c 200 ; echo
```

App-side:

```pwsh
curl.exe -sS http://localhost:8000/api/hybrid/status | python -m json.tool
# Expect:
#   enableLocalFallback: true
#   supervisor.reachable: true
#   localStack.{stt,tts,llm,voice,model}: all populated
#   missingLocalConfig: []
```

Run the 10-row matrix in [`04-testing.md §3`](./04-testing.md#3-hybrid-test-matrix-phase-4-only) to confirm cloud, forced-local, and simulated-outage modes all work.

---

## Phase 5 — (Optional) Production hardening

Apply once both modes work end-to-end. Each item is independent — adopt the ones that match your operational model.

### 5.1 Run the app as a service

| OS | Command |
|---|---|
| Linux (systemd) | Create `/etc/systemd/system/ai-tts-avatar.service` pointing at `python app.py` in the venv, `User=` the service account, `Restart=always`. `systemctl enable --now ai-tts-avatar`. |
| Windows | Use [NSSM](https://nssm.cc/) to wrap `python app.py` as a service. |

### 5.2 Pin container tags

Already done in `docker-compose.local.yml` — never replace with `:latest` for production. Tag bumps should go through a lab site first.

### 5.3 Route logs to your SIEM

The STT container logs include recognized text by default. Decide whether to:
- Accept it on the host (mount `/var/log/<service>`).
- Pipe through your log shipper with PII redaction.

### 5.4 Switch container metering to **disconnected** (offline-tolerant sites)

Pre-requirement: Microsoft approval (~10 business days) + commitment-tier SKU. Steps:

1. Run each container once **online** with `DownloadLicense=True` and a license mount:

   ```bash
   mkdir -p ./speech-licenses/stt ./speech-licenses/tts
   docker run --rm -v $(pwd)/speech-licenses/stt:/license \
     mcr.microsoft.com/azure-cognitive-services/speechservices/speech-to-text:5.1.0-amd64-en-us \
     Eula=accept Billing="$SPEECH_BILLING" ApiKey="$SPEECH_API_KEY" \
     DownloadLicense=True Mounts:License=/license
   ```

   (Repeat for NTTS.)

2. Switch `docker-compose.local.yml` to mount the license dir read-only and drop the `ApiKey`/`Billing` env vars at runtime.
3. Re-run `DownloadLicense=True` every ~30 days on a host with internet to refresh.

Authoritative reference: [Use containers in disconnected environments](https://learn.microsoft.com/azure/ai-services/containers/disconnected-containers).

### 5.5 Tune VAD for the site's acoustic environment

Energy-based VAD is environment-sensitive. Recalibrate with a fixed mic in the deployment room:

| Variable | Default | Tune when |
|---|---|---|
| `LOCAL_VAD_RMS_THRESHOLD` | `350` | Too sensitive → raise to 500–800 for noisy rooms; not sensitive enough → drop to 200–250 for quiet rooms. |
| `LOCAL_VAD_SILENCE_MS` | `700` | Snappier turn-taking → lower; more permissive (slow speakers) → raise to 1000–1200. |
| `LOCAL_VAD_MIN_SPEECH_MS` | `250` | Filters mic clicks; rarely needs tuning. |
| `LOCAL_VAD_MAX_UTTERANCE_MS` | `20000` | Hard cap; raise if your users routinely talk longer than 20 s. |

Background: [`04-testing.md §5`](./04-testing.md#5-vad-tuning-and-acoustic-validation).

### 5.6 Identity

| Use case | What to use |
|---|---|
| Dev box | `az login` (current behavior) |
| Linux VM | Managed identity attached to the VM; `DefaultAzureCredential` picks it up automatically |
| Container / K8s | Workload identity / pod identity; `DefaultAzureCredential` picks it up automatically |
| CI/CD smoke deploys | Service principal with federated credentials (no checked-in secret) |

### 5.7 Observability

- `/api/health` — liveness + config sanity (used by the load balancer).
- `/api/hybrid/status` — supervisor state + local-stack config (alertable on `reachable: false` for > N minutes if you have a runbook for it).

---

## Reference

- Single-page orchestrator: [`00-reproduce-this-demo.md`](./00-reproduce-this-demo.md)
- Architecture: [`01-architecture.md`](./01-architecture.md)
- Prerequisites: [`02-prerequisites.md`](./02-prerequisites.md)
- Testing: [`04-testing.md`](./04-testing.md)
- Troubleshooting: [`05-troubleshooting.md`](./05-troubleshooting.md)
- Hybrid deep-dives: [`hybrid/`](./hybrid/) (customer report, implementation plan, azure-vs-onprem split, model selection)

---

*Last updated: 2026-06-04*
