# 00 — Reproduce this demo

> **Audience.** Someone with zero context who wants to run the AI TTS Avatar
> demo end-to-end. By the time you finish this guide you will have a working
> avatar in your browser, optionally backed by an on-prem fallback pipeline.
>
> **What this doc is.** A single-page orchestrator that threads the install
> steps, the phased Azure provisioning in [`03-deployment.md`](./03-deployment.md),
> the validation matrix in [`04-testing.md`](./04-testing.md), and the
> troubleshooting matrix in [`05-troubleshooting.md`](./05-troubleshooting.md).
> Read this if you want one continuous walkthrough; read the numbered docs
> if you want the canonical phased / reference content.
>
> **Time budget.** Cloud-only demo: **30–45 minutes** including Azure
> provisioning. Add the hybrid on-prem fallback path: **+90–120 minutes**
> (container pulls + Foundry Local install + model download).
>
> All shell snippets are PowerShell (`pwsh`). They work unchanged on
> Windows, macOS, and Linux — `pwsh` 7+ is cross-platform. If you prefer
> `bash`, convert `$VAR = "value"` → `VAR=value` and backtick → `\`.

---

## What you'll end up with

```
┌─────────────────────────────────────────────────────────────────────┐
│ Your machine                                                        │
│   Browser  →  http://localhost:8000  ──┐                            │
│                                         │                           │
│   python app.py  (FastAPI on :8000) ────┤                           │
│                                         ▼                           │
│                                Azure Microsoft Foundry resource     │
│                                  ├─ Voice Live API (gpt-realtime)   │
│                                  ├─ TTS Avatar Service (WebRTC)     │
│                                  └─ HD voices, semantic VAD, AEC    │
│                                                                     │
│   (Optional)  Speech STT + NTTS containers + Foundry Local          │
│               for offline-tolerant deployments                      │
└─────────────────────────────────────────────────────────────────────┘
```

---

## Decide your scope first

Pick one before starting:

| Scope | What works | What you need | Time |
|---|---|---|---|
| **A. Cloud-only demo** | Full avatar, HD voices, semantic VAD, function calling. Requires a stable internet connection. | An Azure subscription. | 30–45 min |
| **B. Cloud + hybrid fallback** | Everything in A, **plus** voice-only fallback when the cloud is unreachable. | All of A + a powerful Linux/Windows box for the containers + Microsoft approval (only if you want true offline mode). | A + 90–120 min |

This document walks Scope A in Steps 1–7. Step 8 is the optional add-on for Scope B.

---

## Step 1 — Install local prerequisites

You need four tools on your laptop.

### 1.1 Python 3.10 or newer

```pwsh
# Check first
python --version
# → Python 3.10.x or newer

# Windows (winget)
winget install Python.Python.3.12

# macOS (brew)
brew install python@3.12

# Ubuntu / Debian
sudo apt-get install -y python3.12 python3.12-venv python3-pip
```

### 1.2 Azure CLI 2.60 or newer

```pwsh
az --version
# az-cli >= 2.60 required

# Windows
winget install Microsoft.AzureCLI

# macOS
brew install azure-cli

# Linux
curl -sL https://aka.ms/InstallAzureCLIDeb | sudo bash
```

### 1.3 Git

```pwsh
git --version

# Windows
winget install Git.Git

# macOS (preinstalled, or)
brew install git

# Linux
sudo apt-get install -y git
```

### 1.4 PowerShell 7+ (only if you're on macOS or Linux — Windows already has it)

```bash
# macOS
brew install --cask powershell

# Linux (Ubuntu)
sudo snap install powershell --classic
```

### 1.5 A modern browser

Chrome 120+ or Edge 120+. The avatar uses WebRTC + AudioWorklet and is not
tested on Firefox or Safari.

### Validation gate ✅

```pwsh
python --version    # Python 3.10+
az --version        # azure-cli >= 2.60
git --version       # any recent version
pwsh --version      # 7.x
```

If any line fails, install the missing tool before continuing.

---

## Step 2 — Provision an Azure Microsoft Foundry resource

You need a Foundry resource (`kind=AIServices`) in a region that supports
Voice Live, TTS Avatar, and HD voices. The safest choices for full feature
parity are `eastus2`, `westus2`, `westeurope`, `swedencentral`, or
`southeastasia` — see the regional matrix in [`README.md`](../README.md).

```pwsh
# 1. Sign in
az login
az account show -o table          # verify the right tenant + subscription
# If you have multiple subscriptions, set the right one:
# az account set --subscription "<subscription-name-or-id>"

