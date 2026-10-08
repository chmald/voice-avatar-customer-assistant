# Changelog

All notable changes to this pattern. Dates are ISO `YYYY-MM-DD`.

## Unreleased

### Changed

- Docs: rewrote for external audiences; removed internal terminology. `docs/hybrid/customer-report.md` is now `docs/hybrid/options-analysis.md` (links updated) and addresses the reader directly instead of a single customer; demo-script and testing wording no longer assumes a customer showing; the service-catalog diagram caption says "runs on your own hardware" (PNG re-exported); the `lint_doc_visuals.py` usage example uses `<repo-root>` instead of a profile path.

## 1.1.0 — 2026-10-07 — visual standard retrofit, azd template, Microsoft Learn refresh

Branch: `docs/visual-standard-retrofit` (from `feature/hybrid-local-fallback`).

### Added

- **One-command deployment:** `azure.yaml`, subscription-scoped `infra/azd.bicep` (wraps the shared `main.bicep`, passes every parameter), `infra/azd.parameters.json` (quoted `${VAR=default}` substitutions), and `infra/hooks/` — `preprovision.ps1` (input checks, tenant + subscription guard against `az account show`, soft-delete collision check with opt-in purge), `postprovision.ps1` (writes `demo-ids.local.json` and `AZURE_AI_ENDPOINT` into `.env`), `common.ps1` (shared with `deploy.ps1`).
- **Docs:** `docs/03b-manual-deployment.md` (portal + az CLI path), `docs/06-hybrid-local-fallback.md` (as-built hybrid design), `docs/07-configuration-reference.md` (every azd variable, output, script parameter and runtime variable).
- **Visuals:** 13 draw.io diagrams with official Microsoft Azure Architecture Icons (V24) and PNG renders in `docs/assets/`, the icon pack in `docs/assets/icons/` (with attribution), local SVG status badges in `docs/assets/badges/`; every README/docs page rebuilt on the visual-doc skeleton (hero icons, badges, At a glance, icon tables, callouts, step cards, collapsible detail).
- **Tooling and tests:** `scripts/export_diagrams.py`, `scripts/lint_doc_visuals.py`, `scripts/make_badges.py`; `tests/test_doc_visuals.py`, `tests/test_configuration.py`, `tests/test_azd_template.py`; `pytest.ini`; `scripts/requirements.txt`; `.github/workflows/validate.yml` (static CI: tests, strict lint, Bicep compile); `demo-ids.template.json`.

### Changed

- **Default model `gpt-realtime` → `gpt-realtime-2.1`** in `config.py` and `.env.example`, because the `gpt-realtime` 2025-08-28 version retires on 2027-03-02 (within six months). `gpt-realtime-2.1` is GA (version 2026-07-07, retires 2027-06-25), Pro pricing tier, and is offered in every region where `gpt-realtime` is plus `eastus`.
- `infra/deploy.ps1` now requires `-TenantId` / `-SubscriptionId` (unless `-SkipLogin`), stops on a tenant/subscription mismatch, passes `--subscription` explicitly, validates the region and always writes `demo-ids.local.json`.
- `infra/main.bicep` region allow-list now matches regions with Voice Live models: removed `northeurope`; added `francecentral`, `canadacentral`, `uksouth`, `australiaeast`.
- Role naming: **Azure AI User → Foundry User** throughout docs and comments (role ID `53ca6127-…` unchanged).
- `.gitignore` also excludes `demo-ids.local.json`, `*.local.json`, `.sp-secret.json`, `secrets.json`, `.pytest_cache/`.
- All Mermaid removed from docs (replaced by draw.io diagrams).

### Microsoft Learn verification (2026-10-07)

