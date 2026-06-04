/**
 * Azure AI Voice Live API with Avatar — browser client.
 *
 * Two modes:
 *   Avatar:     WebRTC video/audio from Azure, mic audio via WebSocket.
 *   Voice-only: Audio played back via WebSocket PCM16, mic via WebSocket.
 *
 * Protocol (Browser → Backend):
 *   start_session, stop_session, audio_chunk, send_text, avatar_sdp_offer, interrupt
 *
 * Protocol (Backend → Browser):
 *   session_started, ice_servers, avatar_sdp_answer, transcript_delta,
 *   transcript_done, response_created, response_done, speech_started,
 *   speech_stopped, audio_data, audio_done, error, session_error
 */

// ── DOM Elements ────────────────────────────────────────────────────────────
const $ = (sel) => document.querySelector(sel);
const avatarVideo = $("#avatarVideo");
const avatarAudio = $("#avatarAudio");
const videoPlaceholder = $("#videoPlaceholder");
const statusBar = $("#statusBar");
const statusText = $("#statusText");
const chatMessages = $("#chatMessages");
const chatInput = $("#chatInput");
const sendBtn = $("#sendBtn");
const micBtn = $("#micBtn");
const connectBtn = $("#connectBtn");
const characterSelect = $("#characterSelect");
const styleSelect = $("#styleSelect");
const voiceSelect = $("#voiceSelect");
const errorCard = $("#errorCard");
const errorText = $("#errorText");
const avatarToggle = $("#avatarEnabled");
const avatarType = $("#avatarType");
const styleLabel = $("#styleLabel");

// Photo avatars injected from server template
const photoAvatars = window.__PHOTO_AVATARS__ || [];

// Mode badge / notice
const modeBadge = $("#modeBadge");
const modeNotice = $("#modeNotice");
const modeNoticeReason = $("#modeNoticeReason");

// ── State ───────────────────────────────────────────────────────────────────
let ws = null;
let peerConnection = null;
let audioContext = null;
let micStream = null;
let micNode = null;
let isRecording = false;
let currentStatus = "disconnected";
let sessionStarted = false;
let currentAssistantDiv = null;
let currentAssistantText = "";
let currentUserDiv = null;
let currentUserText = "";
let userLatitude = null;
let userLongitude = null;
let currentMode = "cloud"; // "cloud" or "local" — set from session_started

// ── Geolocation ─────────────────────────────────────────────────────────────
// Request the user's location on page load so weather queries can use it.
(function requestGeolocation() {
  if (!navigator.geolocation) {
    console.warn("Geolocation API not available");
    return;
  }
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      userLatitude = pos.coords.latitude;
      userLongitude = pos.coords.longitude;
      console.log(`User location: ${userLatitude}, ${userLongitude}`);
    },
    (err) => {
      console.warn("Geolocation denied or unavailable:", err.message);
    },
    { enableHighAccuracy: false, timeout: 10000, maximumAge: 300000 }
  );
})();

// System prompt injected from the server template
const systemPrompt = window.__SYSTEM_PROMPT__ || "";

// ── Status management ───────────────────────────────────────────────────────
const STATUS_LABELS = {
  disconnected: "Disconnected",
  connecting: "Connecting…",
  connected: "Connected — Ready",
  speaking: "Speaking…",
  listening: "Listening…",
  error: "Error",
};

function setStatus(status) {
  currentStatus = status;
  statusBar.className = `status-bar status-${status}`;
  statusText.textContent = STATUS_LABELS[status] || status;

  const isActive = ["connected", "speaking", "listening"].includes(status);
  // In local mode the avatar pane is never used.
  const showVideo = isActive && currentMode === "cloud" && avatarToggle.checked;
  avatarVideo.style.display = showVideo ? "block" : "none";
  videoPlaceholder.style.display = showVideo ? "none" : "flex";

  chatInput.disabled = !isActive;
  sendBtn.disabled = !isActive;
  micBtn.disabled = !isActive;

  if (isActive) {
    connectBtn.textContent = "Disconnect";
    connectBtn.className = "btn-danger";
    connectBtn.disabled = false;
    setSettingsDisabled(true);
  } else if (status === "connecting") {
    connectBtn.textContent = "Connecting…";
    connectBtn.className = "btn-primary";
    connectBtn.disabled = true;
    setSettingsDisabled(true);
  } else {
    connectBtn.textContent = "Start Avatar";
    connectBtn.className = "btn-primary";
    connectBtn.disabled = false;
    setSettingsDisabled(false);
  }
}

