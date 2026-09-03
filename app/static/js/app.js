/* Vélib' GBFS Demo App — frontend with auth */
const DEFAULT_LAT = 48.8566;
const DEFAULT_LON = 2.3522;
const NEARBY_RADIUS_KM = 3;
const REFRESH_MS = 30000;
const TOKEN_KEY = "velib_auth_token";
const USER_KEY = "velib_user";

let map, userMarker, stationLayer, usersLayer;
let ws, clientId, userLat, userLon;
let chatTargetId = null;
let chatTargetName = null;
let mapFittedOnce = false;
let refreshTimer = null;
const stationMarkers = new Map();

const authScreen = document.getElementById("authScreen");
const appScreen = document.getElementById("appScreen");
const authError = document.getElementById("authError");
const displayNameLabel = document.getElementById("displayNameLabel");
const statusEl = document.getElementById("connectionStatus");
const stationListEl = document.getElementById("stationList");
const userListEl = document.getElementById("userList");
const stationCountEl = document.getElementById("stationCount");
const userCountEl = document.getElementById("userCount");
const chatPanel = document.getElementById("chatPanel");
const chatMessages = document.getElementById("chatMessages");
const chatTargetEl = document.getElementById("chatTarget");

function getToken() {
  return localStorage.getItem(TOKEN_KEY);
}

function getStoredUser() {
  try {
    return JSON.parse(localStorage.getItem(USER_KEY) || "null");
  } catch {
    return null;
  }
}

function saveAuth(token, user) {
  localStorage.setItem(TOKEN_KEY, token);
  localStorage.setItem(USER_KEY, JSON.stringify(user));
}

function clearAuth() {
  localStorage.removeItem(TOKEN_KEY);
  localStorage.removeItem(USER_KEY);
}

function authHeaders() {
  const token = getToken();
  return token ? { Authorization: `Bearer ${token}` } : {};
}

function showAuthError(msg) {
  authError.textContent = msg;
  authError.classList.remove("hidden");
}

function hideAuthError() {
  authError.classList.add("hidden");
}

function showAuthScreen() {
  authScreen.classList.remove("hidden");
  appScreen.classList.add("hidden");
}

function showAppScreen(user) {
  authScreen.classList.add("hidden");
  appScreen.classList.remove("hidden");
  displayNameLabel.textContent = user.display_name || user.username;
}

function bikeColor(bikes) {
  if (bikes == null) return "#8b9cb3";
  if (bikes === 0) return "#e17055";
  if (bikes <= 3) return "#fdcb6e";
  return "#00b894";
}

function initMap(lat, lon) {
  map = L.map("map").setView([lat, lon], 12);
  L.tileLayer("https://{s}.tile.openstreetmap.org/{z}/{x}/{y}.png", {
    attribution: "© OpenStreetMap",
    maxZoom: 19,
  }).addTo(map);
  stationLayer = L.layerGroup().addTo(map);
  usersLayer = L.layerGroup().addTo(map);
  userMarker = L.circleMarker([lat, lon], {
    radius: 10,
    color: "#0984e3",
    fillColor: "#0984e3",
    fillOpacity: 0.9,
  }).addTo(map).bindPopup("Vous");
}

function renderAllStationsOnMap(stations, nearbyIds) {
  stationLayer.clearLayers();
  stationMarkers.clear();
  const bounds = [];

  stations.forEach((s) => {
    const bikes = s.num_bikes_available ?? "?";
    const docks = s.num_docks_available ?? "?";
    const color = bikeColor(s.num_bikes_available);
    const isNearby = nearbyIds.has(s.station_id);
    const distLabel = s.distance_km != null ? `${s.distance_km} km` : "";

    const marker = L.circleMarker([s.lat, s.lon], {
      radius: isNearby ? 8 : 5,
      color,
      fillColor: color,
      fillOpacity: isNearby ? 0.9 : 0.45,
      weight: isNearby ? 2 : 1,
    });
    marker.bindPopup(
      `<strong>${s.name || "Station"}</strong><br>` +
        `Vélos: <b>${bikes}</b> · Docks: ${docks}<br>` +
        `Capacité: ${s.capacity ?? "—"}` +
        (distLabel ? `<br>Distance: ${distLabel}` : "")
    );
    marker.addTo(stationLayer);
    stationMarkers.set(s.station_id, marker);
    bounds.push([s.lat, s.lon]);
  });

  if (map) {
    setTimeout(() => map.invalidateSize(), 0);
  }
}

