# Model selection

> Reference for picking the **right LLM in each mode**. Cloud mode runs against
> a Voice Live built-in model (default `gpt-realtime-2.1`) or your own deployment
> via BYOM; local mode runs against a chat-completion model served by Foundry
> Local. There is no on-prem equivalent of the `gpt-realtime` family — read
> [§3](#3-why-there-is-no-on-prem-gpt-realtime) for the reason.

---

## 1. Cloud — Azure Voice Live models

Voice Live API exposes a built-in, fully managed set of models. The
deployment side is **zero-config**: pick a name in `VOICE_LIVE_MODEL` and
Voice Live serves it directly (no Foundry deployment, no capacity planning).
Availability depends on the **resource region**, and the inference scope
(global, data zone, regional) depends on the model name.

| Model | `VOICE_LIVE_MODEL` value | Status (Learn, 2026-10-07) | Use when |
|---|---|---|---|
| **GPT Realtime 2.1** | `gpt-realtime-2.1` | GA (version 2026-07-07, retires 2027-06-25) — **default** | New builds. Pro pricing tier; improved silence and noise handling over GPT Realtime 2. |
| GPT Realtime 2.1 data zone / regional | `gpt-realtime-2.1-datazone`, `gpt-realtime-2.1-regional` | GA | Prompts and responses must stay in the resource's data zone or region. |
| GPT Realtime 2.1 mini | `gpt-realtime-2.1-mini` | GA | Cost-sensitive workloads (Standard pricing tier). |
| **GPT Realtime 1.5** | `gpt-realtime-1.5` (and `-datazone`) | GA (retires 2027-08-24) | A stable alternative to the 2.x series. |
| GPT Realtime | `gpt-realtime` (and `-datazone`, `-regional`) | GA — the 2025-08-28 version **retires 2027-03-02** | Existing apps only; plan the move to `gpt-realtime-2.1`. Not offered in `eastus` or `westeurope`. |
| GPT Realtime mini | `gpt-realtime-mini` | GA | Cost-optimized (Standard tier). |
| Cascaded models | `gpt-4.1`, `gpt-4.1-mini`, `gpt-5.x`, `gpt-4o`, `phi4-mm-realtime` (preview), … | Varies | Speech in / out through Azure speech to text + text to speech; also the only option in some regions (for example `westeurope`). |

> **Removed in v1.1.0:** `gpt-realtime-2` (preview, superseded by `gpt-realtime-2.1`),
> `gpt-4o-realtime-preview` and `gpt-4o-mini-realtime-preview` no longer appear in
> the Voice Live model list.

> **Authoritative sources:**
> [Voice Live overview — supported models](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live#supported-models-and-regions),
> [Voice Live region support](https://learn.microsoft.com/azure/ai-services/speech-service/regions?tabs=voice-live),
> [GPT Realtime 2.x](https://learn.microsoft.com/azure/foundry/openai/concepts/realtime-2) and the
> [model retirement schedule](https://learn.microsoft.com/azure/foundry/openai/concepts/model-retirement-schedule).
> Microsoft updates the list independently of this repo — re-check before every engagement.

### Default in this repo

```env
# .env / .env.example
VOICE_LIVE_MODEL=gpt-realtime-2.1
```

To swap models, change a single line and restart the app:

```env
VOICE_LIVE_MODEL=gpt-realtime-2.1-mini   # GA, Standard tier, cheaper
# or
VOICE_LIVE_MODEL=gpt-realtime-1.5        # GA, previous series
```

No code change required. No Foundry deployment work required for the built-in list.

### When you want a model that isn't built-in — BYOM

If you need a model Voice Live doesn't pre-deploy (a fine-tuned realtime
deployment, a PTU deployment, `gpt-5.5` / `gpt-5.4-mini` / `gpt-5.4-nano`,
a model router, Grok, or Anthropic Claude on Foundry), use the BYOM plumbing
(already wired into `session_handlers/cloud.py`):

| BYOM profile | When | What `VOICE_BYOM_MODEL` is |
|---|---|---|
| `byom-azure-openai-realtime` | You created a private `gpt-realtime-2.1`, `gpt-realtime-1.5` or `gpt-realtime-mini` deployment in your own Foundry resource (e.g. dedicated TPM quota or PTU) | The deployment NAME you set in the Foundry portal |
| `byom-azure-openai-chat-completion` | You want a chat-completion model (`gpt-5.4`, `gpt-5.5`, Grok, model router) — Voice Live will glue STT/TTS around it | The deployment NAME you set in the Foundry portal |
| `byom-foundry-anthropic-messages` | You want Claude on Foundry (preview), e.g. `claude-sonnet-4.6` | The deployment NAME you set in the Foundry portal |

With Entra ID auth, the chat-completion and Anthropic profiles (and any
`VOICE_BYOM_FOUNDRY_RESOURCE_OVERRIDE`) need the Voice Live Foundry resource's
system-assigned identity to hold **Foundry User** on the model's resource
([BYOM authentication setup](https://learn.microsoft.com/azure/ai-services/speech-service/how-to-bring-your-own-model)).

Example `.env` for BYOM with a realtime deployment:

```env
ENABLE_BYOM_MODE=true
VOICE_BYOM_MODE=byom-azure-openai-realtime
VOICE_BYOM_MODEL=my-gpt-realtime-21-prod       # your deployment name
# Optional cross-resource:
# VOICE_BYOM_FOUNDRY_RESOURCE_OVERRIDE=my-other-foundry
```

---

## 2. Local-fallback — Foundry Local chat-completion models

Foundry Local ships a curated catalog of OpenAI-compatible chat-completion
models that run **fully on-device**. The app reaches them via the standard
`/v1/chat/completions` route, so any OpenAI-compatible SDK works.

Recommended choices for this app's local mode:

| Foundry Local model | Approx. size | Why | Hardware |
|---|---|---|---|
| **`qwen2.5-7b-instruct`** *(default)* | ~5 GB | Strong general chat, multi-language, holds a conversation through ~8 turns at 256 max tokens. Battle-tested in Foundry Local. | GPU ≥ 12 GB VRAM recommended; CPU works but slow. |
| **`phi-4`** | ~9 GB | Microsoft model, latency-optimized. Concise answers — fits voice well. | GPU ≥ 16 GB VRAM recommended. |
| `mistral-7b-instruct` | ~4 GB | Proven baseline; slightly older than Qwen2.5 / Phi-4. | GPU ≥ 12 GB VRAM. |
| `phi-3.5-mini-instruct` | ~2 GB | Aggressively small; use on edge boxes without GPU. | CPU-only acceptable; expect ~3–6 s per reply. |
| `qwen2.5-0.5b` | <1 GB | Sanity-test the wiring on a laptop. | CPU. |

Set them in `.env`:

```env
LOCAL_LLM_MODEL=qwen2.5-7b-instruct
# or
LOCAL_LLM_MODEL=phi-4
```

Download once on the edge box (requires internet for first pull only):

```bash
foundry model download qwen2.5-7b-instruct
foundry service start
foundry service status        # prints port, e.g. http://localhost:5273
```

Foundry Local supports Windows, macOS (Apple silicon) and Linux
([What is Foundry Local](https://learn.microsoft.com/azure/foundry-local/what-is-foundry-local)).
If you prefer another server — or need a model outside the Foundry Local catalog —
substitute **vLLM** or **llama.cpp's server** (both expose an OpenAI-compatible API);
the app only requires an OpenAI-compatible `/v1/chat/completions` endpoint. Example:

```bash
pip install "vllm>=0.6"
vllm serve Qwen/Qwen2.5-7B-Instruct \
    --port 5273 --served-model-name qwen2.5-7b-instruct --max-model-len 4096
```

Then set `LOCAL_LLM_ENDPOINT=http://localhost:5273/v1` (the same value the
app already uses for Foundry Local).

---

## 3. Why there is no on-prem `gpt-realtime`

The `gpt-realtime` family is **speech-in / speech-out**: it accepts raw audio
and emits raw audio, fused inside a single model that lives only in Azure. It
is **not** part of Foundry Local's catalog and there is no published container.

The local-fallback handler therefore re-builds the realtime experience out of
three separate components: dedicated **STT container**, a **chat-completion
LLM** in Foundry Local, and a dedicated **NTTS container**. The pipeline is
strictly inferior to `gpt-realtime` on two dimensions:

1. **Latency.** Three round-trips vs one fused model.
2. **Prosody / turn-taking.** Semantic VAD, mid-utterance interruptions, and
   audio-conditioned reasoning are unavailable. We compensate with an
   energy-based VAD and a smaller `LOCAL_LLM_MAX_TOKENS` to keep replies snappy.

This is acceptable because local mode is the **fallback**, not the steady-state
experience.

---

## 4. Side-by-side parity table

| Capability | Cloud (`gpt-realtime-2.1` / `-1.5` / `gpt-realtime`) | Local fallback (chat-completion LLM) |
|---|---|---|
| Speech-in / speech-out fused | ✅ | ❌ Re-built from STT + LLM + TTS |
| Semantic VAD / turn detection | ✅ | ⚠️ Energy-based VAD |
| Barge-in (interrupt assistant) | ✅ | ✅ (TTS playback cancellable) |
| Function calling / tool use | ✅ | ❌ MVP (planned v2) |
| Multiple languages mid-utterance | ✅ | ⚠️ Depends on Foundry Local model + STT locale |
| HD ("Dragon") voices | ✅ | ❌ Standard neural only |
| Real-time TTS Avatar | ✅ | ❌ Not available |
| End-to-end first-audio latency | ~0.5–1.0 s | ~2–4 s (hardware-dependent) |
| Network egress per session | continuous | none (after license/cache is warm) |

---

## 5. Configuration cheat-sheet

| Variable | Default | Where it's used |
|---|---|---|
| `VOICE_LIVE_MODEL` | `gpt-realtime-2.1` | Cloud Voice Live built-in model |
| `VOICE_BYOM_MODE` | `byom-azure-openai-realtime` (only used when `ENABLE_BYOM_MODE=true`) | BYOM profile string |
| `VOICE_BYOM_MODEL` | *(empty)* | Foundry deployment NAME for BYOM |
| `LOCAL_LLM_MODEL` | `qwen2.5-7b-instruct` | Foundry Local model alias |
| `LOCAL_LLM_ENDPOINT` | `http://localhost:5273/v1` | Foundry Local OpenAI-compatible base URL |

Audit current effective values at runtime:

```bash
curl http://localhost:8000/api/hybrid/status
# localStack.model + localStack.voice show what local mode will use
```

The cloud model in use is logged at session start: look for
`Connecting — endpoint=..., model=gpt-realtime-2.1` in the app log.

---

## 6. Migration tips

| Goal | Action |
|---|---|
| Move an existing deployment from `gpt-realtime` → `gpt-realtime-2.1` (before the 2027-03-02 retirement) | Change `VOICE_LIVE_MODEL=gpt-realtime-2.1` on a single test host, run [`../04-testing.md`](../04-testing.md) F1–F2 and F10, roll out gradually. Check the region offers it first. |
| Use your own realtime deployment (dedicated quota / PTU) | `ENABLE_BYOM_MODE=true`, `VOICE_BYOM_MODE=byom-azure-openai-realtime`, `VOICE_BYOM_MODEL=<your-deployment>`. |
| Swap the local LLM to Phi-4 | `foundry model download phi-4`; restart Foundry Local; `LOCAL_LLM_MODEL=phi-4`; restart app. |
| Pin to a specific `gpt-realtime-mini` snapshot | Use BYOM realtime profile and a deployment named for the dated snapshot (e.g. `gpt-realtime-mini-2025-12-15`). |

---

*Last updated: 2026-10-07*
