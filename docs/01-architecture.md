# 01 — Architecture

> Reference architecture for Azure AI Voice Live API with Avatar. Read
> first, then move to [`02-prerequisites.md`](./02-prerequisites.md).

---

## Goals

- **Real-time voice + avatar UX** built on Azure Voice Live (`gpt-realtime` family) with WebRTC-streamed avatar video.
- **Low-code application surface** — single FastAPI process, single-page browser client, no orchestration code beyond what's needed to bridge browser ↔ Azure.
- **Graceful degradation** — when the cloud is unreachable, sessions can be served by an on-prem pipeline (Speech containers + Foundry Local) without the user losing the chat. Voice-only fallback; avatar disabled.
- **Per-environment configurable** — every endpoint, model, voice, and feature flag lives in `.env`. No code change to swap models, voices, or deployment regions.

---

## Non-goals

- Multi-tenant SaaS (single-instance app — pair with a reverse proxy + auth for production multi-user).
- Structured field extraction or RAG over a document corpus (use the RAG knowledge-base pattern instead).
- Streaming voice / on-prem avatar rendering (no Microsoft on-prem equivalent — see [`hybrid/azure-vs-onprem-responsibility.md`](./hybrid/azure-vs-onprem-responsibility.md)).
- Custom orchestration layers (LangChain, Semantic Kernel agent workflows). The app intentionally treats Voice Live as the orchestrator.

---

## Architecture diagram

```mermaid
flowchart LR
    subgraph Browser["🟦 Browser (Chrome / Edge)"]
        UI[index.html + app.js]
        MIC[(Mic — PCM16 24 kHz)]
        SPK[(Speaker)]
        VID[(Avatar video — cloud only)]
    end

    subgraph App["🟪 FastAPI app (app.py)"]
        WS[/ws/voicelive WebSocket router]
        SUP[ConnectivitySupervisor]
        ROUTE{{Per-session mode decision}}
        CLOUD[CloudVoiceLiveSessionHandler]
        LOCAL[LocalSessionHandler]
    end

    subgraph Cloud["☁️ Azure — Microsoft Foundry resource"]
        VL[Azure AI Voice Live API<br/>gpt-realtime / -1.5 / -2]
        AV[Azure TTS Avatar Service<br/>WebRTC video stream]
        TTS_C[Azure Neural TTS<br/>HD + Standard voices]
    end

    subgraph OnPrem["🏭 On-prem edge host — optional hybrid"]
        STT[Speech-to-Text container]
        LLM[Foundry Local<br/>qwen2.5-7b / phi-4]
        NTTS[Neural-TTS container<br/>standard voices only]
    end

    UI -. WebSocket .- WS
    MIC -. base64 PCM16 .- WS
    WS <--> ROUTE
    ROUTE -.->|reachable| CLOUD
    ROUTE -.->|unreachable / forced| LOCAL
    SUP -- "is_cloud_reachable()" --> ROUTE
    SUP -. periodic HTTPS probe .-> VL

    CLOUD <-->|WebSocket| VL
    VL --- AV
    VL --- TTS_C
    AV <-. WebRTC video+audio .-> VID
    VL -. PCM16 audio frames (voice-only) .-> SPK

    LOCAL -->|WAV| STT
    LOCAL -->|chat/completions| LLM
    LOCAL -->|SSML| NTTS
    LOCAL -. PCM16 audio frames .-> SPK
```

---

## Logical layers

| Layer | Components | Responsibility |
|---|---|---|
| **Browser** | `templates/index.html`, `static/js/app.js`, `static/js/audio-processor.js`, `static/css/style.css` | UI, mic capture (24 kHz PCM16 via AudioWorklet), audio playback, WebRTC peer connection for the avatar, mode badge (CLOUD / LOCAL). |
| **App** | `app.py`, `session_handlers/`, `local_clients/`, `connectivity.py`, `weather_service.py` | WebSocket router; per-session handler selection; SDK calls to Voice Live; REST calls to on-prem services; periodic probe of the cloud endpoint; optional `get_weather` function tool. |
| **Cloud (Azure)** | Microsoft Foundry resource — Voice Live, TTS Avatar, HD/Std voices | Speech recognition, generative reasoning (`gpt-realtime` family), text-to-speech, semantic VAD, server-side noise/echo suppression, real-time avatar rendering. |
| **On-prem (optional)** | `speech-to-text` container, `neural-text-to-speech` container, Microsoft Foundry Local | Equivalent STT / TTS / LLM functions for the fallback voice-only experience when the cloud is unreachable. |

---

## Component table

| Component | File / Image | Notes |
|---|---|---|
| FastAPI app | `app.py` | Hosts the WebSocket endpoint, the static UI, `/api/health`, `/api/avatars`, `/api/hybrid/status`. |
| Cloud handler | `session_handlers/cloud.py` | Wraps the `azure-ai-voicelive` async SDK; handles session lifecycle + avatar SDP relay + function-call routing. |
| Local handler | `session_handlers/local.py` | Orchestrates STT → LLM → TTS with energy-based VAD and barge-in. Voice-only. |
| Connectivity supervisor | `connectivity.py` | Background HTTPS probe of `AZURE_AI_ENDPOINT`. Threshold-debounced state flip. |
| Local clients | `local_clients/{stt,tts,llm}.py` | Async wrappers — REST for STT/NTTS, OpenAI-compatible for Foundry Local. |
| Speech STT container | `mcr.microsoft.com/azure-cognitive-services/speechservices/speech-to-text` | Connected or disconnected metering. ≈ 4 vCPU / 4 GB RAM. |
| NTTS container | `mcr.microsoft.com/azure-cognitive-services/speechservices/neural-text-to-speech:<voice-tag>` | One image per voice. ≈ 6 vCPU / 12 GB RAM. Standard neural voices only — no HD/Dragon. |
| Foundry Local | `winget install Microsoft.FoundryLocal` (Windows) / `brew install foundrylocal` (macOS) | Serves an OpenAI-compatible `/v1/chat/completions` endpoint. Linux substitute: vLLM with `--api compat=openai`. |