| Claim | Was | Now | Source |
|---|---|---|---|
| Voice Live WebSocket `api-version` | not stated (SDK-managed) | `2026-04-10`; the `azure-ai-voicelive` SDK (latest 1.3.0 on PyPI) manages it — no code change needed | [Voice Live how-to](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live-how-to) |
| Built-in models | `gpt-realtime` (default), `-1.5`, `gpt-realtime-2` (preview), `-mini`, `gpt-4o(-mini)-realtime-preview` | 25 models incl. `gpt-realtime-2.1` (+ `-mini`, `-datazone`, `-regional`), `-1.5`, `gpt-realtime`, `gpt-4.1`, `gpt-5.x`, `phi4-mm-realtime` (preview), `azure-realtime`; `gpt-realtime-2` and the `gpt-4o-*-realtime-preview` names are gone | [Voice Live overview](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live#supported-models-and-regions) |
| Model retirement | not tracked | `gpt-realtime` (2025-08-28) retires 2027-03-02; `gpt-realtime-2.1` 2027-06-25; `gpt-realtime-1.5` 2027-08-24; `gpt-realtime-2` (preview) replaced by 2.1 | [Model retirement schedule](https://learn.microsoft.com/azure/foundry/openai/concepts/model-retirement-schedule) |
| Region matrix | `eastus` no avatar; `centralindia` no avatar; `westeurope` full Voice Live; `northeurope` Voice Live ⚠️ | Real-time avatar in 11 regions incl. `eastus` and `centralindia`; `westeurope` has no realtime models; `northeurope` has no Voice Live models; `francecentral` avatar capacity limited | [Speech regions](https://learn.microsoft.com/azure/ai-services/speech-service/regions) |
| HD voice regions | 7 regions | 9: adds `canadacentral`, `francecentral` | [Speech regions — TTS](https://learn.microsoft.com/azure/ai-services/speech-service/regions?tabs=tts) |
| Data residency | "Speech doesn't process audio outside the resource region" | Speech data stays in the resource region, but Voice Live **model inference follows the model scope** (global / data zone / regional) | [Speech regions](https://learn.microsoft.com/azure/ai-services/speech-service/regions) |
| Runtime roles | Cognitive Services User + Azure AI User | Cognitive Services User + **Foundry User** (renamed; same ID) | [Voice Live how-to](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live-how-to) |
| BYOM identity | Foundry User only for cross-resource override | Also required for `byom-azure-openai-chat-completion` and `byom-foundry-anthropic-messages` with Entra auth; Anthropic profile still preview | [BYOM](https://learn.microsoft.com/azure/ai-services/speech-service/how-to-bring-your-own-model) |
| Pricing | $0.20–0.40/min Voice Live, $0.50–1.00/min avatar | Token-based Pro / Standard / Lite tiers by model; avatar billed separately; per-minute figures removed | [Voice Live pricing](https://learn.microsoft.com/azure/ai-services/speech-service/voice-live#pricing) |
| Foundry Local platforms | "doesn't officially ship on Linux yet" | Windows, macOS (Apple silicon) and Linux | [What is Foundry Local](https://learn.microsoft.com/azure/foundry-local/what-is-foundry-local) |
| Jeff avatar | retiring Dec 2026 | Still retiring December 2026 (unchanged; omitted from the UI) | [Standard avatars](https://learn.microsoft.com/azure/ai-services/speech-service/text-to-speech-avatar/standard-avatars) |

### Known gaps

- Diagram PNGs were rendered from the same layout model with Microsoft Edge (headless) because the draw.io desktop CLI wasn't installed in the authoring environment. Re-export with `python scripts/export_diagrams.py docs/assets` on a machine with draw.io for pixel-identical draw.io output.
- `az bicep build` wasn't run (Bicep CLI not installed in the authoring environment); `azd provision --preview` wasn't run (no demo tenant targeted). Live tests (F1–F10, H1–H10) weren't re-run for 1.1.0 — see `docs/04-testing.md` § Live validation.

## 1.0.0 — 2026-06-04

- FastAPI + browser client on Azure Voice Live with WebRTC avatar, HD voices, BYOM, weather tool and live transcription (`main`).
- Hybrid local fallback MVP (Approach A): `session_handlers/` split, connectivity supervisor, local clients, `docker-compose.local.yml`, mode badge (`feature/hybrid-local-fallback`).
- Standard 6-doc layout under `docs/` plus `docs/hybrid/` supplements; subscription-scope Bicep (`infra/main.bicep`, `modules/foundry.bicep`, `modules/rbac.bicep`) and `infra/deploy.ps1`.
