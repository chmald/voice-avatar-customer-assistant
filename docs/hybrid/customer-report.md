# Hybrid Localization Options for the Azure AI Voice Live API with Avatar Application

**Audience:** Customer architecture / decision-maker
**Source application:** `ai-voice-live-avatar` (FastAPI + Azure AI Voice Live API with Avatar)
**Goal:** Reduce network dependency on cloud Azure services so that application instances on sites with poor or intermittent internet connectivity remain usable, **without** abandoning Azure as the primary platform.
**Status:** Discovery / planning. Implementation will follow on a feature branch once the approach is approved.

---

## 1. Executive summary

The application today is a thin client around **Azure AI Voice Live API**, with optional real-time **TTS Avatar** rendering, HD ("Dragon") neural voices, and BYOM model deployments from a Microsoft Foundry resource. Every conversational turn — STT, reasoning (LLM), TTS, semantic VAD, barge-in, function-calling, and avatar video — currently traverses the public internet to Azure.

After reviewing the Microsoft Learn documentation, **the Voice Live orchestrator itself and the real-time TTS Avatar are cloud-only** — Microsoft does not ship them as a container, embedded SDK, or Foundry Local model. Therefore a true 100% offline deployment is not achievable while keeping the current experience.

A **hybrid** deployment is achievable. Three concrete approaches are presented below, ranging from minimum disruption (cloud-primary with edge fallback) to maximum resiliency (fully local pipeline with cloud burst). Each trades feature richness against tolerance for connectivity loss.

**Recommendation:** *Approach A — Cloud-primary with on-prem voice-only fallback*. It preserves the avatar/HD-voice experience on a healthy link, gracefully degrades to a usable voice-only experience when the link is poor, and keeps the engineering scope contained.

---

## 2. What must stay integrated with Azure

These pieces have **no supported on-premises substitute from Microsoft** and remain a cloud dependency in every hybrid design:

| Component | Why it must stay in Azure |
|---|---|
| **Voice Live API orchestrator** | Microsoft does not publish the orchestration layer (session protocol, semantic VAD, barge-in, tool-call coordination) as a container or SDK. It is a managed service. |
| **Real-time TTS Avatar (Lisa, Harry, Max, Lori, Meg, photo avatars / `vasa-1`)** | The neural avatar renderer runs only in the Azure Avatar Service. WebRTC ICE/TURN servers are issued by Azure. No container exists. |
| **HD (Dragon) voices** (`*:DragonHDLatestNeural`) | Not present in the Neural TTS container catalog. Cloud-only inference. |
| **Anthropic models on Foundry** (`byom-foundry-anthropic-messages`) | Not in Foundry Local, not in any container. Managed offering only. |
| **Voice Live's "BYOM" plumbing** (`profile=byom-…`, `foundry-resource-override=…`) | Voice Live resolves the deployment server-side against a Foundry resource. It cannot dial a local LAN endpoint. |
| **Container metering / licensing** | Even "disconnected" Speech containers require an Azure Foundry (formerly Cognitive Services) resource for billing, an approved disconnected commitment tier, and periodic usage reporting. |
| **Identity (Entra ID / DefaultAzureCredential)** | Required to acquire tokens for any Azure call. Tokens can be cached, but renewal needs reachability to Entra. |

These remain Azure regardless of approach. Localization can only target the components below.

---

## 3. What *can* be moved to the edge

