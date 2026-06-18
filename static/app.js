const state = {
  keys: new Set(),
  drive: 0,
  steer: 0,
  speed: 100,
  connected: false,
  armed: false,
};

const $ = (id) => document.getElementById(id);
const controlButtons = [...document.querySelectorAll(".control")];

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || "Request failed");
  return data;
}

function deriveControls() {
  state.drive = state.keys.has("w") ? 1 : state.keys.has("s") ? -1 : 0;
  state.steer = state.keys.has("a") ? -1 : state.keys.has("d") ? 1 : 0;
  controlButtons.forEach((button) => {
    const drive = Number(button.dataset.drive || 0);
    const steer = Number(button.dataset.steer || 0);
    button.classList.toggle(
      "active",
      (drive && drive === state.drive) || (steer && steer === state.steer),
    );
  });
}

async function sendControls() {
  if (!state.connected) return;
  try {
    await api("/api/control", {
      method: "POST",
      body: JSON.stringify({
        drive: state.drive,
        steer: state.steer,
        speed: state.speed,
      }),
    });
  } catch (error) {
    $("message").textContent = error.message;
  }
}

function setKey(key, pressed) {
  if (!["w", "a", "s", "d"].includes(key)) return;
  if (!state.armed && pressed) return;
  if (pressed) state.keys.add(key);
  else state.keys.delete(key);
  deriveControls();
  sendControls();
}

document.addEventListener("keydown", (event) => {
  if (event.repeat) return;
  setKey(event.key.toLowerCase(), true);
});
document.addEventListener("keyup", (event) => setKey(event.key.toLowerCase(), false));
window.addEventListener("blur", () => {
  state.keys.clear();
  deriveControls();
  sendControls();
});
document.addEventListener("visibilitychange", () => {
  if (document.hidden) {
    state.keys.clear();
    deriveControls();
    sendControls();
  }
});

controlButtons.forEach((button) => {
  const key = button.dataset.drive === "1" ? "w"
    : button.dataset.drive === "-1" ? "s"
    : button.dataset.steer === "-1" ? "a" : "d";
  button.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    button.setPointerCapture(event.pointerId);
    setKey(key, true);
  });
  ["pointerup", "pointercancel", "lostpointercapture"].forEach((name) => {
    button.addEventListener(name, () => setKey(key, false));
  });
});

$("speedSlider").addEventListener("input", (event) => {
  state.speed = Number(event.target.value);
  $("speedValue").textContent = state.speed;
  sendControls();
});

$("connectButton").addEventListener("click", async () => {
  $("message").textContent = "Connecting to motors 1 and 2…";
  try {
    const status = await api("/api/connect", { method: "POST" });
    render(status);
    $("message").textContent = "Connected. Arm captures the current steering angle as straight.";
  } catch (error) {
    $("message").textContent = error.message;
  }
});

$("armButton").addEventListener("click", async () => {
  try {
    const status = await api("/api/arm", { method: "POST" });
    render(status);
    $("message").textContent = "Armed. Hold W/S to drive and A/D to steer.";
  } catch (error) {
    $("message").textContent = error.message;
  }
});

$("stopButton").addEventListener("click", async () => {
  state.keys.clear();
  deriveControls();
  const status = await api("/api/disarm", { method: "POST" });
  render(status);
  $("message").textContent = "Motors disarmed.";
});

$("centerButton").addEventListener("click", async () => {
  try {
    await api("/api/center", { method: "POST" });
  } catch (error) {
    $("message").textContent = error.message;
  }
});

function render(status) {
  state.connected = status.connected;
  state.armed = status.armed;
  $("connectionBadge").textContent = status.connected ? "CONNECTED" : "OFFLINE";
  $("connectionBadge").className = `badge ${status.connected ? "online" : "offline"}`;
  $("armButton").disabled = !status.connected || status.armed;
  $("connectButton").disabled = status.connected;
  $("driveReadout").textContent = `${status.drive_speed_deg_s.toFixed(1)}°/s`;
  $("steeringReadout").textContent = `${status.steering_deg.toFixed(1)}°`;
  $("safetyReadout").textContent = status.armed ? "ARMED" : "DISARMED";
  const gaugePercent = Math.max(0, Math.min(100, 50 + status.steering_deg / 120 * 100));
  $("gaugeNeedle").style.left = `${gaugePercent}%`;
  if (status.error) $("message").textContent = status.error;
}

setInterval(() => {
  if (state.connected) sendControls();
}, 100);

setInterval(async () => {
  try {
    render(await api("/api/status"));
  } catch (_) {
    state.connected = false;
  }
}, 200);

api("/api/status").then(render);
