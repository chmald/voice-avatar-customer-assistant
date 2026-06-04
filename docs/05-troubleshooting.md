# 05 — Troubleshooting

> Quick-triage table first, then per-symptom diagnosis with concrete fixes,
> then escalation paths.

---

## 1. Quick triage

Skim this table first. If your symptom matches, jump to the row's "Likely cause" or "Fix" column.

| Symptom | Likely cause | Fix |
|---|---|---|
| `Missing env vars: AZURE_AI_ENDPOINT` on app start | `.env` not present or in the wrong directory | §2.1 |
| `Session error: 403 / AuthorizationFailed` | RBAC propagation or wrong roles | §2.2 |
| `Session error` mentions `quota` or `429` | Voice Live TPM exhausted or model unavailable in region | §2.3 |
| Browser hangs at "Connecting…" | Region mismatch or `az login` expired | §2.4 |
| Avatar fails but voice works | Region supports Voice Live but not TTS Avatar | §2.5 |
| No mic permission popup | Mic blocked on non-`localhost` HTTP origins | §2.6 |
| Audio plays once then stops | Barge-in triggered by silence/noise that VAD treats as voiced | §2.7 |
| Status badge says CLOUD but you wanted LOCAL | `ENABLE_LOCAL_FALLBACK=false`, or supervisor still says cloud reachable | §3.1 |
| `mode_notice` reason says `(force-local-env)` and you didn't want it | `FORCE_LOCAL_MODE=true` is set | §3.2 |
| Local NTTS returns 404 / 400 | Voice name mismatch between env var and container image tag | §3.3 |
| Foundry Local responses are slow | Running on CPU instead of GPU | §3.4 |
| Local STT returns empty `DisplayText` | Container loaded a different locale than the request claims | §3.5 |
| Supervisor stays `reachable: false` after fixing endpoint | Probe interval hasn't elapsed yet | §3.6 |
| `missingLocalConfig` lists endpoints that look set | Trailing whitespace in `.env` | §3.7 |
| Container fails to start with `Eula must be accepted` | Missing or wrong env vars on `docker compose up` | §3.8 |
| `docker compose pull` fails | Outbound HTTPS to `mcr.microsoft.com` blocked | §3.9 |

---

## 2. Cloud-path symptoms

### 2.1 `Missing env vars: AZURE_AI_ENDPOINT` on app start

The app loads `.env` via `python-dotenv` from the **current working
directory**. Most common causes:

- You ran `python app.py` from a different folder.
- `.env` is named `.env.txt` (Windows hiding extensions).
- The file is in `docs/` instead of the repo root.

**Fix:**

```pwsh
cd C:\path\to\ai-voice-live-avatar
Get-ChildItem .env           # confirm it exists
Get-Content .env | Select-String AZURE_AI_ENDPOINT
python app.py
```

---

### 2.2 `Session error: 403 / AuthorizationFailed`

The app's identity does not have both `Cognitive Services User` and `Azure AI User` on the Foundry resource scope, **or** the role assignment hasn't propagated yet.

**Fix:**

```pwsh
$Me = az ad signed-in-user show --query id -o tsv
$Scope = az cognitiveservices account show --name $FoundryName --resource-group $RgName --query id -o tsv
az role assignment list --assignee $Me --scope $Scope --query "[].roleDefinitionName" -o tsv
```