---

## Data flow

### Cloud mode (default)

```
mic ─base64 PCM16─▶ App ─WebSocket─▶ Azure Voice Live ─▶ Avatar Service
                                                      ─▶ HD/Std voices
                                                      ─▶ gpt-realtime LLM
              audio + transcripts ◀── Voice Live ◀── (same events)
              video frames        ◀── Avatar Service via WebRTC
```

User audio crosses the public internet. Data residency = the region of the Foundry resource.

### Local-fallback mode

```
mic ─base64 PCM16─▶ App (edge host) ─HTTP─▶ Speech STT container (loopback)
                                       ─HTTP─▶ Foundry Local (loopback)
                                       ─HTTP─▶ NTTS container (loopback)
              audio + transcripts ◀── App ◀── (assembled locally)
```

Audio never leaves the edge host. Outbound during a session: zero (connected
container metering uses a periodic background ping, not per-request).

---

## Trust boundaries

| Boundary | Notes |
|---|---|
| Browser ↔ App | WebSocket. Browser only ever sends `start_session` / `audio_chunk` / `send_text` / `interrupt` / `stop_session` and the optional `avatar_sdp_offer`. App emits the events documented in `static/js/app.js`. |
| App ↔ Azure | `DefaultAzureCredential` (Azure CLI or managed identity) → Voice Live WebSocket. RBAC: **Cognitive Services User** + **Azure AI User** on the Foundry resource. |
| App ↔ on-prem containers | Plain HTTP on the site LAN by default. Run on the same host (loopback) or front with a reverse proxy + mTLS for production. |
| App ↔ Foundry Local | Loopback only. No authentication. |
| On-prem containers ↔ Azure | Required for connected metering. Replaced by license-file mount for disconnected operation. |

---

## Locked design decisions

| # | Decision | Choice | Rationale |
|---|---|---|---|
| 1 | Orchestration layer (cloud) | Azure Voice Live API as the single fused orchestrator | Voice Live bundles ASR + LLM + TTS + semantic VAD + barge-in + tool calling behind one WebSocket; minimizes our orchestration code and matches Microsoft's strategic direction for real-time voice. |
| 2 | Cloud model family | `gpt-realtime`, `gpt-realtime-1.5`, `gpt-realtime-2` (configurable via `VOICE_LIVE_MODEL`) | Speech-in / speech-out fused models with the lowest end-to-end latency and best prosody. `gpt-realtime` is the GA default; -1.5 and -2 are validated upgrade targets. See [`hybrid/model-selection.md`](./hybrid/model-selection.md). |
| 3 | Avatar rendering | Azure TTS Avatar Service via WebRTC | The only Microsoft-supported real-time avatar; no on-prem equivalent exists. Browser handles WebRTC directly using ICE servers issued by Voice Live. |
| 4 | Voice tier | HD ("Dragon") voices preferred, with Multilingual / Standard neural as fallbacks | HD voices deliver the most natural prosody. Standard neural voices are available in the on-prem NTTS container; HD voices are cloud-only. |
| 5 | Identity | `DefaultAzureCredential` (keyless) | Same credential chain works for `az login` on dev boxes and Managed Identity in production. No secrets in the repo. |
| 6 | Local fallback orchestrator | Per-session decision (NOT mid-session failover) | Mid-session handler swap would require replaying conversation state — high complexity for low value. Per-session decision is cheap and easy to reason about. |
| 7 | Local LLM substitute | Foundry Local (Linux: vLLM) serving Qwen 2.5 7B (default) or Phi-4 | No on-prem `gpt-realtime` exists. Foundry Local provides the closest OpenAI-compatible chat-completion experience with hardware acceleration and zero ongoing cost. |
| 8 | Local TTS voice | Standard neural via `neural-text-to-speech` container (default `en-US-JennyNeural`) | HD/Dragon voices are not in the container catalog. Standard neural is the highest-fidelity option that runs on-prem. |
| 9 | Local VAD | Energy-based, in-process | Voice Live's semantic VAD has no on-prem equivalent. Energy VAD is environment-sensitive but tuneable via `LOCAL_VAD_*` env knobs. |
| 10 | Browser protocol | Additive changes only (`mode` field on `session_started`, new `mode_notice` message) | Cloud and local modes share the same event protocol so the UI is identical except for a mode badge + the avatar pane visibility. |

See [`hybrid/customer-report.md`](./hybrid/customer-report.md) for the
comparative analysis that produced decisions #6–#9, and
[`hybrid/implementation-plan.md`](./hybrid/implementation-plan.md) for the
engineering plan that produced the file layout.

---

## File index reference

The component files referenced in this document live in the repo root. See
[`README.md`](../README.md) for the full file index.

---

*Last updated: 2026-06-04*