function setSettingsDisabled(disabled) {
  avatarType.disabled = disabled;
  characterSelect.disabled = disabled;
  styleSelect.disabled = disabled;
  voiceSelect.disabled = disabled;
  avatarToggle.disabled = disabled;
}

function applyModeUI(mode, reason) {
  // Render the CLOUD/LOCAL badge and surface the fallback banner.
  if (!modeBadge) return;
  modeBadge.style.display = "inline-block";
  if (mode === "local") {
    modeBadge.textContent = "LOCAL";
    modeBadge.className = "mode-badge mode-local";
    if (modeNotice) {
      modeNotice.style.display = "block";
      if (modeNoticeReason) {
        modeNoticeReason.textContent = reason ? `(${reason})` : "";
      }
    }
  } else {
    modeBadge.textContent = "CLOUD";
    modeBadge.className = "mode-badge mode-cloud";
    if (modeNotice) modeNotice.style.display = "none";
  }
}

function showError(msg) {
  errorCard.style.display = "block";
  errorText.textContent = msg;
}

function clearError() {
  errorCard.style.display = "none";
  errorText.textContent = "";
}

// ── Character / Style dropdown sync ─────────────────────────────────────────

// Store original video character options from the server-rendered HTML
const videoCharacterOptions = characterSelect.innerHTML;

function populateCharacters() {
  const type = avatarType.value;
  if (type === "photo") {
    // Photo avatars — no styles. Pre-select the configured default.
    const defaultId = window.__DEFAULT_PHOTO_CHARACTER__ || "";
    characterSelect.innerHTML = photoAvatars
      .map((a) => `<option value="${a.id}"${a.id === defaultId ? " selected" : ""}>${a.name}</option>`)
      .join("");
    styleSelect.innerHTML = "";
    styleLabel.style.display = "none";
  } else {
    // Video avatars — restore original options (default already marked in HTML)
    characterSelect.innerHTML = videoCharacterOptions;
    styleLabel.style.display = "";
    populateStyles();
  }
}

function populateStyles() {
  const selected = characterSelect.selectedOptions[0];
  const styles = (selected && selected.dataset.styles)
    ? selected.dataset.styles.split(",").filter(Boolean)
    : [];

  if (styles.length === 0) {
    // Avatar has no style variants — hide the dropdown entirely
    styleSelect.innerHTML = "";
    styleLabel.style.display = "none";
    return;
  }

  styleLabel.style.display = "";
  styleSelect.innerHTML = styles
    .map((s) => `<option value="${s}">${s}</option>`)
    .join("");
}

avatarType.addEventListener("change", populateCharacters);
characterSelect.addEventListener("change", populateStyles);
populateCharacters();

// ── Helpers ─────────────────────────────────────────────────────────────────
function arrayBufferToBase64(buffer) {
  const bytes = new Uint8Array(buffer);
  let binary = "";
  for (let i = 0; i < bytes.length; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary);
}

function wsSend(obj) {
  if (ws && ws.readyState === WebSocket.OPEN) {
    ws.send(JSON.stringify(obj));
  }
}

// ── Voice Live session ──────────────────────────────────────────────────────
async function startSession() {
  setStatus("connecting");
  clearError();

  try {
    const protocol = location.protocol === "https:" ? "wss:" : "ws:";
    ws = new WebSocket(`${protocol}//${location.host}/ws/voicelive`);

    ws.binaryType = "arraybuffer";

    ws.onopen = () => {
      console.log("WebSocket connected — sending start_session");

      // Send start_session with configuration for the backend to set up
      const voiceName = voiceSelect.value;
      const avatarOn = avatarToggle.checked;
      const sessionConfig = {
        character: characterSelect.value,
        style: styleSelect.value || "",
        avatarType: avatarType.value,
        voiceName: voiceName,
        instructions: systemPrompt,
        avatarEnabled: avatarOn,
      };
      // Attach user coordinates if the browser provided them
      if (userLatitude !== null && userLongitude !== null) {
        sessionConfig.userLatitude = userLatitude;
        sessionConfig.userLongitude = userLongitude;
      }
      wsSend({ type: "start_session", config: sessionConfig });
    };

    ws.onmessage = (event) => {
      if (typeof event.data === "string") {
        handleServerMessage(JSON.parse(event.data));
      }
    };

    ws.onerror = (err) => {
      console.error("WebSocket error:", err);
      showError("WebSocket connection failed");
      setStatus("error");
    };

    ws.onclose = (event) => {
      console.log("WebSocket closed:", event.code, event.reason);
      if (currentStatus !== "disconnected") {
        setStatus("disconnected");
      }
    };
  } catch (err) {
    console.error("Session start error:", err);
    showError(err.message);
    setStatus("error");
  }
}

