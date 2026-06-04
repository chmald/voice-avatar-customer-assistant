# 04 — Testing

> Test plan for the AI TTS Avatar covering cloud (Phase 3) and the optional
> hybrid path (Phase 4). Manual today — automated coverage of the new code
> paths is tracked in [`hybrid/implementation-plan.md`](./hybrid/implementation-plan.md).

---

## 1. Pre-flight (always)

```pwsh
python app.py
```

In a second shell:

```pwsh
curl.exe -sS http://localhost:8000/api/health
curl.exe -sS http://localhost:8000/api/hybrid/status
```

| Check | Expected |
|---|---|
| `/api/health` | `{"status":"ok","missing_keys":[]}` |
| `/api/hybrid/status` (cloud-only) | `enableLocalFallback: false`, `supervisor: null` |
| `/api/hybrid/status` (hybrid enabled) | `supervisor.reachable: true`, `missingLocalConfig: []` |

---

## 2. Functional tests — cloud path (Phase 3)

| # | Pre-conditions | Action | Expected result |
|---|---|---|---|
| F1 | Default `.env`, **Enable Avatar** checked | Click **Start Avatar**. | Avatar video appears within ~10 s; greeting audio plays; status `Connected`. |
| F2 | F1 done | Click the mic, ask "What can you do?" | UI shows `Listening…`, then your transcript appears, then assistant text streams in, then audio plays. |
| F3 | F2 done | Type "Tell me a joke" into the chat input, press Enter. | Assistant responds with both text + audio (no mic needed). |
| F4 | F1 done | While the assistant is speaking, click the mic and start talking. | Playback stops within ~100 ms (barge-in). New utterance is transcribed. |
| F5 | Uncheck **Enable Avatar** before clicking Start | Start Avatar. | No video pane shown. Status `Connected`. Voice + text still work. |
| F6 | Change **Voice** to `Ada HD (UK, F)` and restart session | Speak / type to the assistant. | Reply audio is the new voice (verify by ear). |
| F7 | Change **Voice** to `Jenny (US, F)` (standard neural) and restart | Speak / type. | Reply audio works — this is the same voice the on-prem mode uses by default. |
| F8 | Set `ENABLE_WEATHER_TOOL=true`, restart app | Ask "What's the weather in Seattle?" | Assistant calls the tool, returns a weather summary. Console log shows `Function call: get_weather(...)`. |
| F9 | Ask "What's the weather near me?" with browser geolocation allowed | | Assistant uses lat/lng from the browser and answers with local weather. |
| F10 | Change `VOICE_LIVE_MODEL=gpt-realtime-2`, restart | Repeat F1. | App logs `Connecting — endpoint=..., model=gpt-realtime-2` and the session still works. |

### Expected browser event sequence — cloud turn (F2)

```
→ start_session
← session_started { mode: "cloud", avatarEnabled: true }
← ice_servers
← avatar_sdp_answer

→ audio_chunk * N
← speech_started
← speech_stopped
← transcript_delta / transcript_done (role=user)
← response_created
← transcript_delta / transcript_done (role=assistant)
← (avatar audio + video play via WebRTC)
← response_done
```

---

## 3. Hybrid test matrix (Phase 4 only)

| # | Pre-conditions | Action | Expected result |
|---|---|---|---|
| H1 | `ENABLE_LOCAL_FALLBACK=false` (default) | Start a session. | Same UX as F1. Mode badge hidden. App log: `Session ... → cloud`. |
| H2 | `ENABLE_LOCAL_FALLBACK=true`, cloud reachable, local stack down | Start a session. | Session opens in **cloud** mode. Mode badge blue `CLOUD`. No banner. |
| H3 | `ENABLE_LOCAL_FALLBACK=true`, `FORCE_LOCAL_MODE=true`, full local stack up | Start a session. | Mode badge orange `LOCAL`. Banner reads `(force-local-env)`. Greeting plays via NTTS container. |
| H4 | `ENABLE_LOCAL_FALLBACK=true`, simulate cloud outage (set `AZURE_AI_ENDPOINT` to a bogus host, restart app) | Wait > `FAILOVER_FAILURE_THRESHOLD × FAILOVER_PROBE_INTERVAL_S` for supervisor to flip. Start a session. | Mode badge orange `LOCAL`. Banner reads `(cloud-unreachable: connect: ConnectError ...)`. `/api/hybrid/status` shows `reachable: false`. |
| H5 | H4 — restore correct endpoint, restart app | Wait one probe interval, start a new session. | Session opens in **cloud** mode again. Supervisor `reachable: true`. |
| H6 | H3 — running local session | Click mic, ask "What is two plus two?" | UI shows `Listening…`, your transcript, assistant text, audio plays. STT/LLM/TTS container logs show one request each. |
| H7 | H3 — running local session | Type a message into chat input. | Assistant responds with text + audio. STT container is untouched (typed input bypasses it). |
| H8 | H3 — running local session | Start mic; while assistant is speaking, start talking. | Playback stops within ~100 ms. New utterance is transcribed. |
| H9 | `ENABLE_LOCAL_FALLBACK=true`, deliberately wrong `LOCAL_TTS_VOICE` (e.g. a voice not in the container image) | Force local mode, start a session. | Greeting fails. `error` message in UI mentions `local-tts failed: ... 404 / 400`. Cloud path unaffected. |
| H10 | `ENABLE_LOCAL_FALLBACK=true`, empty `LOCAL_LLM_MODEL` | Force local mode, start. | `session_error` with `local-fallback misconfigured: missing LOCAL_LLM_MODEL`. |