function renderNearbyList(nearby, all, hasLocation) {
  stationListEl.innerHTML = "";
  stationCountEl.textContent = nearby.length;

  if (nearby.length === 0 && hasLocation && all.length > 0) {
    const closest = [...all]
      .filter((s) => s.distance_km != null)
      .sort((a, b) => a.distance_km - b.distance_km)
      .slice(0, 15);

    const msg = document.createElement("p");
    msg.className = "hint list-hint";
    msg.textContent =
      "Aucune station Vélib' à proximité (réseau Paris). Stations les plus proches :";
    stationListEl.appendChild(msg);
    stationCountEl.textContent = closest.length;

    closest.forEach((s) => appendStationCard(s));
    return;
  }

  if (nearby.length === 0) {
    const msg = document.createElement("p");
    msg.className = "hint list-hint";
    msg.textContent = "Cliquez « Utiliser ma position » pour voir les stations proches.";
    stationListEl.appendChild(msg);
    return;
  }

  nearby.forEach((s) => appendStationCard(s));
}

function appendStationCard(s) {
  const bikes = s.num_bikes_available ?? "?";
  const docks = s.num_docks_available ?? "?";
  const dist = s.distance_km != null ? `${s.distance_km} km` : "";
  const card = document.createElement("div");
  card.className = "card";
  card.innerHTML = `
    <h3>${s.name || "Station " + s.station_id}</h3>
    <p><span class="bikes">${bikes} vélos</span> · ${docks} docks${dist ? " · " + dist : ""}</p>
  `;
  card.onclick = () => {
    map.setView([s.lat, s.lon], 16);
    const marker = stationMarkers.get(s.station_id);
    if (marker) marker.openPopup();
  };
  stationListEl.appendChild(card);
}

function renderUsers(users) {
  usersLayer.clearLayers();
  userListEl.innerHTML = "";
  userCountEl.textContent = users.length;

  users.forEach((u) => {
    L.circleMarker([u.lat, u.lon], {
      radius: 7,
      color: "#74b9ff",
      fillColor: "#0984e3",
      fillOpacity: 0.7,
    })
      .bindPopup(`${u.name} (${u.distance_km} km)`)
      .addTo(usersLayer);

    const card = document.createElement("div");
    card.className = "card user-card";
    card.innerHTML = `
      <h3>${u.name}</h3>
      <p>À ${u.distance_km} km</p>
      <button class="btn contact-btn" data-id="${u.id}" data-name="${u.name}">Contacter</button>
    `;
    card.querySelector(".contact-btn").onclick = (e) => {
      e.stopPropagation();
      openChat(u.id, u.name);
    };
    userListEl.appendChild(card);
  });
}

async function loadStations() {
  let url = "/api/stations";
  if (userLat != null && userLon != null) {
    url += `?lat=${userLat}&lon=${userLon}&radius_km=${NEARBY_RADIUS_KM}`;
  }
  const res = await fetch(url, { headers: authHeaders() });
  if (res.status === 401) {
    handleUnauthorized();
    return;
  }
  if (!res.ok) {
    statusEl.textContent = "Erreur chargement stations";
    statusEl.className = "status err";
    return;
  }
  const data = await res.json();
  const all = data.stations || [];
  const hasLocation = userLat != null && userLon != null;
  const nearby = hasLocation ? (data.nearby || []) : all;
  const nearbyIds = new Set(nearby.map((s) => s.station_id));

  renderAllStationsOnMap(all, nearbyIds);
  renderNearbyList(nearby, all, hasLocation);

  const total = data.count ?? all.length;
  const near = data.nearby_count ?? nearby.length;
  statusEl.textContent = `MongoDB · ${near} proches / ${total} stations · maj ${new Date().toLocaleTimeString()}`;
  statusEl.className = "status ok";

  if (map && all.length > 0) {
    if (near === 0 && hasLocation) {
      const bounds = all.map((s) => [s.lat, s.lon]);
      map.fitBounds(bounds, { padding: [30, 30], maxZoom: 12 });
    } else if (!mapFittedOnce) {
      const bounds = all.map((s) => [s.lat, s.lon]);
      map.fitBounds(bounds, { padding: [30, 30], maxZoom: 13 });
      mapFittedOnce = true;
    }
  }
}

