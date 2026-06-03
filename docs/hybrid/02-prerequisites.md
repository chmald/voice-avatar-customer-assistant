# 02 — Prerequisites

> What you need in place **before** running the hybrid path. Cloud-only operation
> (the default on `main`) does not require any of this — only the items in the
> root [`README.md`](../../README.md).

---

## 1. Azure-side prerequisites

| Item | Notes |
|---|---|
| **Microsoft Foundry resource** (existing) | Required for Voice Live + Avatar + HD voices on the cloud path **and** for Speech container metering. Region must support every cloud feature you use — see the matrix in the root README. |
| **Speech SKU on the Foundry resource** | Standard S0. Required for container licensing on both connected and disconnected metering. |
| **Disconnected-containers approval** *(only if running offline)* | Submit the request form at <https://aka.ms/csdisconnectedcontainers>. Typical review SLA ≈ 10 business days. Approval is per-tenant. Requires purchase of a **commitment-tier** SKU. |
| **RBAC** | App's identity needs **Cognitive Services User** + **Azure AI User** on the Foundry resource. Same as today. |
| **Entra ID reachability** | App acquires tokens via `DefaultAzureCredential`. Containers' metering identity uses the resource key (not Entra). |

---

## 2. On-prem hardware (per site)

Minimum (works for a single concurrent session, no GPU):

| Resource | Minimum |
|---|---|
| CPU | 16 vCPU |
| RAM | 32 GB |
| Disk | 200 GB SSD |
| GPU | none (LLM runs on CPU — first-token latency ≈ several seconds) |
| OS | Linux x64 (Ubuntu 22.04 LTS+, Debian 12+, RHEL 9+) or Windows 11 / Server 2025 for Foundry Local |
| Docker | Engine 24+ or Podman 4+, with Docker Compose v2 |

Recommended (smooth voice-only conversation, 1–3 concurrent sessions):

| Resource | Recommended |
|---|---|
| CPU | 24 vCPU |
| RAM | 64 GB |
| Disk | 500 GB SSD |
| GPU | NVIDIA, 16+ GB VRAM (e.g. RTX 4080, L4, A10) for 7B-class LLM at chat-quality latency |
| Network | Outbound HTTPS to `mcr.microsoft.com`, `*.cognitiveservices.azure.com`, `*.services.ai.azure.com`, `login.microsoftonline.com`. Inbound on site LAN only. |

### Why these numbers

- **STT container** ≈ 4 vCPU / 4 GB RAM per Microsoft's recommendations.
- **NTTS container** ≈ 6 vCPU / 12 GB RAM **per voice tag** — each voice is its own image.
- **Foundry Local** running a 7B-class model needs either a modern CPU with AVX-512 (slow but workable) or a GPU with ≥ 16 GB VRAM (fast).
- Headroom for the FastAPI app, OS, logging.

---

## 3. Foundry Local

Foundry Local is **not** a container in this stack — it ships as a native installer for Windows and macOS, with a CLI to download and run models.

| OS | Install |
|---|---|
| Windows 10/11 / Server 2025 | `winget install Microsoft.FoundryLocal` |
| macOS (Apple Silicon / Intel) | `brew install foundrylocal` |
| Linux | Currently not officially supported as of the time of writing. For Linux-only edge boxes, use **vLLM** or **llama.cpp** with an OpenAI-compatible front-end as a substitute — the app only requires an OpenAI-compatible `/v1/chat/completions` endpoint. |

Recommended models (pick one):

- `qwen2.5-7b-instruct` — strong general chat, ~7B params.
- `phi-4` — Microsoft model, latency-optimized.
- `mistral-7b-instruct` — proven baseline.

First-run requires internet to download model weights; afterwards Foundry Local runs fully offline.

---

## 4. Network requirements

### Connected mode (default)

- **Outbound HTTPS** to `*.cognitiveservices.azure.com` (Speech container metering).
- **Outbound HTTPS** to `mcr.microsoft.com` (image pulls + updates).
- **Outbound HTTPS** to `login.microsoftonline.com` (Entra ID tokens for the cloud Voice Live path).
- The on-prem services bind to the host LAN; no inbound from the public internet is needed.

### Disconnected mode (offline-tolerant deployments)

- Image pulls still require one-time internet reachability when fetching containers.
- License download (`DownloadLicense=True`) needs **one-time** HTTPS reachability per container per ~30 days.
- After license is mounted, containers run fully offline.

---

## 5. Identity and secrets

| Secret | Where it lives | Notes |
|---|---|---|
| Foundry resource key | Used by Speech containers as `ApiKey=...`. Pass via `SPEECH_API_KEY` env var (read by `docker-compose.local.yml`). Do **not** commit. | Rotate via the Foundry resource portal. |
| Foundry resource billing endpoint | `SPEECH_BILLING` env var. Public. | Format: `https://<name>.cognitiveservices.azure.com/`. |
| Cloud Voice Live auth | `DefaultAzureCredential` — Azure CLI on dev boxes, managed identity in production. Unchanged from today. | |
| Foundry Local | No auth required. The OpenAI client demands a non-empty `api_key` — we pass `"not-needed"`. | |

---

## 6. Validation checklist

Before moving to [`03-onprem-setup.md`](./03-onprem-setup.md), verify:

- [ ] Azure: you can curl `https://<foundry>.cognitiveservices.azure.com/` and get any response (200/401/404 all OK).
- [ ] Azure: `az login` succeeds and `az account show` shows the right subscription.
- [ ] On-prem: `docker info` and `docker compose version` both succeed.
- [ ] On-prem: 30+ GB free disk, 32+ GB RAM available.
- [ ] On-prem: `foundry --version` succeeds (or your chosen alternative — vLLM, llama.cpp, etc.).
- [ ] On-prem: outbound 443 to `mcr.microsoft.com` and `*.cognitiveservices.azure.com` is reachable.
- [ ] If targeting **disconnected** operation: approval email from Microsoft is in hand and the commitment-tier SKU is purchased.