### Expected browser event sequence — local turn (H6)

```
→ start_session
← session_started { mode: "local", avatarEnabled: false }
← mode_notice { mode: "local", reason: "..." }
← response_created   (greeting)
← transcript_delta / transcript_done (role=assistant)
← audio_data * N
← audio_done / response_done

→ audio_chunk * N      (user speaking)
← speech_started
... silence ...
← speech_stopped
← transcript_done (role=user, transcript="...")
← response_created
← transcript_delta / transcript_done (role=assistant)
← audio_data * N
← audio_done / response_done
```

---

## 4. Regression check — cloud parity after hybrid changes

Whenever you change anything in `session_handlers/local.py`, `connectivity.py`, or `local_clients/`, re-run H1 (with `ENABLE_LOCAL_FALLBACK=false`) and F1 + F2 to confirm the cloud path is untouched. The handler refactor is a rename only, but the regression is cheap to verify.

---

## 5. VAD tuning and acoustic validation

Local mode uses energy-based VAD — the defaults work in quiet office environments but the threshold should be tuned per site.

**Calibration procedure:**

1. Set `LOCAL_VAD_RMS_THRESHOLD=0` temporarily (everything is voiced).
2. Make a 5-second recording of silence on the deployment mic. The app's `Audio chunk #N` log lines show the RMS of each chunk — note the silence floor (e.g. 80–120).
3. Repeat with normal speech — note the voiced floor (e.g. 600–1500).
4. Set `LOCAL_VAD_RMS_THRESHOLD` to halfway between silence floor and voiced floor (typical: 350–500).

**Acceptance tests:**

| Test | Expected |
|---|---|
| 3-second silent recording, no speech | `speech_started` does NOT fire. |
| 2-second sentence with 1-second tail silence | `speech_started` fires within 100 ms of speech onset; `speech_stopped` fires ~700 ms after speech ends. |
| Long answer (~10 seconds continuous speech) | Captured as a single utterance — no premature `speech_stopped`. |
| User talks over assistant audio | TTS playback cancelled within ~100 ms; new utterance captured cleanly. |

---

## 6. Demo script (for stakeholder showings)

A 5-minute live walkthrough script:

| Minute | Action | What the audience sees |
|---|---|---|
| 0:00 | Open `http://localhost:8000`. | Empty avatar pane + sidebar. |
| 0:30 | Click **Start Avatar**. | Lisa appears + greets the audience. |
| 1:00 | Ask "What can you do?" via mic. | Lisa replies; status pill turns green/blue as she speaks/listens. |
| 1:30 | (If `ENABLE_WEATHER_TOOL=true`) Ask "What's the weather in Seattle?" | Lisa pauses briefly while the tool runs, then reads the weather. |
| 2:00 | Switch voice to `Ada HD (UK, F)` and reconnect. | Same UI, different voice. |
| 2:30 | Uncheck **Enable Avatar**, reconnect. | Voice-only mode — same chat, no avatar. |
| 3:00 | (Hybrid only) Set `FORCE_LOCAL_MODE=true`, restart, reconnect. | Orange **LOCAL** badge appears + banner; greeting plays from on-prem stack. |
| 3:30 | (Hybrid only) Ask a question via mic. | Show that STT/LLM/TTS containers are processing locally (`docker compose logs -f` in a side window). |
| 4:30 | Stop the app. Talk through the customer report ([`hybrid/customer-report.md`](./hybrid/customer-report.md)) and the Azure-vs-on-prem split ([`hybrid/azure-vs-onprem-responsibility.md`](./hybrid/azure-vs-onprem-responsibility.md)). | Stakeholders see exactly what stays in Azure vs runs on-prem. |

---

## 7. Performance baselines (informational)

Recorded on a single dev box (24 vCPU / 64 GB RAM / NVIDIA L4 16 GB VRAM, Foundry Local with `qwen2.5-7b-instruct`):

| Step (local mode) | Latency |
|---|---|
| STT (3 s utterance, REST) | ~0.4 s |
| LLM first token (256 token cap) | ~0.6 s |
| LLM full response | ~1.5 s |
| TTS first audio chunk | ~0.3 s |
| End-of-utterance → first audio out | **~2.5 s** |

| Step (cloud mode, `gpt-realtime`) | Latency |
|---|---|
| End-of-utterance → first audio out | **~0.5–1.0 s** |

Numbers are indicative — your hardware (especially GPU for the LLM) and your link latency dominate.

---

## 8. Out of scope for this iteration

- Automated unit tests for the new handlers / clients — pending; see [`hybrid/implementation-plan.md`](./hybrid/implementation-plan.md).
- Load testing for concurrent sessions — the cloud path scales linearly with Voice Live quota; the local path scales with edge-host GPU capacity (typically 1–3 concurrent sessions per host).
- Mid-session failover — out of scope per [`hybrid/implementation-plan.md`](./hybrid/implementation-plan.md).
- Function calling on the local path — deferred to v2.

---

*Last updated: 2026-06-04*