function sendPresence() {
  if (!ws || ws.readyState !== WebSocket.OPEN || userLat == null) return;
  ws.send(JSON.stringify({ type: "presence", lat: userLat, lon: userLon }));
}

function connectWebSocket() {
  const token = getToken();
  if (!token) return;

  const proto = location.protocol === "https:" ? "wss" : "ws";
  ws = new WebSocket(`${proto}://${location.host}/ws?token=${encodeURIComponent(token)}`);

  ws.onopen = () => {
    statusEl.textContent = "Connecté";
    statusEl.className = "status ok";
    sendPresence();
  };

  ws.onmessage = (event) => {
    const data = JSON.parse(event.data);
    if (data.type === "welcome") clientId = data.client_id;
    if (data.type === "users") renderUsers(data.users || []);
    if (data.type === "message") {
      if (chatPanel.classList.contains("hidden") || data.from_id !== chatTargetId) {
        openChat(data.from_id, data.from_name);
      }
      addChatMessage(data.from_name, data.text, false);
    }
    if (data.type === "message_sent") {
      /* confirmation envoyée par le serveur */
    }
    if (data.type === "message_error") {
      addChatMessage("Système", data.text || "Message non délivré", false);
    }
  };

  ws.onclose = (event) => {
    if (event.code === 4401) {
      handleUnauthorized();
      return;
    }
    statusEl.textContent = "WebSocket déconnecté";
    statusEl.className = "status err";
    if (getToken()) setTimeout(connectWebSocket, 3000);
  };
}

function handleUnauthorized() {
  clearAuth();
  if (ws) {
    ws.close();
    ws = null;
  }
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
  showAuthScreen();
  showAuthError("Session expirée — reconnectez-vous.");
}

function openChat(id, name) {
  chatTargetId = id;
  chatTargetName = name;
  chatTargetEl.textContent = name;
  chatMessages.innerHTML = "";
  chatPanel.classList.remove("hidden");
}

function addChatMessage(from, text, sent) {
  const div = document.createElement("div");
  div.className = "msg";
  div.innerHTML = sent
    ? `<span class="from">Vous</span>: ${escapeHtml(text)}`
    : `<span class="from">${escapeHtml(from)}</span>: ${escapeHtml(text)}`;
  chatMessages.appendChild(div);
  chatMessages.scrollTop = chatMessages.scrollHeight;
}

function escapeHtml(s) {
  const d = document.createElement("div");
  d.textContent = s;
  return d.innerHTML;
}

function sendChat() {
  const input = document.getElementById("chatInput");
  const text = input.value.trim();
  if (!text || !chatTargetId || !ws) return;
  ws.send(JSON.stringify({ type: "message", to: chatTargetId, text }));
  addChatMessage("Vous", text, true);
  input.value = "";
}

function useLocation() {
  const hint = document.getElementById("locationHint");
  if (!navigator.geolocation) {
    hint.textContent = "Géolocalisation non supportée — centre Paris.";
    userLat = DEFAULT_LAT;
    userLon = DEFAULT_LON;
    ensureMapAt(userLat, userLon);
    loadStations();
    sendPresence();
    return;
  }

  hint.textContent = "Localisation en cours…";
  navigator.geolocation.getCurrentPosition(
    (pos) => {
      userLat = pos.coords.latitude;
      userLon = pos.coords.longitude;
      hint.textContent = `${userLat.toFixed(4)}, ${userLon.toFixed(4)}`;
      ensureMapAt(userLat, userLon);
      loadStations();
      sendPresence();
    },
    () => {
      hint.textContent = "GPS refusé — utilisation du centre Paris.";
      userLat = DEFAULT_LAT;
      userLon = DEFAULT_LON;
      ensureMapAt(userLat, userLon);
      loadStations();
      sendPresence();
    },
    { enableHighAccuracy: true }
  );
}