// ── Server message handler ──────────────────────────────────────────────────
async function handleServerMessage(msg) {
  console.log("Server message:", msg.type);

  switch (msg.type) {
    case "session_started":
      console.log("Session started:", msg.sessionId, "mode:", msg.mode);
      sessionStarted = true;
      currentMode = msg.mode || "cloud";
      applyModeUI(currentMode, null);
      // In voice-only / local mode, mark connected immediately (no WebRTC handshake)
      if (currentMode === "local" || !avatarToggle.checked) {
        setStatus("connected");
      }
      break;

    case "mode_notice":
      applyModeUI(msg.mode || currentMode, msg.reason || null);
      break;

    case "ice_servers":
      // Backend extracted ICE servers from session.updated and sent them
      // Only relevant when avatar is enabled
      console.log("Received ICE servers:", msg.iceServers?.length);
      if (avatarToggle.checked && msg.iceServers && msg.iceServers.length > 0) {
        await setupAvatarWebRTC(msg.iceServers);
      } else if (!avatarToggle.checked) {
        console.log("Avatar disabled — skipping WebRTC setup");
      } else {
        console.warn("No ICE servers received — cannot set up avatar WebRTC");
        showError("No ICE servers received from service");
      }
      break;

    case "avatar_sdp_answer":
      // Server SDP is base64-encoded JSON: {"type":"answer","sdp":"..."}
      if (peerConnection && msg.serverSdp) {
        try {
          const serverSdpJson = atob(msg.serverSdp);
          const serverSdpObj = JSON.parse(serverSdpJson);
          await peerConnection.setRemoteDescription(
            new RTCSessionDescription(serverSdpObj)
          );
          console.log("Avatar WebRTC remote description set");
          setStatus("connected");
        } catch (e) {
          console.error("Failed to parse server SDP:", e);
          showError("Avatar WebRTC handshake failed");
        }
      }
      break;

    case "transcript_delta":
      if (msg.role === "assistant" && msg.delta) {
        appendAssistantDelta(msg.delta);
      } else if (msg.role === "user" && msg.delta) {
        appendUserDelta(msg.delta);
      }
      break;

    case "transcript_done":
      if (msg.role === "user" && msg.transcript) {
        finalizeUserMessage(msg.transcript);
      } else if (msg.role === "assistant") {
        finalizeAssistantMessage();
      }
      break;

    case "response_created":
      setStatus("speaking");
      break;

    case "response_done":
      if (currentStatus === "speaking") {
        setStatus(isRecording ? "listening" : "connected");
      }
      break;

    case "speech_started":
      setStatus("listening");
      // Barge-in: cancel ongoing response
      finalizeAssistantMessage();
      wsSend({ type: "interrupt" });
      break;

    case "speech_stopped":
      break;

    case "session_error":
      console.error("Session error:", msg.error);
      showError(msg.error || "Session error");
      setStatus("error");
      break;

    case "error":
      console.error("Voice Live error:", msg.error);
      showError(typeof msg.error === "string" ? msg.error : JSON.stringify(msg.error));
      break;

    case "stop_playback":
      break;

    case "audio_data":
      // Voice-only mode: play audio through browser
      handleAudioPlayback(msg.data);
      break;

    case "audio_done":
      break;

    default:
      console.log("Unhandled message:", msg.type);
      break;
  }
}