| Component | Local option | Approval needed | Notes |
|---|---|:---:|---|
| **STT (transcription)** | (a) `speech-to-text` Speech container, (b) Embedded Speech SDK | (a) yes for disconnected; (b) yes (limited access) | Container is connected or disconnected. Embedded SDK is C#/C++/Java only. |
| **TTS (standard neural voices)** | `neural-text-to-speech` Speech container | yes for disconnected | One image per voice tag. Approx. 6 vCPU / 12 GB RAM per voice. No HD/Dragon voices. |
| **LLM (chat reasoning)** | **Foundry Local** (OpenAI-compatible REST) running Phi, Mistral, Qwen, DeepSeek, GPT-OSS, etc. | No (Foundry Local is freely available) | Drop-in `/v1/chat/completions`; first model download requires internet, after that fully offline. |
| **Function tools (e.g. `get_weather`)** | Already keyless (Open-Meteo). Can be replaced with a self-hosted mirror. | No | Trivial. |
| **Voice Activity Detection (replacement for `AzureSemanticVad`)** | Silero VAD / WebRTC VAD (not Microsoft) | No | Local mode loses semantic VAD; falls back to energy/endpoint VAD. |
| **Noise / echo suppression (replacement for `azure_deep_noise_suppression`, `server_echo_cancellation`)** | Browser-side WebRTC AEC + RNNoise (not Microsoft) | No | Acceptable for voice-only mode. |

---

## 4. Comparative analysis of approaches

> The same legend is used throughout: ✅ supported · ⚠️ partial / degraded · ❌ not supported

### Approach A — Cloud-primary, on-prem **voice-only fallback** *(Recommended)*

The application defaults to Azure Voice Live + avatar. A small connectivity supervisor watches the WebSocket. When the link to Azure is unreachable or degrades past a threshold (e.g. handshake fails, or > N seconds of dead time), the session is routed to a **local pipeline** running on the same on-prem box: Speech container STT → Foundry Local LLM → Speech container TTS, surfaced through the existing browser UI in voice-only mode. When connectivity returns, the next session reverts to cloud.

**Pros**
- Customer keeps the full avatar + HD-voice experience whenever the link is healthy.
- Failure mode is *graceful*: instead of a "session error", the user gets a degraded but functional assistant.
- Browser protocol does not change — the UI just hides the avatar pane when in local mode.
- Engineering scope is bounded: one new `LocalSessionHandler` and a small supervisor.
- On-prem footprint is moderate (one Linux box per site, 1× STT container + 1× NTTS container + Foundry Local).

**Cons**
- Two codepaths to maintain, including divergent VAD/AEC implementations.
- Avatar and HD voices are unavailable in fallback mode (no Microsoft option for either offline).
- Requires Microsoft approval for **disconnected** containers and a **commitment-tier** SKU.
- Local model quality (Phi-4, Mistral, Qwen) will not match GPT-realtime — answers will be shorter and less nuanced.
- First-token latency in local mode depends on the on-prem hardware (GPU strongly recommended).

**Stays in Azure**
- Voice Live + avatar + HD voices (primary path).
- Foundry resource for billing of the Speech containers and for the cloud Voice Live model.
- Entra ID for both the cloud path and the container metering identity.

**On-prem footprint**
- 1 Linux host (or VM) per site. Reference: 16+ vCPU, 32+ GB RAM, optional NVIDIA GPU for the LLM.
- Docker / Podman.
- `mcr.microsoft.com/azure-cognitive-services/speechservices/speech-to-text:latest` (STT).
- `mcr.microsoft.com/azure-cognitive-services/speechservices/neural-text-to-speech:<voice-tag>` for each fallback voice.
- Foundry Local runtime + one downloaded chat model (e.g. `phi-4`, `qwen2.5-7b-instruct`, or `mistral-7b-instruct`).

---

### Approach B — Fully **local pipeline** with cloud-burst for hard questions

The on-prem box becomes the *primary* path: STT container → Foundry Local LLM → NTTS container. Voice Live and the avatar are removed from the default UX. Optionally, the local orchestrator routes a subset of queries (or all queries when the link is good) to **Azure OpenAI** in the customer's Foundry resource for higher-quality reasoning, with a local fallback if the cloud call fails.

**Pros**
- Survives full internet outages.
- Lowest steady-state egress and predictable latency (STT/TTS on LAN).
- Customer data for routine queries never leaves the site (useful for data-residency stories).
- No dependency on Voice Live region capacity.