If both roles are listed, **wait 5 minutes** for propagation and retry. If either is missing, run [`03-deployment.md §1.6`](./03-deployment.md#16-grant-yourself-rbac).

---

### 2.3 `Session error` mentions `quota` or `429`

Voice Live TPM (tokens-per-minute) exhausted on the model, or the model isn't available in the region. Run:

```pwsh
$region = "<your-region>"
$model  = "<your VOICE_LIVE_MODEL>"
az cognitiveservices model list --location $region `
    --query "[?model.name=='$model' || contains(model.name, '$model')]" -o table
```

If the model is listed, raise quota via the Azure portal. If it isn't, pick a region from the Tier-1 list in [`02-prerequisites.md §1.3`](./02-prerequisites.md#13-regional-availability-matrix) or switch `VOICE_LIVE_MODEL` to a model that is available — see [`hybrid/model-selection.md`](./hybrid/model-selection.md).

---

### 2.4 Browser hangs at "Connecting…"

Two common causes:

- **Region doesn't support Voice Live.** Verify with [`02-prerequisites.md §1.3`](./02-prerequisites.md#13-regional-availability-matrix).
- **`az login` token expired.** Re-run `az login` and refresh the browser.

If neither helps, check the app log — a hung WebSocket handshake usually emits a TLS or DNS error within ~30 seconds.

---

### 2.5 Avatar fails but voice works

Your region supports Voice Live but **not** TTS Avatar. Options:

- Uncheck **Enable Avatar** for a voice-only demo.
- Recreate the Foundry resource in `eastus2`, `westus2`, `westeurope`, `swedencentral`, or `southeastasia` — the only regions with full feature parity ([`02-prerequisites.md §1.3`](./02-prerequisites.md#13-regional-availability-matrix)).

---

### 2.6 No mic permission popup

Modern browsers only grant mic access on **secure origins** — `https://` everywhere except `http://localhost` (or `http://127.0.0.1`, with some caveats).

- For local development, always navigate to `http://localhost:8000` (not the LAN IP).
- For LAN testing, front the app with an HTTPS reverse proxy (Caddy, nginx + Let's Encrypt, or `ngrok`).

---

### 2.7 Audio plays once then stops

Barge-in fired — the mic captured a sound that VAD treated as voiced speech, cancelling the assistant's playback.

- Mute the mic in the browser UI if you're just listening to the greeting.
- For local mode: raise `LOCAL_VAD_RMS_THRESHOLD` (default `350`) — see [`04-testing.md §5`](./04-testing.md#5-vad-tuning-and-acoustic-validation).
- For cloud mode: tune Voice Live's `AzureSemanticVad` parameters in `session_handlers/cloud.py` — defaults work for most environments.

---

## 3. Hybrid-path symptoms

### 3.1 Status badge says CLOUD but you wanted LOCAL

Three possible reasons:

- `ENABLE_LOCAL_FALLBACK=false` — the local handler is disabled entirely.
- The supervisor still says the cloud is reachable (default probe interval 15 s; needs `FAILOVER_FAILURE_THRESHOLD` consecutive failures to flip).
- You wanted to force local but didn't set `FORCE_LOCAL_MODE=true`.

**Diagnostic:**

```pwsh
curl.exe -sS http://localhost:8000/api/hybrid/status | python -m json.tool
```

Check `enableLocalFallback`, `forceLocalMode`, `supervisor.reachable`.

---

### 3.2 Banner says `(force-local-env)` and you didn't want it

`FORCE_LOCAL_MODE=true` is set in your `.env` or environment. Unset it and restart:

```pwsh
$env:FORCE_LOCAL_MODE = $null
Get-Content .env | Select-String FORCE_LOCAL_MODE   # confirm it's not in .env either
python app.py
```

---

### 3.3 Local NTTS returns 404 or 400

The `LOCAL_TTS_VOICE` value doesn't match the voice loaded in the NTTS container image you pulled. Each NTTS image ships **one voice**.

Mapping: image tag `<ver>-amd64-en-us-jennyneural` ↔ env value `en-US-JennyNeural`. Tag is lowercase + hyphenated; env value is capitalized + the `Neural` suffix.

**Fix:**

```bash
# What's in the container right now?
docker inspect ai-voice-live-avatar-tts --format '{{ .Config.Image }}'
# Match the env value
grep LOCAL_TTS_VOICE .env
```

If you need a different voice, pull the matching tag from MCR (see `docker-compose.local.yml` comments) and restart compose.

---

### 3.4 Foundry Local responses are slow

The LLM is running on CPU. Options:

- Install on a GPU-equipped host and re-run `foundry service start`; Foundry Local auto-detects CUDA / DirectML / Metal.
- Drop `LOCAL_LLM_MAX_TOKENS` (default 256) to 96–128 for faster but shorter answers.
- Switch to a smaller model: `LOCAL_LLM_MODEL=phi-3.5-mini-instruct` (~2 GB) runs acceptably on CPU.

See [`hybrid/model-selection.md`](./hybrid/model-selection.md) for the model catalog and sizing.

---

### 3.5 Local STT returns empty `DisplayText`

The container loaded a different locale than the request claims. The `speech-to-text` image you pulled has a baked-in locale (e.g. `5.1.0-amd64-en-us`).

**Fix:**

```bash
docker inspect ai-voice-live-avatar-stt --format '{{ .Config.Image }}'   # confirms locale
grep LOCAL_STT_LANGUAGE .env
```

If they disagree, either change `LOCAL_STT_LANGUAGE` to match the image, or pull the right image tag for your target locale.

---

### 3.6 Supervisor stays `reachable: false` after fixing the endpoint

The supervisor probes every `FAILOVER_PROBE_INTERVAL_S` seconds (default 15). After fixing `AZURE_AI_ENDPOINT`, wait one interval and re-check:

```pwsh
curl.exe -sS http://localhost:8000/api/hybrid/status
```

If it's still `false` after 30 seconds, the URL probably resolves but the network path is blocked. Run the probe manually:

```pwsh
$endpoint = (Get-Content .env | Select-String AZURE_AI_ENDPOINT).ToString().Split("=")[1]
curl.exe -sS -I $endpoint
```

A timeout means egress firewall is blocking it; any HTTP response (200/401/404) should clear the supervisor on the next probe.

---

### 3.7 `missingLocalConfig` lists endpoints that look set

The check uses **exact-string-empty**. A line like `LOCAL_LLM_MODEL=qwen2.5-7b-instruct ` (with trailing space) parses to a non-empty string but a value that won't match what Foundry Local serves.

Strip trailing whitespace from `.env`:

```pwsh
(Get-Content .env) | ForEach-Object { $_.TrimEnd() } | Set-Content .env
```

---

### 3.8 Container fails to start with `Eula must be accepted`

Compose-time env vars weren't set. Re-run:

```pwsh
$env:SPEECH_BILLING = "https://$FoundryName.cognitiveservices.azure.com/"
$env:SPEECH_API_KEY = az cognitiveservices account keys list `
    --name $FoundryName --resource-group $RgName --query key1 -o tsv

docker compose -f docker-compose.local.yml up -d
```

For persistent setup, put these in a `.env` file **next to** `docker-compose.local.yml` (Docker Compose reads `.env` automatically).

---

### 3.9 `docker compose pull` fails

Outbound HTTPS to `mcr.microsoft.com` is blocked.

```bash
curl -sS -I https://mcr.microsoft.com/v2/    # should return 200 or 401
```

If it times out, ask your network team to allow `mcr.microsoft.com` (the public MCR endpoint) or to mirror the images to a private registry and update `docker-compose.local.yml` to point at the mirror.

---

## 4. Operational checks

### Useful one-liners

```pwsh
# What's the supervisor seeing right now?
curl.exe -sS http://localhost:8000/api/hybrid/status | python -m json.tool

# Are the local services up?
docker compose -f docker-compose.local.yml ps
curl.exe -sS http://localhost:5273/v1/models       # Foundry Local

# What was the last error from each service?
docker compose -f docker-compose.local.yml logs --tail=50 speech-stt
docker compose -f docker-compose.local.yml logs --tail=50 speech-tts
```

### Where to look in the app log

- `Session ... → cloud` / `Session ... → local (reason=...)` — handler routing decision
- `Cloud unreachable after N consecutive failures: <error>` — supervisor flip
- `Function call: <name>(<args>)` — tool use (cloud mode)
- `local-stt failed: ...` / `local-llm failed: ...` / `local-tts failed: ...` — local pipeline error surfaces

---

## 5. Escalation

When a symptom isn't covered by §2–§3:

| Layer | Where to go |
|---|---|
| **Azure / Voice Live / Avatar service** | [Voice Live FAQ](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live-faq), [Speech regions](https://learn.microsoft.com/azure/ai-services/speech-service/regions), Azure support ticket on the Foundry resource. |
| **Speech containers** | [Speech containers overview](https://learn.microsoft.com/azure/ai-services/speech-service/speech-container-overview), [Disconnected containers FAQ](https://learn.microsoft.com/azure/ai-services/containers/disconnected-container-faq). |
| **Foundry Local** | [Foundry Local docs](https://learn.microsoft.com/azure/foundry-local/what-is-foundry-local), [Foundry Local CLI](https://learn.microsoft.com/azure/foundry-local/how-to/how-to-use-foundry-local-cli). |
| **App routing / handlers** | Read [`hybrid/implementation-plan.md`](./hybrid/implementation-plan.md), then [`session_handlers/local.py`](../session_handlers/local.py). Open a GitHub issue with the relevant app log lines. |

---

*Last updated: 2026-06-04*