// ── Avatar WebRTC ───────────────────────────────────────────────────────────
async function setupAvatarWebRTC(iceServers) {
  const rtcIceServers = iceServers.map((s) => ({
    urls: s.urls,
    username: s.username || undefined,
    credential: s.credential || undefined,
  }));

  console.log("Setting up WebRTC with", rtcIceServers.length, "ICE server(s)");

  peerConnection = new RTCPeerConnection({ iceServers: rtcIceServers });

  peerConnection.ontrack = (event) => {
    console.log("WebRTC track received:", event.track.kind);
    if (event.track.kind === "video") {
      avatarVideo.srcObject = event.streams[0];
    }
    if (event.track.kind === "audio") {
      avatarAudio.srcObject = event.streams[0];
    }
  };

  peerConnection.oniceconnectionstatechange = () => {
    console.log("ICE connection state:", peerConnection.iceConnectionState);
    if (
      peerConnection.iceConnectionState === "disconnected" ||
      peerConnection.iceConnectionState === "failed"
    ) {
      console.warn("Avatar WebRTC connection lost");
    }
  };

  // ICE gathering via onicecandidate — null candidate signals completion
  let iceGatheringDone = false;
  peerConnection.onicecandidate = (event) => {
    if (event.candidate) {
      console.log("ICE candidate:", event.candidate.type, event.candidate.protocol);
    } else if (!iceGatheringDone) {
      iceGatheringDone = true;
      console.log("ICE gathering complete (null candidate)");
      sendSdpOffer();
    }
  };

  // Transceivers: sendrecv (matching reference sample)
  peerConnection.addTransceiver("video", { direction: "sendrecv" });
  peerConnection.addTransceiver("audio", { direction: "sendrecv" });

  // Data channel (required by reference sample)
  peerConnection.createDataChannel("eventChannel");
  peerConnection.addEventListener("datachannel", (event) => {
    const dc = event.channel;
    dc.onmessage = (e) => console.log("WebRTC data channel message:", e.data);
    dc.onclose = () => console.log("Data channel closed");
  });

  // Create offer and set local description — ICE gathering starts automatically
  const offer = await peerConnection.createOffer();
  await peerConnection.setLocalDescription(offer);

  // Timeout fallback: send SDP after 10s even if ICE gathering hasn't completed
  setTimeout(() => {
    if (!iceGatheringDone) {
      iceGatheringDone = true;
      console.warn("ICE gathering timed out after 10s, sending SDP with available candidates");
      sendSdpOffer();
    }
  }, 10000);

  function sendSdpOffer() {
    // SDP must be base64-encoded JSON (matching reference sample format)
    const sdpJson = JSON.stringify(peerConnection.localDescription);
    const sdpBase64 = btoa(sdpJson);
    const rawSdp = peerConnection.localDescription.sdp;
    const candidateCount = (rawSdp.match(/a=candidate/g) || []).length;
    console.log(`Sending SDP offer: ${rawSdp.length} bytes, ${candidateCount} candidates (base64: ${sdpBase64.length} chars)`);

    wsSend({
      type: "avatar_sdp_offer",
      clientSdp: sdpBase64,
    });
  }
}

// ── Chat messages ───────────────────────────────────────────────────────────
function addMessage(role, text) {
  const welcome = chatMessages.querySelector(".chat-welcome");
  if (welcome) welcome.remove();

  const div = document.createElement("div");
  div.className = `chat-msg ${role}`;
  div.textContent = text;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
  return div;
}