# 2. Variables (customize these)
$Sub        = az account show --query id -o tsv
$Region     = "eastus2"
$RgName     = "rg-ai-tts-avatar-demo"
$FoundryName = "aif-ttsdemo-$(Get-Random -Maximum 9999)"

# 3. Resource group
az group create --name $RgName --location $Region -o table

# 4. Foundry resource (a unified Azure AI Services account)
az cognitiveservices account create `
    --name $FoundryName `
    --resource-group $RgName `
    --location $Region `
    --kind AIServices `
    --sku S0 `
    --custom-domain $FoundryName `
    --assign-identity `
    --yes -o table

# 5. Capture the endpoint you'll put in .env
$endpoint = "https://$FoundryName.services.ai.azure.com"
"AZURE_AI_ENDPOINT=$endpoint"
```

> The Voice Live built-in model (`gpt-realtime` and friends) is served
> directly by Voice Live — **you do not need to deploy any model in
> Foundry**. The only time you do is when you want a private / fine-tuned
> deployment via BYOM (see [`hybrid/model-selection.md`](./hybrid/model-selection.md)).

### Validation gate ✅

```pwsh
# Endpoint resolves
curl.exe -sS -I $endpoint | Select-Object -First 1
# → HTTP/1.1 200 Service Operational  (or 401/404 — anything but a transport error)

# Resource shows kind=AIServices and the right region
az cognitiveservices account show --name $FoundryName --resource-group $RgName `
    --query "{name:name, kind:kind, location:location, sku:sku.name}" -o table
```

---

## Step 3 — Grant yourself the right RBAC roles

The app authenticates with `DefaultAzureCredential` — i.e. it will use your
`az login` token. Your user account needs two role assignments on the
Foundry resource: **Cognitive Services User** + **Azure AI User**.

```pwsh
$Me = az ad signed-in-user show --query id -o tsv
$Scope = az cognitiveservices account show `
    --name $FoundryName --resource-group $RgName --query id -o tsv

az role assignment create --assignee-object-id $Me `
    --assignee-principal-type User `
    --role "Cognitive Services User" --scope $Scope -o table

az role assignment create --assignee-object-id $Me `
    --assignee-principal-type User `
    --role "Azure AI User" --scope $Scope -o table
```

### Validation gate ✅

```pwsh
az role assignment list --assignee $Me --scope $Scope `
    --query "[].roleDefinitionName" -o tsv
# Expect both:
#   Cognitive Services User
#   Azure AI User
```

Role propagation can take **up to 5 minutes**. If the next step fails with
an auth error, wait and retry.

---

## Step 4 — Clone the repo and install Python deps

```pwsh
git clone <your-repo-url> ai-tts-avatar
cd ai-tts-avatar
git checkout main             # or feature/hybrid-local-fallback for Scope B

python -m venv .venv
. .\.venv\Scripts\Activate.ps1          # macOS/Linux: . ./.venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements.txt
```

### Validation gate ✅

```pwsh
python -c "import config, voice_handler; print('OK,', voice_handler.VoiceSessionHandler.__name__)"
# → OK, CloudVoiceLiveSessionHandler
```

---

## Step 5 — Configure `.env`

```pwsh
Copy-Item .env.example .env
notepad .env                  # or: code .env
```

Edit just two lines for Scope A (everything else is fine at defaults):

```env
AZURE_AI_ENDPOINT=https://aif-ttsdemo-1234.services.ai.azure.com   # from Step 2
VOICE_LIVE_MODEL=gpt-realtime                                       # or gpt-realtime-2 / gpt-realtime-1.5
```

The `gpt-realtime` family is built into Voice Live — no Foundry deployment
required. See [`hybrid/model-selection.md`](./hybrid/model-selection.md)
for the full list (including `gpt-realtime-mini`).

### Validation gate ✅

```pwsh
python -c "from config import settings; print('Missing:', settings.validate(), 'Endpoint:', settings.AZURE_AI_ENDPOINT); print('Model:', settings.VOICE_LIVE_MODEL)"
# → Missing: []  Endpoint: https://...services.ai.azure.com  Model: gpt-realtime
```

