# 05 — Testing & validation

> Manual test plan for the hybrid path. The MVP does not ship automated tests
> for the new code paths — the cloud path is unchanged and continues to be
> covered by existing manual smoke tests, and the local path requires a running
> on-prem stack to test meaningfully.

---

## 1. Pre-flight (always)

```pwsh
# From the repo root, with .env populated
python app.py
```

Then in a second shell:

```pwsh
curl http://localhost:8000/api/health
curl http://localhost:8000/api/hybrid/status
```

Expect `/api/health` to return `{"status":"ok"}`. `/api/hybrid/status` will be
`null` for the supervisor block when `ENABLE_LOCAL_FALLBACK=false` (default).

---

## 2. Test matrix

| # | Pre-conditions | Action | Expected result |
|---|---|---|---|
| T1 | `ENABLE_LOCAL_FALLBACK=false` (default) | Start a session in the browser. | Same UX as `main`. Status bar shows the existing dot; mode badge is hidden. `session_started` log shows `→ cloud`. |
| T2 | `ENABLE_LOCAL_FALLBACK=true`, cloud reachable, local stack down | Start a session. | Session opens in **cloud** mode. Mode badge shows blue `CLOUD`. No banner. |
| T3 | `ENABLE_LOCAL_FALLBACK=true`, `FORCE_LOCAL_MODE=true`, full local stack up | Start a session. | Session opens in **local** mode. Mode badge shows orange `LOCAL`. Banner reads `(force-local-env)`. Greeting plays over the speaker via the NTTS container. |
| T4 | `ENABLE_LOCAL_FALLBACK=true`, **simulate cloud outage** (set `AZURE_AI_ENDPOINT` to a bogus host, then restart app) | Wait > `FAILOVER_FAILURE_THRESHOLD × FAILOVER_PROBE_INTERVAL_S` for supervisor to flip. Start a session. | Session opens in **local** mode. Banner reads `(cloud-unreachable: connect: ConnectError ...)`. `/api/hybrid/status` shows `reachable: false`. |
| T5 | T4 continued — restore the correct `AZURE_AI_ENDPOINT`, restart app. | Wait one probe interval, start a new session. | Session opens in **cloud** mode again. Supervisor `reachable: true`. |
| T6 | Same as T3 — running local session | Click the mic, ask a short question (e.g. "What is two plus two?"). | UI shows `Listening…`, then your transcript, then assistant text, then audio plays back. STT/LLM/TTS container logs show one request each. |
| T7 | Same as T3 — running local session | Type a message into the chat input and hit Enter. | Assistant responds with text+audio. STT container is untouched. |
| T8 | Same as T3 — running local session | Start the mic, then while the assistant is speaking, start talking. | Playback stops within ~100 ms (barge-in). New utterance is transcribed. |
| T9 | `ENABLE_LOCAL_FALLBACK=true`, deliberately wrong `LOCAL_TTS_VOICE` (e.g. a voice not loaded in the container image). | Force local mode and start a session. | Greeting fails; `error` message in the UI mentions `local-tts failed: ... 404 / 400`. Cloud path remains usable. |
| T10 | `ENABLE_LOCAL_FALLBACK=true`, empty `LOCAL_LLM_MODEL`. | Start a session forced local. | App emits `session_error` with `local-fallback misconfigured: missing LOCAL_LLM_MODEL`. |

---

## 3. Expected browser event sequence — local turn (T6)

```
→ start_session
← session_started { mode: "local" }
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

## 4. Cloud regression check

After validating any local-path change, also run T1 with `ENABLE_LOCAL_FALLBACK=false` to confirm the cloud path is untouched. The handler refactor is a rename only — but the regression is cheap to verify.

---

## 5. Things we are NOT testing in MVP

- **Mid-session failover** — out of scope.
- **HD voices in local mode** — not possible.
- **Avatar in local mode** — not possible.
- **Function calling (`get_weather`) in local mode** — deferred to v2.
- **Streaming STT** — local mode uses utterance-batched recognition only.

These items are tracked as `TODO(hybrid-v2):` comments in the source.

---

## 6. Performance benchmarks (informational)

Recorded on a single dev box (24 vCPU / 64 GB / NVIDIA L4 16 GB VRAM, Foundry Local with `qwen2.5-7b-instruct`):

| Step | Latency |
|---|---|
| STT (3 s utterance, REST) | ~0.4 s |
| LLM first token (~256 token cap) | ~0.6 s |
| LLM full response | ~1.5 s |
| TTS first audio chunk | ~0.3 s |
| End-of-utterance → first audio out | **~2.5 s** |

These are indicative only — your hardware will dominate. Cloud Voice Live typically delivers first audio in ~0.5 s once a session is warm.