function ensureMapAt(lat, lon) {
  if (!map) initMap(lat, lon);
  else {
    userMarker.setLatLng([lat, lon]);
    map.invalidateSize();
  }
}

async function startApp(user) {
  showAppScreen(user);
  mapFittedOnce = false;

  try {
    const health = await fetch("/api/health");
    const h = await health.json();
    if (!h.ok) throw new Error(h.error || "MongoDB indisponible");
  } catch (e) {
    statusEl.textContent = "MongoDB hors ligne — lancez docker compose up";
    statusEl.className = "status err";
  }

  await new Promise((r) => requestAnimationFrame(r));
  initMap(DEFAULT_LAT, DEFAULT_LON);
  map.invalidateSize();

  connectWebSocket();
  useLocation();

  if (refreshTimer) clearInterval(refreshTimer);
  refreshTimer = setInterval(() => {
    loadStations();
    sendPresence();
  }, REFRESH_MS);
}

async function login(username, password) {
  hideAuthError();
  const res = await fetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await res.json();
  if (!res.ok) {
    showAuthError(data.detail || "Connexion impossible");
    return;
  }
  saveAuth(data.token, data.user);
  await startApp(data.user);
}

async function register(username, password, displayName) {
  hideAuthError();
  const body = { username, password };
  if (displayName) body.display_name = displayName;

  const res = await fetch("/api/auth/register", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  const data = await res.json();
  if (!res.ok) {
    showAuthError(data.detail || "Inscription impossible");
    return;
  }
  saveAuth(data.token, data.user);
  await startApp(data.user);
}

async function logout() {
  try {
    await fetch("/api/auth/logout", { method: "POST", headers: authHeaders() });
  } catch {
    /* ignore */
  }
  clearAuth();
  if (ws) {
    ws.close();
    ws = null;
  }
  if (refreshTimer) {
    clearInterval(refreshTimer);
    refreshTimer = null;
  }
  map = null;
  showAuthScreen();
}

function setupAuthTabs() {
  const tabs = document.querySelectorAll(".auth-tab");
  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("registerForm");

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      tabs.forEach((t) => t.classList.remove("active"));
      tab.classList.add("active");
      hideAuthError();
      if (tab.dataset.tab === "login") {
        loginForm.classList.remove("hidden");
        registerForm.classList.add("hidden");
      } else {
        loginForm.classList.add("hidden");
        registerForm.classList.remove("hidden");
      }
    });
  });
}

document.getElementById("loginForm").addEventListener("submit", (e) => {
  e.preventDefault();
  login(
    document.getElementById("loginUsername").value.trim(),
    document.getElementById("loginPassword").value
  );
});

document.getElementById("registerForm").addEventListener("submit", (e) => {
  e.preventDefault();
  register(
    document.getElementById("registerUsername").value.trim(),
    document.getElementById("registerPassword").value,
    document.getElementById("registerDisplayName").value.trim()
  );
});

document.getElementById("logoutBtn").addEventListener("click", logout);
document.getElementById("locateBtn").addEventListener("click", useLocation);
document.getElementById("chatSend").addEventListener("click", sendChat);
document.getElementById("chatInput").addEventListener("keydown", (e) => {
  if (e.key === "Enter") sendChat();
});
document.getElementById("chatClose").addEventListener("click", () => {
  chatPanel.classList.add("hidden");
  chatTargetId = null;
});

async function init() {
  setupAuthTabs();

  const token = getToken();
  if (!token) {
    showAuthScreen();
    return;
  }

  try {
    const res = await fetch("/api/auth/me", { headers: authHeaders() });
    if (!res.ok) {
      clearAuth();
      showAuthScreen();
      return;
    }
    const data = await res.json();
    saveAuth(token, data.user);
    await startApp(data.user);
  } catch {
    clearAuth();
    showAuthScreen();
  }
}

init();
