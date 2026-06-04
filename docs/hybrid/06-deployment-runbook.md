# 06 — Deployment runbook

> Single-page orchestrator for standing up the hybrid AI TTS Avatar — cloud
> path + on-prem local-fallback path — from scratch. Each Part is a discrete
> checkpoint; finish A before starting B.
>
> Detail docs are linked inline so you can drop into the runbook from your
> deep-dive references (architecture, prerequisites, on-prem setup, app
> configuration, testing, model selection).

---

## What you'll end up with

```
┌─────────────────────────────────────────────────────────────────────────┐
│ Browser (Chrome / Edge)                                                 │
│   ↕ WebSocket   ↕ WebRTC (cloud mode only)                              │
└──────────────────┬──────────────────────────────────────────────────────┘
                   │
┌──────────────────▼──────────────────────────────────────────────────────┐
│ FastAPI app (app.py)        — runs on the edge host OR a central server │
│   ├─ ConnectivitySupervisor (HTTPS probe of AZURE_AI_ENDPOINT)          │
│   ├─ CloudVoiceLiveSessionHandler  ── Azure path                        │
│   └─ LocalSessionHandler            ── on-prem path                     │
└──────────────────┬──────────────────────────────────────┬───────────────┘
                   │ when cloud reachable                 │ when unreachable
                   ▼                                      ▼
┌─────────────────────────────────────────┐ ┌────────────────────────────┐
│ Azure                                   │ │ On-prem edge box           │
│   Foundry resource (kind=AIServices)    │ │   docker-compose.local.yml │
│     ├─ Voice Live API                   │ │     ├─ Speech STT          │
│     │     model = gpt-realtime[-2/-1.5] │ │     │     :5001            │
│     ├─ TTS Avatar Service (WebRTC)      │ │     └─ NTTS                │
│     ├─ HD voices, semantic VAD, AEC     │ │           :5002            │
│     └─ (optional) BYOM deployments      │ │   Foundry Local            │
│                                         │ │     :5273  qwen2.5-7b/phi-4│
└─────────────────────────────────────────┘ └────────────────────────────┘
```

Time budget: **first stand-up ≈ 3–5 hours** end-to-end (dominated by container
image pulls and Foundry Local model download). Subsequent stand-ups on
prepared hosts: **under 1 hour**.

---

## Prerequisites checklist (verify before Part A)

Full details: [`02-prerequisites.md`](./02-prerequisites.md).

- [ ] **Azure subscription** with Contributor + User Access Administrator on the target RG.
- [ ] **Microsoft Foundry resource** (`kind=AIServices`) in a region that supports every cloud feature you plan to use — see the matrix in the root `README.md`. Default for full feature parity: `eastus2`, `westus2`, `westeurope`, `swedencentral`, `southeastasia`.
- [ ] **RBAC:** the app's identity (your user for `az login` dev, or a managed identity in prod) has **Cognitive Services User** + **Azure AI User** on the Foundry resource.
- [ ] **Voice Live model:** confirmed access to at least one of `gpt-realtime`, `gpt-realtime-2`, `gpt-realtime-1.5` (see [`08-model-selection.md`](./08-model-selection.md)).
- [ ] **(For offline / disconnected sites)** Microsoft approval from <https://aka.ms/csdisconnectedcontainers> + commitment-tier SKU purchased.
- [ ] **Edge host** sized per [`02-prerequisites.md`](./02-prerequisites.md): 16+ vCPU, 32+ GB RAM, optional NVIDIA GPU ≥ 16 GB VRAM (recommended for Foundry Local), Docker 24+ / Podman 4+.
- [ ] **Local dev tools:** Python 3.10+, `az` 2.60+ with the `bicep` extension installed, `git`, PowerShell 7+ (`pwsh`).
- [ ] Outbound HTTPS from the edge host to `mcr.microsoft.com`, `*.cognitiveservices.azure.com`, `*.services.ai.azure.com`, `login.microsoftonline.com`.

---

## Part A — Provision and confirm the Azure surface

Goal: working cloud-only experience before any on-prem work begins. If Part A
doesn't pass, no amount of on-prem will save the deployment.

```pwsh
# 1. Authenticate
az login --tenant <your-tenant-id>
az account set --subscription <your-subscription-id>

# 2. Sanity-check the Foundry resource and your RBAC on it
$FoundryName  = "<your-foundry-name>"
$ResourceGroup = "<your-rg>"
az cognitiveservices account show `
    --name $FoundryName --resource-group $ResourceGroup `
    --query "{name:name, kind:kind, sku:sku.name, location:location, endpoint:properties.endpoint}" `
    -o table