**Cons**
- **No avatar at all** — the headline UX feature is permanently gone.
- **No HD/Dragon voices** — only standard neural voices.
- Must reimplement orchestration: VAD, barge-in, tool-calling, transcript streaming, session state. This is the largest item of work.
- Loses Voice Live's semantic VAD and `azure_deep_noise_suppression` — quality of conversation flow will drop noticeably.
- Same approval/commitment-tier requirement for disconnected containers.
- Higher on-prem hardware bill (LLM runs constantly, not just on failover).

**Stays in Azure**
- Foundry resource for container billing and (optionally) Azure OpenAI burst.
- Entra ID.
- Optional: cloud Whisper or Foundry-hosted LLM for the burst path.

**On-prem footprint**
- Same as Approach A, but sized for steady production load (recommend NVIDIA GPU, 24+ GB VRAM, for the LLM at low latency).

---

### Approach C — Cloud Voice Live with **local RAG / tool execution only**

Keep the architecture exactly as it is today. Move only the *tools* and any retrieval/lookup the model performs onto the on-prem box. The Voice Live call continues to traverse the internet; the win is that the tool latency that *amplifies* a session's wall-clock time becomes local.

**Pros**
- Minimal change. No new containers from Microsoft required.
- Avatar and HD voices fully preserved.
- No approval process, no commitment-tier purchase.

**Cons**
- Does **not** address the customer's stated problem — if the internet drops, the application is still dead.
- Only modestly reduces round-trip latency on tool-using turns.

**Stays in Azure**
- Everything in the current architecture stays unchanged.

**On-prem footprint**
- A small service exposing the tools the model calls (today, only the weather tool — Open-Meteo is already keyless and trivial to mirror).

---

### Side-by-side summary

| Dimension | A — Cloud + local fallback | B — Local-first + cloud burst | C — Tools only |
|---|:---:|:---:|:---:|
| Works during full internet outage | ⚠️ Voice-only | ✅ | ❌ |
| Avatar preserved | ⚠️ Only when online | ❌ | ✅ |
| HD (Dragon) voices preserved | ⚠️ Only when online | ❌ | ✅ |
| Semantic VAD / barge-in / `azure_deep_noise_suppression` preserved | ⚠️ Only when online | ❌ | ✅ |
| Response quality at the edge | Phi / Mistral class | Phi / Mistral class | Cloud (unchanged) |
| Engineering effort | Medium | High | Low |
| On-prem hardware burden | Medium (idle, used on failover) | High (steady-state) | Low |
| New Azure approvals needed | Disconnected containers + commitment tier | Same | None |
| Predictable monthly Azure spend | Mixed (PAYG cloud + commitment tier) | Commitment tier dominant | Unchanged |
| Customer data residency | Mostly cloud | Mostly on-prem | Cloud |

---

## 5. Hybrid resources to update or provision

This section enumerates everything that needs to change to support **Approach A** (the recommendation). Items marked *(also B)* are required if Approach B is chosen instead.

### 5.1 Azure-side resources

