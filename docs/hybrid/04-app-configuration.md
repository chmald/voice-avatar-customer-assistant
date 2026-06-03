# 04 — App configuration

> Reference for every environment variable consumed by the hybrid path. All of
> these are optional — with `ENABLE_LOCAL_FALLBACK=false` (the default) the app
> behaves exactly as on `main`.

---

## 1. Top-level switches

| Variable | Default | Purpose |
|---|---|---|
| `ENABLE_LOCAL_FALLBACK` | `false` | Master switch. When false, the local handler is never used and the supervisor doesn't run. |
| `FORCE_LOCAL_MODE` | `false` | When true (and fallback is enabled), every session is served by the local handler regardless of cloud reachability. Useful for offline demos and CI runs. |

---

## 2. Local stack endpoints

| Variable | Default | Purpose |
|---|---|---|
| `LOCAL_STT_ENDPOINT` | `http://localhost:5001` | Base URL of the Speech `speech-to-text` container. |
| `LOCAL_STT_LANGUAGE` | `en-US` | BCP-47 locale tag sent to the STT container. Must match the language model loaded in the container image. |
| `LOCAL_TTS_ENDPOINT` | `http://localhost:5002` | Base URL of the Speech `neural-text-to-speech` container. |
| `LOCAL_TTS_VOICE` | `en-US-JennyNeural` | Voice short-name. **Must** match the image tag pulled (`...-en-us-jennyneural`). HD/Dragon voices are not in the container catalog. |
| `LOCAL_LLM_ENDPOINT` | `http://localhost:5273/v1` | OpenAI-compatible base URL. Foundry Local prints the port via `foundry service status`. |
| `LOCAL_LLM_MODEL` | `qwen2.5-7b-instruct` | Model alias. Must already be downloaded (or, with vLLM, registered as `--served-model-name`). |
| `LOCAL_LLM_API_KEY` | `not-needed` | Foundry Local doesn't authenticate; the OpenAI client just demands a non-empty value. |
| `LOCAL_LLM_TIMEOUT_S` | `30` | HTTP timeout for chat completions. |
| `LOCAL_LLM_MAX_TOKENS` | `256` | Max tokens per assistant reply. Tune to balance latency vs. answer richness. |

---

## 3. Connectivity supervisor

| Variable | Default | Purpose |
|---|---|---|
| `FAILOVER_PROBE_INTERVAL_S` | `15` | Seconds between probes. |
| `FAILOVER_PROBE_TIMEOUT_S` | `3` | Per-probe HTTP timeout. A slower link can legitimately need a larger value — bump to 5–8 on satellite connections. |
| `FAILOVER_FAILURE_THRESHOLD` | `2` | Consecutive failures required to flip from "reachable" to "unreachable". Prevents a single transient blip from triggering fallback. |

---

## 4. Voice Activity Detection (local mode only)

The cloud handler uses `AzureSemanticVad` server-side. The local handler can't — it implements a simple energy-based VAD over 20 ms frames.

| Variable | Default | Purpose |
|---|---|---|
| `LOCAL_VAD_RMS_THRESHOLD` | `350` | RMS amplitude above which a frame is considered "voiced". Mic gain, room noise, and the headset model all affect what a reasonable value is — for quiet office headsets, 250–500 works. Run with a fixed mic and a brief silence to calibrate. |
| `LOCAL_VAD_SILENCE_MS` | `700` | Trailing silence (ms) that ends an utterance. Lower for snappier turn-taking, higher to be more permissive. |
| `LOCAL_VAD_MIN_SPEECH_MS` | `250` | Utterances shorter than this are discarded (filters mic clicks). |
| `LOCAL_VAD_MAX_UTTERANCE_MS` | `20000` | Hard cap. Anything longer is sent to STT even if the user is still talking — the REST short-audio endpoint caps at 60 s. |

---

## 5. Inspecting the runtime state

Two endpoints help operators check the hybrid plumbing:

```http
GET /api/health
{ "status": "ok", "missing_keys": [] }

GET /api/hybrid/status
{
  "enableLocalFallback": true,
  "forceLocalMode": false,
  "supervisor": {
    "endpoint": "https://your-foundry.cognitiveservices.azure.com",
    "reachable": true,
    "consecutiveFailures": 0,
    "lastCheckTs": 1717452390.12,
    "lastError": null
  },
  "localStack": {
    "stt": "http://localhost:5001",
    "tts": "http://localhost:5002",
    "llm": "http://localhost:5273/v1",
    "voice": "en-US-JennyNeural",
    "model": "qwen2.5-7b-instruct"
  },
  "missingLocalConfig": []
}
```

---

## 6. Troubleshooting

| Symptom | Likely cause / fix |
|---|---|
| Banner says `(client-requested)` even though I didn't toggle anything | Browser dev tooling injected `forceMode: "local"` in `start_session`. Refresh. |
| Status flashes `LOCAL` but voice never plays | NTTS container is up but the voice tag in `LOCAL_TTS_VOICE` doesn't match the image tag. Verify with `docker compose ps` and the SSML voice name. |
| Local turns are very slow | Foundry Local is on CPU. Either drop `LOCAL_LLM_MAX_TOKENS` (faster but shorter answers) or run on a GPU host. |
| VAD never triggers end-of-speech | `LOCAL_VAD_RMS_THRESHOLD` too low for a noisy room — every frame counts as voiced. Raise it (try `600` or `800`) and re-test. |
| VAD ends utterance after every breath | `LOCAL_VAD_SILENCE_MS` too low — bump from 700 ms to 1200 ms. |
| STT returns empty `DisplayText` | The container loaded a different locale than the request claims. Confirm the image's locale matches `LOCAL_STT_LANGUAGE`. |
| Supervisor stays `reachable: false` even after the link comes back | Default probe interval is 15 s — wait, or hit `GET /api/hybrid/status` after a manual probe. If it persists, check the URL in `AZURE_AI_ENDPOINT` and your egress firewall. |
| `missingLocalConfig` includes endpoints that look set | The empty-string check is exact — make sure your `.env` lines don't have trailing whitespace. |
| Cloud session works but starts local even when reachable | Either `FORCE_LOCAL_MODE=true` is set, or the supervisor's first probe failed and the next probe is still seconds away. Visit `/api/hybrid/status` to confirm. |