# 3. Capture the endpoint you'll use in .env
$endpoint = az cognitiveservices account show `
    --name $FoundryName --resource-group $ResourceGroup `
    --query "properties.endpoints['Azure AI Voice Live']" -o tsv
"AZURE_AI_ENDPOINT=$endpoint"
```

Validation gate — the endpoint URL must look like
`https://<foundry-name>.services.ai.azure.com` (Foundry's AI Services surface),
**not** the legacy `*.cognitiveservices.azure.com` form. If the query above
returns nothing, your resource may be missing the AI Services kind — confirm
with `--query kind` (must be `AIServices`).

Verify the model you plan to use is supported in the region by reviewing
[`08-model-selection.md`](./08-model-selection.md). The default `gpt-realtime`
is built-in to Voice Live — no separate deployment needed unless you choose to
use BYOM.

---

## Part B — Run the app cloud-only on your dev box

Goal: confirm the unchanged cloud path before any hybrid plumbing is enabled.

```pwsh
git clone <your-repo-url>
cd ai-tts-avatar
git checkout feature/hybrid-local-fallback   # or main once merged

python -m venv venv
. .\venv\Scripts\Activate.ps1
pip install -r requirements.txt

# Minimum .env for cloud-only
Copy-Item .env.example .env
# Edit .env — set AZURE_AI_ENDPOINT to the value from Part A.
# Leave ENABLE_LOCAL_FALLBACK=false.

az login   # so DefaultAzureCredential can pick up the token
python app.py
```

Open <http://localhost:8000>, click **Start Avatar**, verify the avatar
appears and audio plays. Status bar shows the existing dot, no mode badge.

Validation gate — `/api/health` returns `{"status":"ok"}` and `/api/hybrid/status`
returns `enableLocalFallback: false, supervisor: null`. If either is wrong, stop
and re-check `.env` before continuing.

---

## Part C — Provision the on-prem edge host

Goal: a Linux or Windows host with Docker (or Podman), the Foundry resource key
on hand, and outbound HTTPS to MCR.

See [`03-onprem-setup.md`](./03-onprem-setup.md) for the full procedure. The
essential pre-flight:

```bash
# Linux example
sudo apt-get update && sudo apt-get install -y docker.io docker-compose-plugin
sudo usermod -aG docker $USER       # log out and back in
docker info && docker compose version

# Confirm the Foundry endpoint and key the containers will use for metering
echo "SPEECH_BILLING=https://<your-foundry-name>.cognitiveservices.azure.com/" > .env
echo "SPEECH_API_KEY=<key-from-Foundry-portal-Keys-and-Endpoint>"             >> .env
```

> The key is taken from the Foundry resource portal page "Keys and Endpoint".
> Either KEY1 or KEY2 works; rotate via the portal.

---

## Part D — Start the on-prem stack

```bash
# From the repo root on the edge host
docker compose -f docker-compose.local.yml pull       # ~6 GB on first pull
docker compose -f docker-compose.local.yml up -d
docker compose -f docker-compose.local.yml ps          # both services Up
```

