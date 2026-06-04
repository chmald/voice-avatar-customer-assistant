# Azure AI Voice Live API with Avatar

Real-time AI voice assistant with an optional lifelike avatar, powered by [Azure Voice Live API](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live-how-to).

![Python](https://img.shields.io/badge/Python-FastAPI-009688?logo=fastapi&logoColor=white)
![Azure](https://img.shields.io/badge/Azure-Voice%20Live-0078D4?logo=microsoftazure&logoColor=white)

## Features

- **Avatar mode** — WebRTC-streamed photorealistic avatar (Lisa, Harry, Max, Lori)
- **Voice-only mode** — Same AI conversation without the avatar video
- **Voice input** — Mic capture at 24 kHz via AudioWorklet, noise/echo cancellation server-side
- **Text input** — Type messages for the AI to respond to
- **Multiple voices** — Azure standard + HD (Dragon) voices
- **Proactive greeting** — The assistant speaks first when a session starts
- **BYOM (Bring Your Own Model)** — Point at a custom Foundry deployment (Azure OpenAI realtime / chat completion / Anthropic Claude)
- **Hybrid local fallback (preview)** — When the cloud is unreachable, sessions automatically continue on-prem against Speech containers + Foundry Local. See [`docs/hybrid/`](./docs/hybrid/).
- **Optional weather tool** — Function-calling demo using browser geolocation
- **DefaultAzureCredential** — Keyless auth via Azure CLI or managed identity

## Architecture

```
Browser ←WebSocket→ FastAPI backend ←SDK→ Azure Voice Live API
                                              ↕ (avatar mode)
Browser ←─── WebRTC video/audio ───── Azure Avatar Service
```

| File | Purpose |
|---|---|
| `app.py` | FastAPI server, WebSocket message router, session management, hybrid routing |
| `voice_handler.py` | Back-compat shim — re-exports `CloudVoiceLiveSessionHandler` as `VoiceSessionHandler` |
| `session_handlers/` | `SessionHandler` protocol + cloud and local implementations |
| `local_clients/` | Async clients for the on-prem Speech containers and Foundry Local |
| `connectivity.py` | Background supervisor that probes the cloud Voice Live endpoint |
| `config.py` | Settings from environment variables |
| `static/js/app.js` | Browser client — WebRTC, mic capture, audio playback, UI, mode badge |
| `static/js/audio-processor.js` | AudioWorklet for 24 kHz PCM16 mic capture |
| `templates/index.html` | Single-page UI (Jinja2 template) |
| `static/css/style.css` | Dark-theme application styles |
| `docker-compose.local.yml` | On-prem Speech STT + NTTS containers for the hybrid path |
| `docs/` | Standard project docs (6-doc layout): orchestrator, architecture, prerequisites, deployment, testing, troubleshooting |
| `docs/hybrid/` | Hybrid-path supplements: customer report, implementation plan, Azure-vs-on-prem responsibility, model selection |

## Prerequisites

| Requirement | Details |
|---|---|
| Python | 3.10+ |
| Azure subscription | [Free account](https://azure.microsoft.com/free/) |
| Microsoft Foundry resource | In a [supported region](https://learn.microsoft.com/azure/ai-services/speech-service/regions?tabs=ttsavatar) |
| Azure CLI | For `az login` authentication |
| RBAC roles | **Cognitive Services User** + **Azure AI User** on your Foundry resource |

## Support matrix

This project depends on three Azure capabilities, each with its own regional footprint. **Your Foundry resource must be created in a region that supports every feature you plan to use.** Pick a region from the recommendations below based on which features you enable.

### Feature → requirement

| Feature in this app | Azure capability | Required? |
|---|---|---|
| Voice-only conversation | Voice Live API (built-in `gpt-realtime`) | Always |
| Avatar video (Lisa, Harry, Max, Lori, Meg, etc.) | TTS Real-time Avatar | When **Enable Avatar** is on |
| HD (Dragon) voices — e.g. `en-US-Ava:DragonHDLatestNeural` | Azure Neural HD voices | When selecting an `HD` voice |
| Standard / Multilingual voices | Azure Neural TTS (broad coverage) | When selecting a non-HD voice |
| BYOM (`byom-azure-openai-realtime`, `…-chat-completion`) | Azure OpenAI deployment in your Foundry resource | When `ENABLE_BYOM_MODE=true` |
| BYOM (`byom-foundry-anthropic-messages`) | Anthropic model on Foundry (preview) | When using Claude via BYOM |
| Weather tool | Open-Meteo (keyless, no region) | When `ENABLE_WEATHER_TOOL=true` |

### Region × feature matrix

✅ = supported · ❌ = not supported · ⚠️ = check docs (changes frequently)

| Region | Voice Live API | TTS Avatar (real-time) | HD (Dragon) voices | Standard / Multilingual TTS |
|---|:---:|:---:|:---:|:---:|
| `eastus`           | ⚠️ | ❌ | ✅ | ✅ |
| `eastus2`          | ✅ | ✅ | ✅ | ✅ |
| `westus2`          | ✅ | ✅ | ✅ | ✅ |
| `southcentralus`   | ⚠️ | ✅ | ❌ | ✅ |
| `northeurope`      | ⚠️ | ✅ | ❌ | ✅ |
| `westeurope`       | ✅ | ✅ | ✅ | ✅ |
| `swedencentral`    | ✅ | ✅ | ✅ | ✅ |
| `southeastasia`    | ✅ | ✅ | ✅ | ✅ |
| `centralindia`     | ✅ | ❌ | ✅ | ✅ |
| All other Speech regions | ❌ | ❌ | ❌ | ✅ |

Sources (authoritative — verify before deploying):
- [Azure Speech regions — Voice Live tab](https://learn.microsoft.com/azure/ai-services/speech-service/regions?tabs=voicelive)
- [Azure Speech regions — TTS Avatar tab](https://learn.microsoft.com/azure/ai-services/speech-service/regions?tabs=ttsavatar)
- [HD voice region availability](https://learn.microsoft.com/azure/ai-services/speech-service/language-support?tabs=tts)
- [Voice Live overview & supported models](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live)

### Recommended deployments

| Scenario | Recommended regions | Why |
|---|---|---|
| **Full featured** (avatar + HD voices + Voice Live) | `eastus2`, `westus2`, `westeurope`, `swedencentral`, `southeastasia` | Only regions that support all three at once |
| **Voice-only, HD voices** | Any of the above, plus `eastus`, `centralindia` | HD voices without avatar |
| **Voice-only, no HD** | Any Voice Live region | Lowest cost / broadest availability |
| **EU data residency** | `westeurope`, `swedencentral`, `northeurope` | Data stays in EU geography |
| **APAC** | `southeastasia` | Only APAC region with full feature parity |

> Data residency: Azure Speech doesn't process or store your audio outside the region of your Foundry resource — pick a region that matches your compliance needs.

## Quick Start

> **First time deploying this demo?** Follow the full step-by-step guide in
> **[`docs/00-reproduce-this-demo.md`](./docs/00-reproduce-this-demo.md)** — it
> covers prerequisites, provisioning the Azure Foundry resource with `az`,
> RBAC, validation tests at each step, and the optional hybrid on-prem
> fallback path. The phased deployment reference lives in
> [`docs/03-deployment.md`](./docs/03-deployment.md). The condensed version
> below assumes you already have a Foundry resource and tools installed.

```bash
# Clone and install
git clone <your-repo-url>
cd ai-voice-live-avatar
python -m venv venv
source venv/bin/activate      # macOS/Linux
# venv\Scripts\activate       # Windows
pip install -r requirements.txt

# Configure
cp .env.example .env
# Edit .env with your endpoint

# Authenticate
az login

# Run
python app.py
```

Open **http://localhost:8000** in Chrome or Edge.

## Configuration

Edit `.env` (copy from `.env.example`):

```env
# Required
AZURE_AI_ENDPOINT=https://your-resource.services.ai.azure.com

# Model served by Voice Live (default: gpt-realtime)
VOICE_LIVE_MODEL=gpt-realtime

# Server port (default: 8000)
PORT=8000
```

### Optional: Bring Your Own Model (BYOM)

Use a custom model deployment from your Foundry resource instead of the built-in `VOICE_LIVE_MODEL`.
See the [BYOM docs](https://learn.microsoft.com/azure/ai-services/speech-service/how-to-bring-your-own-model) for full details.

```env
ENABLE_BYOM_MODE=true
# Profile — pick one to match your deployment type:
#   byom-azure-openai-realtime         (e.g. gpt-realtime, gpt-realtime-mini)
#   byom-azure-openai-chat-completion  (e.g. gpt-5, gpt-4.1, model router)
#   byom-foundry-anthropic-messages    (e.g. claude-sonnet-4.6) — preview
VOICE_BYOM_MODE=byom-azure-openai-realtime

# Deployment NAME from the Foundry portal (not the underlying model id)
VOICE_BYOM_MODEL=my-gpt-realtime-deployment

# Optional: target a deployment in a DIFFERENT Foundry resource.
# Resource name only — no domain. e.g. "my-other-foundry"
VOICE_BYOM_FOUNDRY_RESOURCE_OVERRIDE=
```

When BYOM is enabled, `VOICE_BYOM_MODEL` becomes the `model` query param and `VOICE_LIVE_MODEL` is ignored. The connection URL gets `profile=<VOICE_BYOM_MODE>` (and optionally `foundry-resource-override=<...>`) appended.

**Cross-resource note:** if you set `VOICE_BYOM_FOUNDRY_RESOURCE_OVERRIDE`, the Voice Live Foundry resource needs its system-assigned managed identity granted the **Foundry User** role on the *model's* Foundry resource. See the docs above for the exact `az` commands.

### Optional: Weather tool

Set `ENABLE_WEATHER_TOOL=true` to expose a `get_weather` function the model can call. Uses the browser's geolocation when the user says "near me".

### Optional: Hybrid local fallback (preview)

When sites have intermittent internet, the app can automatically fall back to a
fully on-prem pipeline (Speech containers + Foundry Local) on a per-session basis.
Cloud is always preferred when reachable; local mode is voice-only (no avatar,
no HD voices) and is signalled to the user with an orange `LOCAL` badge.

```env
ENABLE_LOCAL_FALLBACK=true
LOCAL_STT_ENDPOINT=http://localhost:5001
LOCAL_TTS_ENDPOINT=http://localhost:5002
LOCAL_TTS_VOICE=en-US-JennyNeural
LOCAL_LLM_ENDPOINT=http://localhost:5273/v1
LOCAL_LLM_MODEL=qwen2.5-7b-instruct
```

Full reference and on-prem setup steps live in the standard project docs
(see [`docs/`](./docs/)). The hybrid-specific supplements live in
[`docs/hybrid/`](./docs/hybrid/):

| Doc | Purpose |
|---|---|
| [`docs/00-reproduce-this-demo.md`](./docs/00-reproduce-this-demo.md) | **Single-page orchestrator** — start here for first-time stand-up |
| [`docs/01-architecture.md`](./docs/01-architecture.md) | Full app architecture (cloud + hybrid), Mermaid diagram, locked decisions |
| [`docs/02-prerequisites.md`](./docs/02-prerequisites.md) | Azure + on-prem prerequisites, regional matrix, cost estimate, pre-flight checklist |
| [`docs/03-deployment.md`](./docs/03-deployment.md) | Phased deployment with validation gates (Phase 1–5) |
| [`docs/04-testing.md`](./docs/04-testing.md) | Functional tests + hybrid matrix + demo script + performance baselines |
| [`docs/05-troubleshooting.md`](./docs/05-troubleshooting.md) | Quick-triage table + per-symptom diagnosis + escalation |
| [`docs/hybrid/customer-report.md`](./docs/hybrid/customer-report.md) | Comparative report — three approaches, what stays in Azure, decision checklist |
| [`docs/hybrid/implementation-plan.md`](./docs/hybrid/implementation-plan.md) | MVP scope, file map, milestones, out-of-scope items |
| [`docs/hybrid/azure-vs-onprem-responsibility.md`](./docs/hybrid/azure-vs-onprem-responsibility.md) | Per-component responsibility matrix, network egress rules, data-flow diagrams |
| [`docs/hybrid/model-selection.md`](./docs/hybrid/model-selection.md) | Voice Live model list (`gpt-realtime`, `gpt-realtime-2`, `gpt-realtime-1.5`, `…-mini`), BYOM profiles, local LLM substitutes, parity table |

## Usage

1. Select avatar character, style, and voice in the sidebar
2. Toggle **Enable Avatar** on/off (off = voice-only mode for faster testing)
3. Click **Start Avatar** to connect
4. Type a message or click the mic to speak
5. The AI responds through the avatar (or audio only)

## When to use this app

### Use this app when

- You want a production-style real-time voice + avatar experience built on Azure AI Voice Live and the `gpt-realtime` family.
- You need a working reference for the Voice Live + TTS Avatar + neural-voice integration in a single FastAPI + browser pair.
- You want BYOM (private / fine-tuned Azure OpenAI realtime or chat-completion deployments) wired up without writing the connection plumbing yourself.
- You have sites with intermittent internet and need a **graceful degradation** path — the hybrid local-fallback mode delivers a voice-only conversation on-prem using Azure Speech containers + Foundry Local when the cloud is unreachable.

### Use a different pattern when

- You need a **knowledge-base / RAG** experience over a document corpus → use the low-code RAG knowledge-base pattern (Copilot Studio + Azure AI Search) instead.
- You need **multi-agent orchestration or custom tool-calling logic** beyond a single function tool → add Foundry Agent Service as an orchestration layer above this app, or use a different pattern entirely.
- You need a **fully air-gapped** experience with zero cloud dependency. Voice Live, the TTS Avatar, the `gpt-realtime` family, and HD voices are all Azure-only — no on-prem equivalent exists. The hybrid mode degrades gracefully but is not the same UX.

## Troubleshooting

A short list — the full quick-triage table + per-symptom diagnoses live in
[`docs/05-troubleshooting.md`](./docs/05-troubleshooting.md).

| Issue | Solution |
|---|---|
| Session error on connect | Check `AZURE_AI_ENDPOINT` in `.env`; run `az login` |
| Avatar fails, voice works | Ensure region supports TTS avatar; try voice-only first |
| No audio/video | Allow mic/camera in browser; use Chrome or Edge |
| Stale JS behavior | Hard refresh (Ctrl+Shift+R) — no-cache middleware should handle this |
| BYOM connect fails | Verify `VOICE_BYOM_MODEL` matches a real **deployment name** in the Foundry portal, and that the deployment's profile matches `VOICE_BYOM_MODE` |
| BYOM 401/403 with override | When using `VOICE_BYOM_FOUNDRY_RESOURCE_OVERRIDE`, grant the Voice Live resource's managed identity **Foundry User** on the model resource |

## Decision provenance

| Decision area | Where it's recorded |
|---|---|
| Cloud orchestrator = Voice Live; model = `gpt-realtime` family | [`docs/01-architecture.md` §Locked design decisions](./docs/01-architecture.md#locked-design-decisions) |
| Hybrid Approach A (cloud-primary + voice-only fallback) chosen over Approaches B (local-first) and C (tools-only) | [`docs/hybrid/customer-report.md`](./docs/hybrid/customer-report.md) |
| MVP engineering scope + explicit out-of-scope items | [`docs/hybrid/implementation-plan.md`](./docs/hybrid/implementation-plan.md) |
| Per-component Azure-vs-on-prem split (what must stay Azure, what can move) | [`docs/hybrid/azure-vs-onprem-responsibility.md`](./docs/hybrid/azure-vs-onprem-responsibility.md) |
| Voice Live model choice + BYOM profile guidance + local LLM substitutes | [`docs/hybrid/model-selection.md`](./docs/hybrid/model-selection.md) |

## License

MIT

---

*Last updated: 2026-06-04*