| Resource | Action | Why |
|---|---|---|
| **Microsoft Foundry resource (existing)** | Keep. Confirm the region supports Voice Live (with your model) + avatar + HD voices — Tier 1 as of 2026-10-07: `eastus2`, `westus2`, `swedencentral`, `southeastasia`, `centralindia`, `eastus` (see [`../02-prerequisites.md` §1.3](../02-prerequisites.md#13-regional-availability-matrix)). | Used for cloud-primary path. |
| **Foundry resource — Speech "Standard S0" SKU** | Verify or add. The Speech container metering identity attaches here. | Required for both connected and disconnected container billing. |
| **Disconnected Containers commitment tier** | Purchase via Microsoft account team after approval. | Mandatory pricing model for offline containers. |
| **Access approval** | Submit the disconnected-containers request form (`aka.ms/csdisconnectedcontainers`). Allow ~10 business days. | Microsoft must approve disconnected use per Azure tenant. |
| **RBAC role assignments** | `Cognitive Services User` + `Foundry User` (formerly named `Azure AI User`; same role ID) on the Foundry resource for the application's managed identity. Unchanged from today. | Already in use; reconfirm for any new sites. |
| **Entra app / managed identity** | One per site if you want per-site auditability; one shared otherwise. | Token acquisition for container metering and for the cloud Voice Live path. |
| **(Optional) Azure OpenAI deployment** *(also B)* | Add a `gpt-4.1` or `gpt-5` deployment in your Foundry resource as a "burst" target. | Used by Approach B; can be added later. |
| **Azure Monitor / Log Analytics workspace** | Add a workspace and forward container + app logs (when online). | Operational visibility across both paths. |

### 5.2 On-premises resources (per site)

| Resource | Action | Sizing |
|---|---|---|
| **Edge host** | Provision one Linux server or VM per site. | 16+ vCPU, 32+ GB RAM, 200+ GB SSD, optional NVIDIA GPU (recommended for LLM latency). |
| **Container runtime** | Install Docker Engine or Podman + Compose. | Per Microsoft docs. |
| **Speech STT container** | Pull `mcr.microsoft.com/azure-cognitive-services/speechservices/speech-to-text:latest`; run with `Eula=accept Billing=<endpoint> ApiKey=<key>` (connected) or `DownloadLicense=True` once, then offline-mode flags (disconnected). | ~4 vCPU, 4 GB RAM per replica. |
| **Speech NTTS container(s)** | Pull `…/speechservices/neural-text-to-speech:<voice-tag>` for each fallback voice (recommend at least one US English and one regional voice matching the site). | ~6 vCPU, 12 GB RAM per voice. |
| **Foundry Local** | Install via `winget` (Windows), `brew` (macOS) or the Linux package — Foundry Local supports Windows, macOS (Apple silicon) and Linux. Pre-download chat model (e.g. `phi-4`, `qwen2.5-7b-instruct`, `mistral-7b-instruct`). | GPU strongly recommended; 16 GB+ VRAM for a 7B model at chat-quality latency. |
| **(Optional) Self-hosted Open-Meteo mirror** | If full offline weather lookups are required. | Negligible. |
| **(Optional) Local Whisper container** *(also B)* | If you prefer Whisper over the Speech STT container. | GPU recommended. |
| **Networking** | Outbound HTTPS to `*.cognitiveservices.azure.com`, `*.services.ai.azure.com`, `login.microsoftonline.com`, `mcr.microsoft.com` for image pulls and (in connected mode) metering. Inbound on the site LAN only. | Standard. |
| **Time sync** | NTP. | Required for both Azure tokens and container licensing. |
| **Local persistent storage** | Volume for Foundry Local model cache and Speech container licenses. | ~30 GB. |

### 5.3 Application changes (this repo)

These are the code-level updates that will go on the feature branch:

| File / area | Change |
|---|---|
| `config.py` | Add settings: `ENABLE_LOCAL_FALLBACK`, `LOCAL_STT_ENDPOINT`, `LOCAL_TTS_ENDPOINT`, `LOCAL_TTS_VOICE`, `LOCAL_LLM_ENDPOINT`, `LOCAL_LLM_MODEL`, `FAILOVER_HEALTHCHECK_INTERVAL_S`, `FAILOVER_HANDSHAKE_TIMEOUT_S`. |
| `voice_handler.py` | Extract a small `SessionHandler` interface. Keep current implementation as `CloudVoiceLiveSessionHandler`. Add `LocalSessionHandler` that wires STT → LLM → TTS and emits the same browser events (`audio_data`, `transcript_*`, `status`). |
| New `connectivity.py` | Lightweight supervisor: periodic probe of the Voice Live WebSocket endpoint; exposes `should_use_local()` and notifies the WS router on state changes. |
| `app.py` | `/ws/voicelive` chooses handler at session start based on connectivity supervisor. On a state change mid-session, surface a UI notice and let the user decide whether to restart in the other mode. |
| New `local_clients/` package | Thin async clients for the local Speech STT container REST/WS API, local NTTS container REST API, and the Foundry Local OpenAI-compatible endpoint. |
| `static/js/app.js` + `templates/index.html` | Add a "Mode" indicator (Cloud / Local) and auto-hide the avatar pane when in Local mode. |
| `requirements.txt` | Add `openai` (used as a thin OpenAI-compatible client for Foundry Local) and any HTTP client deps. |
| `README.md` | New "Hybrid / offline mode" section documenting the env vars, the on-prem prerequisites, and the degraded-mode caveats. |
| `docker-compose.local.yml` *(new)* | Optional convenience file that spins up the STT + NTTS containers + Foundry Local for developers and for the on-prem deployment. |

### 5.4 Operational / governance items

- **Commitment tier accounting:** Disconnected containers bill on the tier, not per request — finance needs to size the tier to expected hours of use per site.
- **Licensing renewal cadence:** Disconnected containers require periodic license refresh (every ~30 days for some SKUs). Establish a process to bring the license file back online and reinstall.
- **Model lifecycle:** Pin Speech container tags (do **not** use `latest` in production); test version bumps in a lab site first. Same for the Foundry Local model version.
- **Logging:** Decide whether transcripts in local mode are persisted on-prem (for support) or discarded (for privacy). The Voice Live path's logging is unchanged.
- **Privacy posture changes:** In local mode, no audio leaves the site. Document this for the customer's compliance team.

---

## 6. Decision checklist for the customer

1. Is loss of the **avatar** acceptable during connectivity incidents? *(If yes → A or B viable. If no → only C, which doesn't actually solve the problem.)*
2. Is loss of **HD/Dragon voice quality** acceptable in degraded mode? *(Required for A and B.)*
3. Is the customer willing to go through the **disconnected containers approval process** and purchase a **commitment tier**? *(Required for A and B.)*
4. Does the on-prem environment have **GPU capacity** for a 7B-class local LLM? *(Strongly recommended for A; required for B.)*
5. Are **outbound HTTPS** to MCR, Entra, and the Foundry endpoint reliably available, even on slow links? *(Required for container licensing and Approach A's cloud-primary path.)*
6. What **per-site latency budget** is acceptable for first audio when in local mode? *(Sets the GPU sizing.)*
7. Are there **data residency** requirements that prefer Approach B over A?

---

## 7. Suggested next step

> **Status update (2026-10-07):** Approach A has since been implemented as an MVP on `feature/hybrid-local-fallback` (session-handler split, connectivity supervisor, local clients, mode badge, `docker-compose.local.yml`). See [`../06-hybrid-local-fallback.md`](../06-hybrid-local-fallback.md) for the as-built design. The original recommendation is kept below for provenance.

If the customer agrees with Approach A, the implementation work will proceed on a new branch off `main`:

- Branch: `feature/hybrid-local-fallback`
- First milestones: (1) extract `SessionHandler` interface; (2) stub `LocalSessionHandler` returning canned audio; (3) connectivity supervisor; (4) wire real local STT/LLM/TTS; (5) UI mode indicator; (6) `docker-compose.local.yml` and README updates.

At the time this report was written no code changes had been made.

---

*Document version 1.1 — prepared from a review of the codebase (`config.py`, `voice_handler.py`, `app.py`, `requirements.txt`) and Microsoft Learn documentation for Voice Live, Real-time TTS Avatar, Speech containers, Embedded Speech, and Foundry Local. 1.1 refreshes the region list, the Foundry User role name and the Foundry Local platform list.*

---

*Last updated: 2026-10-07*