If `Missing` is non-empty, fix `.env` before moving on.

---

## Step 6 — Run the cloud-only demo

```pwsh
# Make sure your az session is still active
az account show -o table

# Boot the app
python app.py
# → Uvicorn running on http://0.0.0.0:8000
```

In a second terminal, smoke-check the HTTP surface:

```pwsh
curl.exe -sS http://localhost:8000/api/health
# → {"status":"ok","missing_keys":[]}

curl.exe -sS http://localhost:8000/api/avatars | python -m json.tool | Select-Object -First 8
# Should list video + photo avatar characters
```

Now open the browser:

1. Navigate to **http://localhost:8000**.
2. Pick **Character** = `Lisa`, **Style** = `casual-sitting`, **Voice** = `Ava HD (US, F)` (default).
3. Make sure **Enable Avatar** is checked.
4. Click **Start Avatar**.
5. Within 5–10 seconds Lisa should appear and greet you.
6. Click the microphone button and ask "What can you do?" — she should respond.

### Validation gate ✅ (this IS the demo)

- [ ] Status dot turns green ("Connected").
- [ ] Avatar video plays.
- [ ] Greeting audio plays from your speakers.
- [ ] Mic icon turns red when you click it; your speech is transcribed in the chat panel.
- [ ] Assistant replies with both text + audio.