Validate both containers (commands from [`03-onprem-setup.md §2`](./03-onprem-setup.md#2-connected-mode-recommended-for-first-run)):

```bash
# STT health
curl -sS -X POST \
  "http://localhost:5001/speech/recognition/conversation/cognitiveservices/v1?language=en-US" \
  -H "Content-Type: audio/wav; codecs=audio/pcm; samplerate=16000" \
  --data-binary "@/dev/null" | head -c 200 ; echo

# NTTS synth → WAV
curl -sS -X POST "http://localhost:5002/cognitiveservices/v1" \
  -H "Content-Type: application/ssml+xml" \
  -H "X-Microsoft-OutputFormat: riff-24khz-16bit-mono-pcm" \
  -H "User-Agent: setup-test" \
  -o /tmp/hello.wav \
  --data '<speak version="1.0" xml:lang="en-US"><voice name="en-US-JennyNeural">Hello.</voice></speak>'
file /tmp/hello.wav
```

Install Foundry Local + a chat-completion model — see
[`03-onprem-setup.md §4`](./03-onprem-setup.md#4-install-and-warm-foundry-local)
for the per-OS commands. For most sites, default to **`qwen2.5-7b-instruct`**
or **`phi-4`** — neither is a realtime model (no on-prem equivalent of
`gpt-realtime` exists today), they are chat-completion stand-ins (see
[`08-model-selection.md`](./08-model-selection.md)).

Validation gate — `curl http://localhost:5273/v1/models` lists the model you
downloaded, and a 1-shot `chat/completions` call returns text in under ~3 s.

---

## Part E — Enable hybrid in the app and verify failover

On the same host that will serve users (typically the edge box), edit the
app's `.env`:

```env
AZURE_AI_ENDPOINT=https://<your-foundry-name>.services.ai.azure.com

# Cloud Voice Live model — pick one of the supported gpt-realtime family.
# See docs/hybrid/08-model-selection.md for the full list and trade-offs.
VOICE_LIVE_MODEL=gpt-realtime          # or gpt-realtime-2, gpt-realtime-1.5

# Hybrid local-fallback
ENABLE_LOCAL_FALLBACK=true
LOCAL_STT_ENDPOINT=http://localhost:5001
LOCAL_TTS_ENDPOINT=http://localhost:5002
LOCAL_TTS_VOICE=en-US-JennyNeural       # must match the NTTS container tag
LOCAL_LLM_ENDPOINT=http://localhost:5273/v1
LOCAL_LLM_MODEL=qwen2.5-7b-instruct     # must match what Foundry Local serves
```

Restart the app and verify both modes:

```pwsh
python app.py
# Cloud mode test: open the browser, click Start Avatar — badge is blue CLOUD.
# Local mode test: stop the app, set FORCE_LOCAL_MODE=true, restart — badge is orange LOCAL.
```

Run the full test matrix in [`05-testing.md`](./05-testing.md) (T1 → T10).
Every row must pass before declaring the deployment done.

Validation gate — `/api/hybrid/status` shows:

```json
{
  "enableLocalFallback": true,
  "supervisor": { "reachable": true, ... },
  "localStack": { "stt":"http://localhost:5001", "tts":"...", "llm":"...", "voice":"...", "model":"..." },
  "missingLocalConfig": []
}
```

If `missingLocalConfig` is non-empty, fix those env vars before proceeding.

---

## Part F — Production hardening (recommended)

Once both modes work end-to-end:

1. **Pin image tags** in `docker-compose.local.yml` (already done in the
   default file — never replace with `:latest` for prod).
2. **Run the app as a service** (systemd unit on Linux, NSSM on Windows) so
   it restarts on boot.
3. **Route logs** to your SIEM. The STT container logs include recognized
   text — decide whether that's acceptable or whether to redact.
4. **Switch container metering to disconnected** if the site is
   offline-tolerant: follow [`03-onprem-setup.md §3`](./03-onprem-setup.md#3-disconnected-mode-offline-tolerant-deployments).
   You need Microsoft approval (~10 business days) and a commitment-tier SKU.
5. **Schedule license re-download** (~ every 30 days) for disconnected
   containers.
6. **Tune VAD** for the actual site acoustic environment — see
   [`04-app-configuration.md §4`](./04-app-configuration.md#4-voice-activity-detection-local-mode-only).
7. **Decide identity** — for dev boxes `az login` is fine; for prod use a
   managed identity or a service principal whose creds the app picks up via
   `DefaultAzureCredential`.

---

## Quick reference — what runs where

A condensed view of [`07-azure-vs-onprem.md`](./07-azure-vs-onprem.md):

| Component | Cloud mode | Local-fallback mode |
|---|---|---|
| WebSocket / chat UI | App (anywhere) | App (anywhere) |
| Orchestration | Azure Voice Live | App (`LocalSessionHandler`) |
| LLM | `gpt-realtime` family in Azure | Foundry Local (chat completion) |
| STT | Voice Live built-in (`azure-speech`) | Local Speech STT container |
| TTS | Voice Live built-in (HD or standard) | Local NTTS container (standard only) |
| Avatar | Azure Avatar Service via WebRTC | **Not available** |
| Semantic VAD / AEC / NS | Voice Live built-in | Energy-based VAD only |
| Function calling | Voice Live tools | **Not in MVP** |

---

## Sign-off checklist

- [ ] Part A: cloud endpoint resolved, RBAC confirmed, region supports your chosen feature set.
- [ ] Part B: cloud-only path works on a dev box.
- [ ] Part C: edge host meets the prereqs.
- [ ] Part D: both containers respond to curl probes; Foundry Local serves the chat model.
- [ ] Part E: app boots with `ENABLE_LOCAL_FALLBACK=true`; cloud and local sessions both succeed.
- [ ] Part F: prod hardening applied (service auto-start, logs, license posture decided).
- [ ] [`05-testing.md`](./05-testing.md) matrix T1–T10 all pass.
