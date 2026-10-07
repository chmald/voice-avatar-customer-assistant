"""Configuration management for Azure AI Voice Live API with Avatar."""

import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """Application settings loaded from environment variables."""

    # Azure AI / Microsoft Foundry resource (Voice Live API)
    AZURE_AI_ENDPOINT: str = os.getenv("AZURE_AI_ENDPOINT", "")
    # Voice Live built-in model. Realtime options (availability varies by region —
    # see the Voice Live tab of the Speech regions page):
    #   gpt-realtime-2.1          (GA, default; also -mini, -datazone, -regional variants)
    #   gpt-realtime-1.5          (GA)
    #   gpt-realtime              (GA; the 2025-08-28 version retires 2027-03-02)
    #   gpt-realtime-mini         (GA, cost-optimized)
    # Voice Live also serves non-realtime models (gpt-4.1, gpt-5.x, phi4-mm-realtime …)
    # through Azure speech to text + text to speech.
    # For private/fine-tuned deployments use the BYOM settings below instead.
    # Reference: docs/hybrid/model-selection.md
    VOICE_LIVE_MODEL: str = os.getenv("VOICE_LIVE_MODEL", "gpt-realtime-2.1")

    # Optional BYOM (Bring Your Own Model) configuration.
    # See: https://learn.microsoft.com/azure/ai-services/speech-service/how-to-bring-your-own-model
    #   VOICE_BYOM_MODE  — profile: byom-azure-openai-realtime |
    #                       byom-azure-openai-chat-completion |
    #                       byom-foundry-anthropic-messages
    #   VOICE_BYOM_MODEL — your Foundry *deployment name* (overrides VOICE_LIVE_MODEL when BYOM is on)
    #   VOICE_BYOM_FOUNDRY_RESOURCE_OVERRIDE — optional cross-resource override (resource name only, no domain)
    VOICE_BYOM_MODE: str = os.getenv("VOICE_BYOM_MODE", "byom-azure-openai-realtime")
    VOICE_BYOM_MODEL: str = os.getenv("VOICE_BYOM_MODEL", "")
    VOICE_BYOM_FOUNDRY_RESOURCE_OVERRIDE: str = os.getenv("VOICE_BYOM_FOUNDRY_RESOURCE_OVERRIDE", "")

    PORT: int = int(os.getenv("PORT", "8000"))

    # UI defaults (must match an entry in AVATAR_CHARACTERS / PHOTO_AVATARS / VOICES below)
    DEFAULT_VIDEO_CHARACTER: str = os.getenv("DEFAULT_VIDEO_CHARACTER", "lisa")
    DEFAULT_PHOTO_CHARACTER: str = os.getenv("DEFAULT_PHOTO_CHARACTER", "isabella")
    DEFAULT_VOICE: str = os.getenv("DEFAULT_VOICE", "en-US-Ava:DragonHDLatestNeural")

    # Feature flags
    ENABLE_WEATHER_TOOL: bool = os.getenv("ENABLE_WEATHER_TOOL", "false").lower() in ("1", "true", "yes")
    ENABLE_BYOM_MODE: bool = os.getenv("ENABLE_BYOM_MODE", "false").lower() in ("1", "true", "yes")

    # ── Hybrid local fallback (Approach A — see docs/hybrid/) ───────────────
    # When true, the app will fall back to a fully local STT/LLM/TTS pipeline
    # if the cloud Voice Live endpoint is unreachable at session start.
    ENABLE_LOCAL_FALLBACK: bool = os.getenv("ENABLE_LOCAL_FALLBACK", "false").lower() in ("1", "true", "yes")

    # Force the next session to use local mode regardless of cloud reachability
    # (handy for offline development / demos). Off by default.
    FORCE_LOCAL_MODE: bool = os.getenv("FORCE_LOCAL_MODE", "false").lower() in ("1", "true", "yes")

    # Local Speech STT container (Azure Speech `speech-to-text` image).
    # Default points at the docker-compose service name on the same host.
    LOCAL_STT_ENDPOINT: str = os.getenv("LOCAL_STT_ENDPOINT", "http://localhost:5001")
    LOCAL_STT_LANGUAGE: str = os.getenv("LOCAL_STT_LANGUAGE", "en-US")

    # Local NTTS container (Azure Speech `neural-text-to-speech` image).
    LOCAL_TTS_ENDPOINT: str = os.getenv("LOCAL_TTS_ENDPOINT", "http://localhost:5002")
    # Voice short-name matching the container tag pulled (e.g. en-us-jennyneural → en-US-JennyNeural).
    LOCAL_TTS_VOICE: str = os.getenv("LOCAL_TTS_VOICE", "en-US-JennyNeural")

    # Local LLM (Microsoft Foundry Local — OpenAI-compatible endpoint).
    # Foundry Local exposes /v1/chat/completions on a dynamic port; we accept
    # a full base URL ending in /v1.
    LOCAL_LLM_ENDPOINT: str = os.getenv("LOCAL_LLM_ENDPOINT", "http://localhost:5273/v1")
    LOCAL_LLM_MODEL: str = os.getenv("LOCAL_LLM_MODEL", "qwen2.5-7b-instruct")
    # Foundry Local doesn't require a key, but the OpenAI client insists one
    # is passed. Any non-empty value works.
    LOCAL_LLM_API_KEY: str = os.getenv("LOCAL_LLM_API_KEY", "not-needed")
    LOCAL_LLM_TIMEOUT_S: float = float(os.getenv("LOCAL_LLM_TIMEOUT_S", "30"))
    LOCAL_LLM_MAX_TOKENS: int = int(os.getenv("LOCAL_LLM_MAX_TOKENS", "256"))

    # Connectivity supervisor.
    FAILOVER_PROBE_INTERVAL_S: float = float(os.getenv("FAILOVER_PROBE_INTERVAL_S", "15"))
    FAILOVER_PROBE_TIMEOUT_S: float = float(os.getenv("FAILOVER_PROBE_TIMEOUT_S", "3"))
    # Consecutive failures before the supervisor flips to "unreachable".
    FAILOVER_FAILURE_THRESHOLD: int = int(os.getenv("FAILOVER_FAILURE_THRESHOLD", "2"))

    # Energy-based VAD knobs (local mode only — semantic VAD requires Voice Live).
    LOCAL_VAD_SILENCE_MS: int = int(os.getenv("LOCAL_VAD_SILENCE_MS", "700"))
    LOCAL_VAD_RMS_THRESHOLD: int = int(os.getenv("LOCAL_VAD_RMS_THRESHOLD", "350"))
    LOCAL_VAD_MIN_SPEECH_MS: int = int(os.getenv("LOCAL_VAD_MIN_SPEECH_MS", "250"))
    LOCAL_VAD_MAX_UTTERANCE_MS: int = int(os.getenv("LOCAL_VAD_MAX_UTTERANCE_MS", "20000"))

    # Standard video avatar characters and their available styles.
    # Source: https://learn.microsoft.com/azure/ai-services/speech-service/text-to-speech-avatar/standard-avatars
    #
    # Notes:
    #   - Rowan, Celine, Nia, Malik have no style variants (single appearance).
    #   - Lisa's other styles (graceful-sitting/standing, technical-sitting/standing)
    #     are NOT supported via the real-time API — only `casual-sitting` is listed.
    #   - Jeff is being retired (Dec 2026) and is omitted.
    AVATAR_CHARACTERS = [
        {"id": "rowan", "name": "Rowan", "styles": []},
        {"id": "celine", "name": "Celine", "styles": []},
        {"id": "nia", "name": "Nia", "styles": []},
        {"id": "malik", "name": "Malik", "styles": []},
        {"id": "harry", "name": "Harry", "styles": ["business", "casual", "youthful"]},
        {"id": "lisa", "name": "Lisa", "styles": ["casual-sitting"]},
        {"id": "lori", "name": "Lori", "styles": ["casual", "graceful", "formal"]},
        {"id": "max", "name": "Max", "styles": ["business", "casual", "formal"]},
        {"id": "meg", "name": "Meg", "styles": ["business", "casual", "formal"]},
    ]

    # Standard photo avatars (no styles — single appearance per character)
    # Source: https://learn.microsoft.com/en-us/azure/ai-services/speech-service/text-to-speech-avatar/standard-avatars
    PHOTO_AVATARS = [
        {"id": "adrian", "name": "Adrian"},
        {"id": "amara", "name": "Amara"},
        {"id": "amira", "name": "Amira"},
        {"id": "anika", "name": "Anika"},
        {"id": "bianca", "name": "Bianca"},
        {"id": "camila", "name": "Camila"},
        {"id": "carlos", "name": "Carlos"},
        {"id": "clara", "name": "Clara"},
        {"id": "darius", "name": "Darius"},
        {"id": "diego", "name": "Diego"},
        {"id": "elise", "name": "Elise"},
        {"id": "farhan", "name": "Farhan"},
        {"id": "faris", "name": "Faris"},
        {"id": "gabrielle", "name": "Gabrielle"},
        {"id": "hyejin", "name": "Hyejin"},
        {"id": "imran", "name": "Imran"},
        {"id": "isabella", "name": "Isabella"},
        {"id": "layla", "name": "Layla"},
        {"id": "liwei", "name": "Liwei"},
        {"id": "ling", "name": "Ling"},
        {"id": "marcus", "name": "Marcus"},
        {"id": "matteo", "name": "Matteo"},
        {"id": "rahul", "name": "Rahul"},
        {"id": "rana", "name": "Rana"},
        {"id": "ren", "name": "Ren"},
        {"id": "riya", "name": "Riya"},
        {"id": "sakura", "name": "Sakura"},
        {"id": "simone", "name": "Simone"},
        {"id": "zayd", "name": "Zayd"},
        {"id": "zoe", "name": "Zoe"},
    ]

    # English-only TTS voices for Voice Live.
    # Source: https://learn.microsoft.com/azure/ai-services/speech-service/language-support?tabs=tts
    #
    # Tiers (all use voice.type = "azure-standard" per Voice Live spec):
    #   - HD (Dragon) — highest quality, most natural. Limited to regions:
    #       canadacentral, centralindia, eastus, eastus2, francecentral, southeastasia,
    #       swedencentral, westeurope, westus2
    #   - Multilingual — can speak many languages with the same voice persona.
    #   - Standard — classic neural voices, broad regional coverage.
    VOICES = [
        # ── US English — HD (Dragon) ──
        {"id": "en-US-Ava:DragonHDLatestNeural",     "name": "Ava HD (US, F)",     "type": "azure-standard"},
        {"id": "en-US-Andrew:DragonHDLatestNeural",  "name": "Andrew HD (US, M)",  "type": "azure-standard"},
        {"id": "en-US-Brian:DragonHDLatestNeural",   "name": "Brian HD (US, M)",   "type": "azure-standard"},
        {"id": "en-US-Davis:DragonHDLatestNeural",   "name": "Davis HD (US, M)",   "type": "azure-standard"},
        {"id": "en-US-Emma:DragonHDLatestNeural",    "name": "Emma HD (US, F)",    "type": "azure-standard"},
        {"id": "en-US-Aria:DragonHDLatestNeural",    "name": "Aria HD (US, F)",    "type": "azure-standard"},
        {"id": "en-US-Jenny:DragonHDLatestNeural",   "name": "Jenny HD (US, F)",   "type": "azure-standard"},
        {"id": "en-US-Nova:DragonHDLatestNeural",    "name": "Nova HD (US, F)",    "type": "azure-standard"},
        {"id": "en-US-Steffan:DragonHDLatestNeural", "name": "Steffan HD (US, M)", "type": "azure-standard"},
        # ── UK English — HD (Dragon) ──
        {"id": "en-GB-Ada:DragonHDLatestNeural",     "name": "Ada HD (UK, F)",     "type": "azure-standard"},
        {"id": "en-GB-Ollie:DragonHDLatestNeural",   "name": "Ollie HD (UK, M)",   "type": "azure-standard"},
        # ── Multilingual (can switch languages mid-utterance) ──
        {"id": "en-US-AvaMultilingualNeural",        "name": "Ava (US, F, Multilingual)",     "type": "azure-standard"},
        {"id": "en-US-AndrewMultilingualNeural",    "name": "Andrew (US, M, Multilingual)",  "type": "azure-standard"},
        {"id": "en-US-EmmaMultilingualNeural",      "name": "Emma (US, F, Multilingual)",    "type": "azure-standard"},
        {"id": "en-US-BrianMultilingualNeural",     "name": "Brian (US, M, Multilingual)",   "type": "azure-standard"},
        {"id": "en-GB-AdaMultilingualNeural",       "name": "Ada (UK, F, Multilingual)",     "type": "azure-standard"},
        {"id": "en-GB-OllieMultilingualNeural",     "name": "Ollie (UK, M, Multilingual)",   "type": "azure-standard"},
        # ── Standard regional ──
        {"id": "en-US-JennyNeural",                  "name": "Jenny (US, F)",      "type": "azure-standard"},
        {"id": "en-US-GuyNeural",                   "name": "Guy (US, M)",        "type": "azure-standard"},
        {"id": "en-GB-SoniaNeural",                 "name": "Sonia (UK, F)",      "type": "azure-standard"},
        {"id": "en-GB-RyanNeural",                  "name": "Ryan (UK, M)",       "type": "azure-standard"},
        {"id": "en-AU-NatashaNeural",               "name": "Natasha (AU, F)",    "type": "azure-standard"},
        {"id": "en-AU-WilliamNeural",               "name": "William (AU, M)",    "type": "azure-standard"},
        {"id": "en-IE-EmilyNeural",                 "name": "Emily (IE, F)",      "type": "azure-standard"},
        {"id": "en-IE-ConnorNeural",                "name": "Connor (IE, M)",     "type": "azure-standard"},
        {"id": "en-CA-ClaraNeural",                 "name": "Clara (CA, F)",      "type": "azure-standard"},
        {"id": "en-CA-LiamNeural",                  "name": "Liam (CA, M)",       "type": "azure-standard"},
    ]

    SYSTEM_PROMPT = (
        "You are a friendly, helpful AI assistant embodied as a lifelike avatar. "
        "Keep responses conversational and concise (2-3 sentences max) since they "
        "will be spoken aloud. Be warm and engaging. "
        "Always begin the conversation in English (en-US). If the user later "
        "speaks or asks you to switch to another language, you may follow their "
        "lead \u2014 but the initial greeting and any unsolicited response must be in English. "
    )

    if ENABLE_WEATHER_TOOL:
        SYSTEM_PROMPT += (
            "You can look up current weather conditions for any location using the "
            "get_weather tool — use it whenever the user asks about weather, "
            "temperature, or conditions in a place."
        )

    def validate(self) -> list[str]:
        """Return a list of missing required configuration keys."""
        errors = []
        if not self.AZURE_AI_ENDPOINT:
            errors.append("AZURE_AI_ENDPOINT")
        return errors

    def validate_local_fallback(self) -> list[str]:
        """Return missing required keys for the local-fallback path (only checked when enabled)."""
        errors = []
        if not self.LOCAL_STT_ENDPOINT:
            errors.append("LOCAL_STT_ENDPOINT")
        if not self.LOCAL_TTS_ENDPOINT:
            errors.append("LOCAL_TTS_ENDPOINT")
        if not self.LOCAL_LLM_ENDPOINT:
            errors.append("LOCAL_LLM_ENDPOINT")
        if not self.LOCAL_LLM_MODEL:
            errors.append("LOCAL_LLM_MODEL")
        if not self.LOCAL_TTS_VOICE:
            errors.append("LOCAL_TTS_VOICE")
        return errors


settings = Settings()
