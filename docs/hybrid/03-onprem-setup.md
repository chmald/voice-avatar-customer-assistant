# 03 — On-prem setup

> Step-by-step guide to standing up the local stack (STT + NTTS containers + Foundry Local) on a single edge host. Validated commands. Run as the user who will operate the host — not root unless you're using rootless Docker.

---

## 1. Prepare the host

```bash
# Verify Docker
docker info
docker compose version

# Verify ports we'll bind (5001 STT, 5002 NTTS) are free
sudo lsof -i :5001 -i :5002 || true
```

Create an `.env` file alongside `docker-compose.local.yml` (this file is **not** committed):

```bash
# .env (sibling of docker-compose.local.yml)
SPEECH_BILLING=https://<your-foundry-name>.cognitiveservices.azure.com/
SPEECH_API_KEY=<your-foundry-resource-key>
```

> The key is one of the two access keys on the Foundry resource (Portal → *Keys and Endpoint*). Treat it like a password; rotate periodically.

---

## 2. Connected mode (recommended for first run)

This is the simpler path — containers phone home to Azure for metering on a schedule. Use it for development, demos, and pilots before deciding whether you need the disconnected approval.

```bash
# Pull both images (~6 GB total — first time only)
docker compose -f docker-compose.local.yml pull

# Start
docker compose -f docker-compose.local.yml up -d

# Tail logs (Ctrl-C to stop tailing — containers keep running)
docker compose -f docker-compose.local.yml logs -f
```

Validate:

```bash
# STT — empty POST returns a `RecognitionStatus: Error` body, which proves the
# endpoint is up and routing requests.
curl -sS -X POST \
  "http://localhost:5001/speech/recognition/conversation/cognitiveservices/v1?language=en-US" \
  -H "Content-Type: audio/wav; codecs=audio/pcm; samplerate=16000" \
  --data-binary "@/dev/null" | head -c 200 ; echo

# NTTS — synthesize "Hello" and save to a WAV
curl -sS -X POST "http://localhost:5002/cognitiveservices/v1" \
  -H "Content-Type: application/ssml+xml" \
  -H "X-Microsoft-OutputFormat: riff-24khz-16bit-mono-pcm" \
  -H "User-Agent: setup-test" \
  -o /tmp/hello.wav \
  --data '<speak version="1.0" xml:lang="en-US"><voice name="en-US-JennyNeural">Hello from the local container.</voice></speak>'
file /tmp/hello.wav   # → RIFF (little-endian) data, WAVE audio, ...
```

If either curl fails, check `docker compose logs <service>` for an `Eula`, `ApiKey`, or `Billing` error.

---

## 3. Disconnected mode (offline-tolerant deployments)

> Requires approval — see [02-prerequisites.md §1](./02-prerequisites.md#1-azure-side-prerequisites).

### One-time: download the license

Run each container once **online** with `DownloadLicense=True`, mounting a directory the container can write the license file into. Then stop the container.

```bash
mkdir -p ./speech-licenses/stt ./speech-licenses/tts

docker run --rm \
  -v $(pwd)/speech-licenses/stt:/license \
  mcr.microsoft.com/azure-cognitive-services/speechservices/speech-to-text:5.1.0-amd64-en-us \
  Eula=accept \
  Billing="$SPEECH_BILLING" \
  ApiKey="$SPEECH_API_KEY" \
  DownloadLicense=True \
  Mounts:License=/license

docker run --rm \
  -v $(pwd)/speech-licenses/tts:/license \
  mcr.microsoft.com/azure-cognitive-services/speechservices/neural-text-to-speech:3.11.0-amd64-en-us-jennyneural \
  Eula=accept \
  Billing="$SPEECH_BILLING" \
  ApiKey="$SPEECH_API_KEY" \
  DownloadLicense=True \
  Mounts:License=/license
```

### Disconnected run args

For each container, replace the `Billing`/`ApiKey` envs with the license mount:

```yaml
# overrides for docker-compose.local.yml in disconnected mode
services:
  speech-stt:
    environment:
      - Eula=accept
      - Mounts:License=/license
    volumes:
      - ./speech-licenses/stt:/license:ro
  speech-tts:
    environment:
      - Eula=accept
      - Mounts:License=/license
    volumes:
      - ./speech-licenses/tts:/license:ro
```

Renew the license every ~30 days by re-running `DownloadLicense=True` on a host that has internet.

Microsoft Learn reference: [Use containers in disconnected environments](https://learn.microsoft.com/azure/ai-services/containers/disconnected-containers).

---

## 4. Install and warm Foundry Local

**Windows:**

```pwsh
winget install Microsoft.FoundryLocal
foundry --version
foundry model download qwen2.5-7b-instruct    # ~5 GB
foundry service start                          # binds an OpenAI-compatible /v1 endpoint
foundry service status                         # prints the URL — e.g. http://localhost:5273
```

**macOS:**

```bash
brew install foundrylocal
foundry --version
foundry model download qwen2.5-7b-instruct
foundry service start
foundry service status
```

**Linux (vLLM substitute):**

If you can't use Foundry Local on Linux, vLLM gives you an OpenAI-compatible endpoint:

```bash
pip install "vllm>=0.6"
vllm serve Qwen/Qwen2.5-7B-Instruct \
  --port 5273 \
  --served-model-name qwen2.5-7b-instruct \
  --max-model-len 4096
```

Validate Foundry Local (or your substitute):

```bash
curl -sS http://localhost:5273/v1/models | head -c 200 ; echo

curl -sS http://localhost:5273/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
        "model": "qwen2.5-7b-instruct",
        "messages": [{"role":"user","content":"Say hi in one short sentence."}],
        "max_tokens": 32
      }' | head -c 400 ; echo
```

---

## 5. Point the app at the local stack

Edit the app's `.env` (the project root one, not the compose one):

```env
ENABLE_LOCAL_FALLBACK=true

LOCAL_STT_ENDPOINT=http://localhost:5001
LOCAL_TTS_ENDPOINT=http://localhost:5002
LOCAL_TTS_VOICE=en-US-JennyNeural
LOCAL_LLM_ENDPOINT=http://localhost:5273/v1
LOCAL_LLM_MODEL=qwen2.5-7b-instruct
```

Then start the app as usual:

```pwsh
python app.py
```

Force a local-mode session for testing:

```pwsh
$env:FORCE_LOCAL_MODE = "true"
python app.py
```

Then open `http://localhost:8000` — you should see the orange **LOCAL** badge in the status bar after clicking *Start Avatar*.

---

## 6. Operational notes

- **Container restarts.** The compose file uses `restart: unless-stopped` — a container that crashes will come back automatically.
- **Voice variants.** Each NTTS voice is its own image. Pull additional tags and bind to different ports if you want multi-voice support (we currently only pass one voice to the app — `LOCAL_TTS_VOICE`).
- **Pinning.** Replace `:latest` (which we don't use) and the pinned tags in `docker-compose.local.yml` only after you've validated the new image in a lab — Microsoft does ship breaking changes between minor versions occasionally.
- **Logs.** STT logs include the recognized text by default. Decide whether that's acceptable on the host or whether you want to mount `/var/log/<service>` and run it through your SIEM.
- **GPU for Foundry Local.** Foundry Local auto-detects CUDA / DirectML / Metal — no extra flags needed once a compatible driver is installed.
