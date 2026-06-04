# 02 — Prerequisites

> What you need before standing up the demo. The cloud path (always required)
> is in §1. The optional on-prem fallback adds the items in §2.
>
> Pre-flight checklist is at the bottom — verify every box before starting
> [`03-deployment.md`](./03-deployment.md).

---

## 1. Always required — cloud path

### 1.1 Azure

| Item | Notes |
|---|---|
| **Azure subscription** | With **Contributor** + **User Access Administrator** on the target resource group (or subscription scope for greenfield). |
| **Microsoft Foundry resource** (`kind=AIServices`) | The unified multi-service Cognitive Services account. Hosts Voice Live, TTS Avatar, neural voices, and (optionally) BYOM model deployments under one endpoint. |
| **Regional alignment** | Foundry resource must be in a region that supports every cloud feature you plan to enable — see [§1.3](#13-regional-availability-matrix). |
| **RBAC** | App identity needs **Cognitive Services User** + **Azure AI User** on the Foundry resource. |
| **Voice Live model access** | Built-in models (`gpt-realtime` family) are served by Voice Live with no separate deployment. For BYOM (`byom-azure-openai-realtime`, `…-chat-completion`, `…-foundry-anthropic-messages`) you need a deployment in the Foundry resource. |

### 1.2 Local developer tooling

| Tool | Minimum | Install |
|---|---|---|
| **Python** | 3.10+ | `winget install Python.Python.3.12` / `brew install python@3.12` / apt |
| **Azure CLI** | 2.60+ | `winget install Microsoft.AzureCLI` / `brew install azure-cli` / [InstallAzureCLIDeb](https://aka.ms/InstallAzureCLIDeb) |
| **Git** | any recent | `winget install Git.Git` / `brew install git` / apt |
| **PowerShell** | 7+ (`pwsh`) | Built into Windows. macOS: `brew install --cask powershell`. Linux: `sudo snap install powershell --classic`. |
| **Browser** | Chrome 120+ or Edge 120+ | WebRTC + AudioWorklet path. Not tested on Firefox or Safari. |

> **Shell convention.** Every shell snippet in `docs/` is PowerShell (`pwsh`).
> They work cross-platform on `pwsh` 7+. To translate to `bash`, convert
> `$VAR = "value"` → `VAR=value` and backtick `` ` `` → `\`.

### 1.3 Regional availability matrix

Each cloud capability we use has its own regional footprint. The Foundry resource must be in a region that supports **every** feature you plan to enable.

✅ supported · ❌ not supported · ⚠️ check Microsoft Learn (changes frequently)

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

> Sources (verify before deploying):
> [Speech regions — Voice Live](https://learn.microsoft.com/azure/ai-services/speech-service/regions?tabs=voicelive),
> [Speech regions — TTS Avatar](https://learn.microsoft.com/azure/ai-services/speech-service/regions?tabs=ttsavatar),
> [HD voice availability](https://learn.microsoft.com/azure/ai-services/speech-service/language-support?tabs=tts),
> [Voice Live model availability](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live).

#### Tiered recommendation

| Tier | Regions | Use when |
|---|---|---|
| **Tier 1 (recommended)** | `eastus2`, `westus2`, `westeurope`, `swedencentral`, `southeastasia` | You want full feature parity (avatar + HD + Voice Live). Default for new deployments. |
| **Tier 2 (acceptable)** | `eastus`, `centralindia` | Voice-only with HD voices acceptable; no avatar. |
| **Tier 3 (workarounds)** | Any other Voice Live region | Voice-only with standard neural voices. No HD, no avatar. |

Run the verify-at-deployment-time CLI snippet from [`03-deployment.md` Phase 1.5](./03-deployment.md#15-verify-region-supports-your-feature-set) before provisioning to confirm the matrix above is still accurate for your tenant.

### 1.4 Cost estimate (order-of-magnitude)

Per concurrent session, in cloud mode, at typical demo / pilot workloads:

| Component | Charging model | Rough rate |
|---|---|---|
| Voice Live API | Per minute of audio | $0.20–0.40 / min depending on tier (verify with the [Speech service pricing page](https://azure.microsoft.com/pricing/details/cognitive-services/speech-services/)) |
| Avatar (real-time) | Per minute of video | $0.50–1.00 / min |
| HD voices | Included with Voice Live when used inline | n/a |
| BYOM Azure OpenAI deployment (if used) | Per TPM / PTU on the deployment | Customer's existing AOAI billing applies |

For accurate quotes, use the [Azure Pricing Calculator](https://azure.microsoft.com/pricing/calculator/) or invoke the pricing skill that produced the Demos exemplars.

---

## 2. Optional — on-prem hybrid fallback path

Skip this section if you only need cloud mode.

### 2.1 Edge host hardware (per site)

Minimum (single concurrent session, no GPU):

| Resource | Minimum |
|---|---|
| CPU | 16 vCPU |
| RAM | 32 GB |
| Disk | 200 GB SSD |
| GPU | none (LLM on CPU — first-token latency several seconds) |
| OS | Linux x64 (Ubuntu 22.04 LTS+, Debian 12+, RHEL 9+) or Windows 11 / Server 2025 for Foundry Local |
| Docker | Engine 24+ or Podman 4+, with Docker Compose v2 |

Recommended (1–3 concurrent voice sessions, snappy responses):

| Resource | Recommended |
|---|---|
| CPU | 24 vCPU |
| RAM | 64 GB |
| Disk | 500 GB SSD |
| GPU | NVIDIA, 16+ GB VRAM (e.g. RTX 4080, L4, A10) — for 7B-class LLM at chat-quality latency |

#### Why these numbers

- STT container: ≈ 4 vCPU / 4 GB RAM per Microsoft's container recommendation.
- NTTS container: ≈ 6 vCPU / 12 GB RAM **per voice tag** (each voice = one image).
- Foundry Local 7B-class model: GPU strongly preferred (CPU works, just slow).
- Headroom for the FastAPI app + OS + logging.

### 2.2 Azure-side prerequisites (on-prem still needs these)

| Item | Notes |
|---|---|
| **Speech SKU on Foundry resource** | Standard S0. Required for Speech container metering. |
| **Foundry resource key** | KEY1 or KEY2 from the Foundry portal → *Keys and Endpoint*. Passed to containers as `ApiKey=...`. Rotate via the portal. |
| **Disconnected-containers approval** *(only if running offline)* | Submit <https://aka.ms/csdisconnectedcontainers>. Typical review SLA ≈ 10 business days. Requires a **commitment-tier** SKU purchase. |

### 2.3 Network requirements

#### Connected mode (default)

| Outbound HTTPS to | Why |
|---|---|
| `*.cognitiveservices.azure.com` | Speech container metering + Voice Live optional REST surfaces |
| `*.services.ai.azure.com` | Voice Live WebSocket (cloud mode) |
| `login.microsoftonline.com` | Entra ID tokens for `DefaultAzureCredential` and container metering |
| `mcr.microsoft.com` | Image pulls + updates |
| `huggingface.co` or `*.foundry.microsoft.com` | First-time model download for Foundry Local |

#### Disconnected mode (offline-tolerant)

After initial image pulls + license download:
- Containers run fully offline. License file refresh ≈ every 30 days.
- Foundry Local: fully offline after first model download.
- Cloud-mode sessions still need the URLs above; only the **local-fallback path** runs with zero internet.

### 2.4 Identity and secrets

| Secret | Lives where | Used by |
|---|---|---|
| Foundry resource key | Site-local secrets manager / Docker secrets / `.env` (0600 perms) | Speech containers — `ApiKey=...` env var |
| Entra token | Acquired on demand by `DefaultAzureCredential`; cached in process | App for cloud Voice Live calls |
| Foundry Local | n/a (no auth) | Bind to loopback or to a LAN interface behind a firewall |
| Speech disconnected license file | `/license` bind mount on the host | Speech containers (offline metering) |

---

## 3. Verify-at-deployment-time CLI snippets

Run these on the day of deployment to catch any drift from this document.

### 3.1 Confirm your subscription supports the Foundry resource kind

```pwsh
az provider show --namespace Microsoft.CognitiveServices `
    --query "resourceTypes[?resourceType=='accounts'].locations" -o tsv `
    | Select-String -Pattern "<your-region>"
```

### 3.2 Confirm the model is available in your region

```pwsh
# Replace with your target region and the Voice Live model you plan to use
$region = "eastus2"
$model  = "gpt-realtime"   # or gpt-realtime-2, gpt-realtime-1.5, gpt-realtime-mini

az cognitiveservices model list --location $region `
    --query "[?model.name=='$model' || contains(model.name, '$model')].{name:model.name, version:model.version, format:model.format}" `
    -o table
```

If the model isn't returned, pick a different region from [§1.3](#13-regional-availability-matrix) or pick a different model from [`hybrid/model-selection.md`](./hybrid/model-selection.md).

### 3.3 Confirm container images are pullable (hybrid only)

```bash
docker pull mcr.microsoft.com/azure-cognitive-services/speechservices/speech-to-text:latest
docker pull mcr.microsoft.com/azure-cognitive-services/speechservices/neural-text-to-speech:latest
```

If a pull fails, your firewall is blocking `mcr.microsoft.com`.

### 3.4 Confirm Foundry Local can serve your chosen model (hybrid only)

```pwsh
foundry --version
foundry model list                       # browse the catalog
foundry model download qwen2.5-7b-instruct
foundry service start
curl.exe -sS http://localhost:5273/v1/models
```

---

## 4. Naming conventions

| Resource | Convention | Example |
|---|---|---|
| Resource group | `rg-aitts-<env>-<region>` | `rg-aitts-dev-eastus2` |
| Foundry resource | `aif-aitts-<env>-<region>` (≤ 64 chars, must be globally unique) | `aif-aitts-dev-eastus2-001` |
| Edge host (DNS) | `aitts-edge-<site>-01` | `aitts-edge-seattle-01` |
| Hybrid voice tag | NTTS image tag `<ver>-amd64-<locale>-<voice>` ↔ env `LOCAL_TTS_VOICE` `<Locale>-<VoiceName>Neural` | tag `3.11.0-amd64-en-us-jennyneural` ↔ `LOCAL_TTS_VOICE=en-US-JennyNeural` |

---

## 5. Pre-flight checklist

Verify every box before starting [`03-deployment.md`](./03-deployment.md).

### Always (cloud path)

- [ ] `az login` succeeds and `az account show` returns the correct subscription.
- [ ] You have Contributor + User Access Administrator on the target RG (or subscription).
- [ ] Region chosen from [§1.3](#13-regional-availability-matrix) supports every feature you plan to enable.
- [ ] `python --version` ≥ 3.10, `az --version` ≥ 2.60, `git --version`, `pwsh --version` ≥ 7.
- [ ] Browser is Chrome 120+ or Edge 120+.
- [ ] Voice Live model availability verified in your region (§3.2).

### Hybrid (additional)

- [ ] Edge host meets at least the minimum spec from §2.1.
- [ ] Outbound HTTPS open to all URLs in §2.3.
- [ ] `docker info` and `docker compose version` succeed on the edge host.
- [ ] Foundry resource key on hand (from portal → Keys and Endpoint).
- [ ] Container images pullable (§3.3).
- [ ] Foundry Local installed (Windows / macOS) **or** vLLM available (Linux substitute).
- [ ] If offline operation is the goal: disconnected approval email + commitment-tier SKU.

---

*Last updated: 2026-06-04*