If any of these fail, jump to [Troubleshooting](#troubleshooting) below.

---

## Step 7 — Try voice-only and a few extras

| Try this | Why |
|---|---|
| Uncheck **Enable Avatar** before Start Avatar | Voice-only mode — same conversation without the WebRTC video. Faster to start. |
| Change **Voice** to `Ada HD (UK, F)` and restart | Verify HD voice swap works. |
| Change **Voice** to `Jenny (US, F)` (a standard neural) and restart | Verify non-HD voice works (this is the voice the hybrid local mode also uses). |
| Set `ENABLE_WEATHER_TOOL=true` in `.env`, restart, ask "What's the weather like in Seattle?" | Function-calling demo. Browser will prompt for geolocation if you say "near me". |
| Set `VOICE_LIVE_MODEL=gpt-realtime-2`, restart | Switch to the latest preview realtime model (verify it's available in your region). |

If you only need the cloud demo, **you're done**. Skip to
[Cleanup](#cleanup) when you're ready to tear down the Azure resource.

---

## Step 8 — (Optional) Add the hybrid local-fallback path

This is the on-prem half of the demo. It only adds value if:

- The site running the app has unreliable internet, **or**
- You want to demonstrate a voice-only conversation with no Azure round-trip,
  **or**
- You're scoping a production deployment that needs offline-tolerance.

You'll add three on-prem components (Speech STT container, NTTS container,
Foundry Local LLM) and a routing layer so the app falls back to them when the
cloud is unreachable.

### 8.1 Switch to the hybrid branch and re-install

```pwsh
git fetch
git checkout feature/hybrid-local-fallback
pip install -r requirements.txt        # adds the `openai` SDK for Foundry Local
```

### 8.2 Prepare the edge host

Use a Linux server (Ubuntu 22.04+ recommended) or Windows 11 / Server 2025
with these minimums:

- 16+ vCPU, 32+ GB RAM
- 200+ GB SSD
- NVIDIA GPU with 16+ GB VRAM **strongly recommended** for snappy local-LLM
  replies (CPU-only works but the local mode will feel slow)
- Docker Engine 24+ or Podman 4+
- Outbound HTTPS to `mcr.microsoft.com`, `*.cognitiveservices.azure.com`,
  `login.microsoftonline.com`

For a smoke-test you can run everything on the same machine you're using
for development. For production deploy the app + containers + Foundry Local
on the same edge host so the local hops are loopback.

### 8.3 Start the Speech containers

```pwsh
# In the repo root on the edge host
$env:SPEECH_BILLING = "https://$FoundryName.cognitiveservices.azure.com/"
$env:SPEECH_API_KEY = az cognitiveservices account keys list `
    --name $FoundryName --resource-group $RgName --query key1 -o tsv

docker compose -f docker-compose.local.yml pull        # ~6 GB first time
docker compose -f docker-compose.local.yml up -d
docker compose -f docker-compose.local.yml ps          # both Up
```

Validate both:

```bash
# STT — empty request returns an error envelope, which proves routing works
curl -sS -X POST \
  "http://localhost:5001/speech/recognition/conversation/cognitiveservices/v1?language=en-US" \
  -H "Content-Type: audio/wav; codecs=audio/pcm; samplerate=16000" \
  --data-binary "@/dev/null" | head -c 200 ; echo

# NTTS — synthesize "Hello" to a WAV
curl -sS -X POST "http://localhost:5002/cognitiveservices/v1" \
  -H "Content-Type: application/ssml+xml" \
  -H "X-Microsoft-OutputFormat: riff-24khz-16bit-mono-pcm" \
  -H "User-Agent: setup-test" \
  -o /tmp/hello.wav \
  --data '<speak version="1.0" xml:lang="en-US"><voice name="en-US-JennyNeural">Hello from local TTS.</voice></speak>'
file /tmp/hello.wav   # → RIFF (little-endian) data, WAVE audio, ...
```

### 8.4 Install Foundry Local and download a model

```pwsh
# Windows
winget install Microsoft.FoundryLocal
# macOS
# brew install foundrylocal

foundry model download qwen2.5-7b-instruct     # ~5 GB
foundry service start
foundry service status                          # prints port — usually http://localhost:5273
```

Validate:

```pwsh
curl.exe -sS http://localhost:5273/v1/models
curl.exe -sS http://localhost:5273/v1/chat/completions `
    -H 'Content-Type: application/json' `
    -d '{"model":"qwen2.5-7b-instruct","messages":[{"role":"user","content":"Say hi in one short sentence."}],"max_tokens":32}'
```

> **Linux note.** Foundry Local doesn't officially ship for Linux yet. Use
> `vllm serve Qwen/Qwen2.5-7B-Instruct --port 5273 --served-model-name qwen2.5-7b-instruct`
> instead. The app only needs an OpenAI-compatible `/v1/chat/completions` endpoint —
> see [`hybrid/model-selection.md`](./hybrid/model-selection.md).

### 8.5 Enable the hybrid path in `.env`

```env
ENABLE_LOCAL_FALLBACK=true
LOCAL_STT_ENDPOINT=http://localhost:5001
LOCAL_TTS_ENDPOINT=http://localhost:5002
LOCAL_TTS_VOICE=en-US-JennyNeural        # must match the NTTS container tag
LOCAL_LLM_ENDPOINT=http://localhost:5273/v1
LOCAL_LLM_MODEL=qwen2.5-7b-instruct      # must match what Foundry Local serves
```

### 8.6 Restart and verify both modes

```pwsh
python app.py
```

In a second shell:

```pwsh
# Confirm the supervisor is up and the local stack is fully configured
curl.exe -sS http://localhost:8000/api/hybrid/status | python -m json.tool
# → enableLocalFallback: true
#   supervisor.reachable: true   (since cloud is up)
#   localStack.{stt,tts,llm,voice,model}: all populated
#   missingLocalConfig: []
```

Browser tests:

1. **Cloud mode (default).** Start Avatar — the status bar should now show a
   blue **CLOUD** badge next to the dot. Everything works as in Step 6.
2. **Forced local mode.** Stop the app, set `FORCE_LOCAL_MODE=true` in `.env`,
   restart, click Start Avatar. Badge turns orange **LOCAL**; an info banner
   appears under the video; the avatar pane stays hidden (no on-prem avatar
   exists); greeting and conversation flow through the local stack.
3. **Simulated outage.** Stop the app, change `AZURE_AI_ENDPOINT` to a
   bogus host (e.g. `https://does-not-exist.invalid`), unset
   `FORCE_LOCAL_MODE`, restart. After about 30 seconds the supervisor flips
   to `reachable: false` (visible at `/api/hybrid/status`). Starting a new
   session opens in LOCAL mode with the reason `cloud-unreachable: ...` in
   the banner.

### Full hybrid test matrix

The 10-row test plan in [`04-testing.md §3`](./04-testing.md#3-hybrid-test-matrix-phase-4-only)
covers every combination (forced/auto, working/missing config,
barge-in, etc.). Run it once before declaring the hybrid deployment done.

### Deeper hybrid docs

| If you want to | Read |
|---|---|
| Understand the architecture | [`01-architecture.md`](./01-architecture.md) |
| Size hardware for production | [`02-prerequisites.md`](./02-prerequisites.md) |
| Run the containers truly offline (with Microsoft approval) | [`03-deployment.md §5.4`](./03-deployment.md#54-switch-container-metering-to-disconnected-offline-tolerant-sites) |
| Tune VAD or change voices | [`03-deployment.md §5.5`](./03-deployment.md#55-tune-vad-for-the-sites-acoustic-environment) |
| Know exactly what stays in Azure vs on-prem | [`hybrid/azure-vs-onprem-responsibility.md`](./hybrid/azure-vs-onprem-responsibility.md) |
| See the customer-facing report | [`hybrid/customer-report.md`](./hybrid/customer-report.md) |
| Read the engineering plan that produced the hybrid path | [`hybrid/implementation-plan.md`](./hybrid/implementation-plan.md) |

---

## Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| `Missing env vars: AZURE_AI_ENDPOINT` on app start | `.env` not in the repo root, or the line has a typo. The app loads `.env` via `python-dotenv` from the current working directory. |
| Browser stuck on "Connecting…" | Region mismatch (Voice Live not supported there), or `az login` token expired. Re-run `az login` and refresh the browser. |
| `Session error: 403` or `AuthorizationFailed` | Wait 5 minutes for RBAC propagation, or confirm Step 3 ran with **both** role names. |
| Avatar fails but voice works | Region supports Voice Live but not TTS Avatar. Uncheck Enable Avatar for a voice-only demo, or recreate the Foundry resource in `eastus2` / `westus2` / `westeurope` / `swedencentral` / `southeastasia`. |
| No mic permission popup | The browser blocks mic on `http://` for non-localhost hosts. Use `http://localhost:8000` (not `127.0.0.1`) or set up an HTTPS reverse proxy. |
| Audio plays once then stops | The mic captured silence and barge-in killed the playback. Look at the browser console — `speech_started` events without speech indicate the VAD threshold needs tuning (or you're on a noisy line). |
| In Step 8, supervisor stays `reachable: false` after fixing the endpoint | Default probe interval is 15 s — wait, then re-check `/api/hybrid/status`. |
| In Step 8, `missingLocalConfig` lists endpoints that look correct | The empty-string check is exact — make sure your `.env` lines have no trailing whitespace. |
| In Step 8, NTTS returns 404 | The voice short-name in `LOCAL_TTS_VOICE` doesn't match the image tag. Container image `…-en-us-jennyneural` ⇒ voice name `en-US-JennyNeural`. |

---

## Cleanup

Tear down everything when you're done with the demo:

```pwsh
# Local app
# Ctrl-C the running python process.

# (Step 8 only) Stop and remove the on-prem containers + their data
docker compose -f docker-compose.local.yml down -v

# Remove the Azure resource group (deletes the Foundry resource and everything in it)
az group delete --name $RgName --yes --no-wait
```

> The Foundry resource is **soft-deleted** for 30 days after `az group delete`.
> Purge with `az cognitiveservices account purge --location $Region --resource-group $RgName --name $FoundryName` if you need to recreate one with the same name immediately.

---

## Reference

- App overview: [`../README.md`](../README.md)
- Architecture: [`01-architecture.md`](./01-architecture.md)
- Prerequisites: [`02-prerequisites.md`](./02-prerequisites.md)
- Phased deployment: [`03-deployment.md`](./03-deployment.md)
- Testing: [`04-testing.md`](./04-testing.md)
- Troubleshooting: [`05-troubleshooting.md`](./05-troubleshooting.md)
- Hybrid supplements: [`hybrid/`](./hybrid/) (customer report, implementation plan, Azure-vs-on-prem responsibility, model selection)
- Microsoft Learn — Voice Live: <https://learn.microsoft.com/azure/ai-services/speech-service/voice-live>
- Microsoft Learn — TTS Avatar: <https://learn.microsoft.com/azure/ai-services/speech-service/text-to-speech-avatar/what-is-text-to-speech-avatar>
- Microsoft Learn — Speech containers: <https://learn.microsoft.com/azure/ai-services/speech-service/speech-container-overview>
- Microsoft Learn — Foundry Local: <https://learn.microsoft.com/azure/foundry-local/what-is-foundry-local>

---

*Last updated: 2026-06-04*