function appendAssistantDelta(delta) {
  if (!currentAssistantDiv) {
    const welcome = chatMessages.querySelector(".chat-welcome");
    if (welcome) welcome.remove();

    currentAssistantDiv = document.createElement("div");
    currentAssistantDiv.className = "chat-msg assistant";
    chatMessages.appendChild(currentAssistantDiv);
    currentAssistantText = "";
  }
  currentAssistantText += delta;
  currentAssistantDiv.textContent = currentAssistantText;
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function finalizeAssistantMessage() {
  currentAssistantDiv = null;
  currentAssistantText = "";
}

function appendUserDelta(delta) {
  if (!currentUserDiv) {
    const welcome = chatMessages.querySelector(".chat-welcome");
    if (welcome) welcome.remove();

    currentUserDiv = document.createElement("div");
    currentUserDiv.className = "chat-msg user streaming";
    chatMessages.appendChild(currentUserDiv);
    currentUserText = "";
  }
  currentUserText += delta;
  currentUserDiv.textContent = currentUserText;
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function finalizeUserMessage(fullTranscript) {
  // Replace partial deltas with the authoritative completed transcript
  // (the deltas can be slightly off vs. the final result).
  if (currentUserDiv) {
    currentUserDiv.textContent = fullTranscript;
    currentUserDiv.classList.remove("streaming");
  } else {
    addMessage("user", fullTranscript);
  }
  currentUserDiv = null;
  currentUserText = "";
}

// ── Send text message ───────────────────────────────────────────────────────
function sendTextMessage(text) {
  if (!text.trim() || !ws) return;

  chatInput.value = "";
  addMessage("user", text);

  wsSend({
    type: "send_text",
    text: text,
  });
}

// ── Microphone handling ─────────────────────────────────────────────────────
async function startMicrophone() {
  try {
    audioContext = new AudioContext({ sampleRate: 24000 });

    micStream = await navigator.mediaDevices.getUserMedia({
      audio: {
        channelCount: 1,
        echoCancellation: false,
        noiseSuppression: false,
        autoGainControl: true,
      },
    });

    await audioContext.audioWorklet.addModule("/static/js/audio-processor.js");

    const source = audioContext.createMediaStreamSource(micStream);
    micNode = new AudioWorkletNode(audioContext, "mic-processor");

    micNode.port.onmessage = (event) => {
      const base64 = arrayBufferToBase64(event.data);
      wsSend({
        type: "audio_chunk",
        data: base64,
      });
    };

    source.connect(micNode);

    isRecording = true;
    micBtn.classList.add("recording");
    setStatus("listening");
  } catch (err) {
    console.error("Microphone error:", err);
    showError("Microphone access failed: " + err.message);
  }
}

function stopMicrophone() {
  if (micNode) {
    micNode.disconnect();
    micNode = null;
  }
  if (micStream) {
    micStream.getTracks().forEach((t) => t.stop());
    micStream = null;
  }
  if (audioContext) {
    audioContext.close();
    audioContext = null;
  }
  isRecording = false;
  micBtn.classList.remove("recording");
  if (currentStatus === "listening") setStatus("connected");
}

function toggleMicrophone() {
  if (isRecording) {
    stopMicrophone();
  } else {
    startMicrophone();
  }
}

// ── Cleanup ─────────────────────────────────────────────────────────────────
async function endSession() {
  stopMicrophone();

  if (ws) {
    wsSend({ type: "stop_session" });
    ws.close();
    ws = null;
  }
  if (peerConnection) {
    peerConnection.close();
    peerConnection = null;
  }

  avatarVideo.srcObject = null;
  avatarAudio.srcObject = null;

  sessionStarted = false;
  currentAssistantDiv = null;
  currentAssistantText = "";
  currentUserDiv = null;
  currentUserText = "";
  currentMode = "cloud";
  if (modeBadge) modeBadge.style.display = "none";
  if (modeNotice) modeNotice.style.display = "none";

  setStatus("disconnected");
  clearError();
}

// ── Event listeners ─────────────────────────────────────────────────────────
connectBtn.addEventListener("click", () => {
  if (["connected", "speaking", "listening"].includes(currentStatus)) {
    endSession();
  } else {
    startSession();
  }
});

sendBtn.addEventListener("click", () => {
  sendTextMessage(chatInput.value.trim());
});

chatInput.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey) {
    e.preventDefault();
    sendTextMessage(chatInput.value.trim());
  }
});

micBtn.addEventListener("click", toggleMicrophone);

window.addEventListener("beforeunload", () => {
  endSession();
});

// ── Voice-only audio playback ───────────────────────────────────────────────
let playbackContext = null;
let nextPlaybackTime = 0;

function base64ToArrayBuffer(base64) {
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return bytes.buffer;
}

function handleAudioPlayback(base64Data) {
  if (!base64Data) return;
  if (!playbackContext) {
    playbackContext = new AudioContext({ sampleRate: 24000 });
    nextPlaybackTime = 0;
  }
  const arrayBuffer = base64ToArrayBuffer(base64Data);
  const int16 = new Int16Array(arrayBuffer);
  const float32 = new Float32Array(int16.length);
  for (let i = 0; i < int16.length; i++) {
    float32[i] = int16[i] / 32768;
  }
  const buffer = playbackContext.createBuffer(1, float32.length, 24000);
  buffer.getChannelData(0).set(float32);
  const source = playbackContext.createBufferSource();
  source.buffer = buffer;
  source.connect(playbackContext.destination);

  const now = playbackContext.currentTime;
  if (nextPlaybackTime < now) nextPlaybackTime = now;
  source.start(nextPlaybackTime);
  nextPlaybackTime += buffer.duration;
}
