# Hybrid local-fallback — implementation plan (MVP)

This document is the engineering plan for **Approach A** from [`00-customer-report.md`](./00-customer-report.md): keep Azure Voice Live + Avatar as the primary experience and add a **voice-only local-fallback mode** that the app uses when Azure is unreachable.

Status: **in progress on `feature/hybrid-local-fallback`**.

---

## 1. MVP scope

In scope for this branch:

1. A `SessionHandler` abstraction so the WebSocket endpoint is agnostic of how a session is fulfilled.
2. `CloudVoiceLiveSessionHandler` — the existing `VoiceSessionHandler` class behind the new interface, **behavior preserved**.
3. `LocalSessionHandler` — a new voice-only handler that orchestrates a local pipeline:
   - **STT** ⇒ Azure Speech `speech-to-text` Docker container, called over its short-audio REST endpoint.
   - **LLM** ⇒ Microsoft **Foundry Local** (OpenAI-compatible chat completions).
   - **TTS** ⇒ Azure Speech `neural-text-to-speech` Docker container, called over its REST `/cognitiveservices/v1` endpoint.
   - **VAD** ⇒ in-process energy-based detector (we don't have semantic VAD without Voice Live).
4. A `ConnectivitySupervisor` that probes the cloud Voice Live REST surface and tracks online/offline state.
5. Routing in `app.py`: at session start the supervisor's state plus the `ENABLE_LOCAL_FALLBACK` flag pick the handler. The browser gets a `mode` field on `session_started`.
6. Browser UI changes: a **Cloud / Local** mode badge in the status bar; the avatar pane auto-hides in Local mode and shows a "voice-only fallback" notice.
7. `docker-compose.local.yml` to bring up STT + NTTS for development.
8. Documentation in `docs/hybrid/` (architecture, prerequisites, on-prem setup, app configuration, testing).

**Explicitly out of scope for MVP** (tracked as follow-ups, not blockers for merge):

- **Mid-session failover.** Switching handlers in the middle of an active session requires replaying conversation state and is not worth the complexity for v1. The supervisor only chooses at session start. If cloud drops mid-call, the session ends with `session_error` and the next session starts in Local mode automatically.
- **Semantic VAD / `azure_deep_noise_suppression` / `server_echo_cancellation`** in Local mode. Energy-based VAD only. Document the quality gap.
- **Streaming STT.** The Speech container *does* support streaming via the SDK's WebSocket protocol, but for the MVP we use the REST short-audio endpoint per utterance (60 s max). Streaming is a v2 enhancement.
- **Avatar in Local mode.** Microsoft does not publish an on-prem avatar — see customer report §2. Local mode is voice-only by design.
- **HD ("Dragon") voices in Local mode.** Not in the container catalog. Local mode picks a standard neural voice (default `en-US-JennyNeural`).
- **Function calling (`get_weather`) in Local mode.** v1 ships without tool calling on the local path. Foundry Local supports it; we'll wire it in v2 once the base flow is stable.
- **Bicep / IaC** for the on-prem stack. The on-prem layer is `docker-compose.local.yml` only. The Azure surface is unchanged from `main`.

---

## 2. File map

```
ai-tts-avatar/
├── app.py                                  # CHG: route handler by mode
├── config.py                               # CHG: new env vars + validation
├── voice_handler.py                        # KEEP: file remains (re-exports for back-compat)
├── session_handlers/                       # NEW
│   ├── __init__.py
│   ├── base.py                             # SessionHandler Protocol
│   ├── cloud.py                            # CloudVoiceLiveSessionHandler (moved from voice_handler.py)
│   └── local.py                            # LocalSessionHandler (new)
├── local_clients/                          # NEW
│   ├── __init__.py
│   ├── stt.py                              # Speech container REST client (short audio)
│   ├── tts.py                              # NTTS container REST client (SSML → PCM16)
│   └── llm.py                              # Foundry Local (OpenAI-compatible) client
├── connectivity.py                         # NEW: cloud reachability supervisor
├── docker-compose.local.yml                # NEW: STT + NTTS containers
├── .env.example                            # CHG: documents new env vars
├── requirements.txt                        # CHG: + openai
├── static/js/app.js                        # CHG: render mode badge, hide avatar in local
├── static/css/style.css                    # CHG: badge styles
├── templates/index.html                    # CHG: mode badge markup
├── README.md                               # CHG: hybrid section + file index
└── docs/hybrid/
    ├── 00-customer-report.md               # Comparative report (already in branch)
    ├── IMPLEMENTATION-PLAN.md              # This file
    ├── 01-architecture.md                  # Hybrid architecture + sequence diagrams
    ├── 02-prerequisites.md                 # On-prem sizing, approvals, identity
    ├── 03-onprem-setup.md                  # Container pulls, license download, validation
    ├── 04-app-configuration.md             # Env var reference + troubleshooting
    ├── 05-testing.md                       # Manual test plan
    ├── 06-deployment-runbook.md            # Step-by-step Parts A–F orchestrator
    ├── 07-azure-vs-onprem.md               # Responsibility matrix + data flow + egress rules
    └── 08-model-selection.md               # Voice Live + BYOM + Foundry Local model guide
```

---

## 3. Browser protocol changes (additive only)

New fields and messages (existing ones unchanged):

| Direction | Message | New field(s) | Purpose |
|---|---|---|---|
| Backend → Browser | `session_started` | `mode: "cloud" \| "local"` | Drive UI badge + avatar visibility. |
| Backend → Browser | `mode_notice` (new) | `mode`, `reason` (string) | Sent once on session start to display the "cloud unreachable, falling back to local" banner. |
| Backend → Browser | `session_error` | unchanged | If both cloud and local are unavailable. |

The browser does not gain any new sent messages — it still sends `start_session`, `audio_chunk`, `send_text`, `interrupt`, `stop_session`. In Local mode the `avatar_sdp_offer` flow is never triggered because the avatar pane is hidden.

---

## 4. Milestones

| # | Milestone | What "done" looks like |
|---|---|---|
| M1 | Plan & config | This doc + updated `config.py` and `.env.example`. App still boots, cloud flow unaffected. |
| M2 | Handler abstraction | `session_handlers/base.py` exists; `CloudVoiceLiveSessionHandler` moved into the package; old import path still works (back-compat shim in `voice_handler.py`). Cloud flow unchanged. |
| M3 | Local clients | `local_clients/{stt,tts,llm}.py` with unit-free, async APIs. Importable; smoke-tested against documented endpoints. |
| M4 | Local handler | `LocalSessionHandler` emits the same browser protocol as cloud. End-to-end voice loop works on a developer box that has the containers running. |
| M5 | Connectivity + routing | Supervisor wired into `app.py`; session start picks the right handler; degraded mode surfaces via `mode_notice`. |
| M6 | UI | Mode badge, hidden avatar, banner. |
| M7 | Compose + docs | `docker-compose.local.yml` works on a clean dev box; docs in `docs/hybrid/` complete. |
| M8 | Smoke test | `python app.py` boots clean; `/api/health` ok; `/api/hybrid/status` returns supervisor state; cloud mode unchanged. |

---

## 5. Backward compatibility

- The cloud path is untouched at the protocol level.
- `voice_handler.py` remains as a thin compatibility module re-exporting `VoiceSessionHandler = CloudVoiceLiveSessionHandler` so any external import does not break.
- All new behavior is gated by `ENABLE_LOCAL_FALLBACK`. With it left at the default (`false`), the app behaves exactly as it does on `main`.

---

## 6. Open questions to close before merge

1. **Local LLM default model.** MVP defaults to `qwen2.5-7b-instruct` — confirm this is what we want to recommend, or substitute Phi-4.
2. **Container licensing model.** For developer dev boxes we recommend connected metering. For deployed sites we assume the customer has obtained the disconnected approval.
3. **Audio format from NTTS container.** Container default is `riff-24khz-16bit-mono-pcm`. Our browser playback path expects raw 24 kHz PCM16 — the WAV header must be stripped (44 bytes) before sending. Document and implement.
4. **VAD thresholds.** Energy-based VAD is environment-sensitive. Defaults work in a quiet office; expose `LOCAL_VAD_*` knobs.
5. **Foundry Local discovery.** SDK can auto-resolve port (e.g. 5273) but the OpenAI-compatible endpoint is at `/v1`. We accept a full URL via `LOCAL_LLM_ENDPOINT` to avoid SDK coupling.

These are tracked inline in the relevant source files with `# TODO(hybrid-v2):` comments.
