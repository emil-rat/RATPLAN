// RATPLAN simulation_tool -- a visual frontend over the real Scan/GP-correction pipeline. Terrain
// hillshade + roads rendering is copied verbatim from mapviz/frontend/app.js; the coverage-raster
// color ramp (MARGIN_COLOR_STOPS/marginToRgb/buildCoverageDataUrl) is ported from
// rattfallan-demo/scenario_builder/frontend/js/app.js so this tool's heatmap reads the same way that
// tool's does. Everything else (relay/observation placement, the click-mode state machine) is new,
// calling the real backend endpoints in server.py -- no scan/GP math lives in this file.

const statusEl = document.getElementById("status");

function setStatus(text) {
  statusEl.textContent = text;
}

// Shared by every image-source layer this app builds client-side (hillshade and the coverage
// raster) -- paints a canvas pixel-by-pixel via pixelAt(row, col) -> [r, g, b, a] and returns a data
// URL MapLibre's `image` source can use directly as its `url`.
function gridToDataUrl(nRows, nCols, pixelAt) {
  const canvas = document.createElement("canvas");
  canvas.width = nCols;
  canvas.height = nRows;
  const ctx = canvas.getContext("2d");
  const imgData = ctx.createImageData(nCols, nRows);
  for (let r = 0; r < nRows; r++) {
    for (let c = 0; c < nCols; c++) {
      const idx = (r * nCols + c) * 4;
      const [red, green, blue, alpha] = pixelAt(r, c);
      imgData.data[idx] = red;
      imgData.data[idx + 1] = green;
      imgData.data[idx + 2] = blue;
      imgData.data[idx + 3] = alpha;
    }
  }
  ctx.putImageData(imgData, 0, 0);
  return canvas.toDataURL();
}

function buildHillshadeDataUrl(hillshade) {
  const { n_rows, n_cols, intensity } = hillshade;
  return gridToDataUrl(n_rows, n_cols, (r, c) => {
    const v = intensity[r][c];
    return [v, v, v, 255];
  });
}

function boundsFromCorners(corners) {
  // corners: [nw, ne, se, sw], each [lon, lat]
  const lons = corners.map((c) => c[0]);
  const lats = corners.map((c) => c[1]);
  return [
    [Math.min(...lons), Math.min(...lats)],
    [Math.max(...lons), Math.max(...lats)],
  ];
}

// Same color ramp rattfallan-demo's app.js uses for its own coverage heatmap (interpolate on
// margin_db: -20 -> red, 0 -> orange, 15 -> green, 40 -> light green), reused verbatim so this
// tool's heatmap reads the same way that one's does.
const MARGIN_COLOR_STOPS = [
  [-20, [192, 57, 43]],
  [0, [217, 160, 42]],
  [15, [111, 174, 63]],
  [40, [158, 217, 106]],
];

function marginToRgb(v) {
  if (v <= MARGIN_COLOR_STOPS[0][0]) return MARGIN_COLOR_STOPS[0][1];
  const last = MARGIN_COLOR_STOPS[MARGIN_COLOR_STOPS.length - 1];
  if (v >= last[0]) return last[1];
  for (let i = 0; i < MARGIN_COLOR_STOPS.length - 1; i++) {
    const [v0, c0] = MARGIN_COLOR_STOPS[i];
    const [v1, c1] = MARGIN_COLOR_STOPS[i + 1];
    if (v >= v0 && v <= v1) {
      const t = (v - v0) / (v1 - v0);
      return [
        Math.round(c0[0] + (c1[0] - c0[0]) * t),
        Math.round(c0[1] + (c1[1] - c0[1]) * t),
        Math.round(c0[2] + (c1[2] - c0[2]) * t),
      ];
    }
  }
  return last[1];
}

// `raster.margin_db` is already row-0-is-north (server-flipped in _serialize_raster) to match this
// canvas's image row order.
function buildCoverageDataUrl(raster) {
  const { n_rows, n_cols, margin_db } = raster;
  return gridToDataUrl(n_rows, n_cols, (r, c) => {
    const [red, green, blue] = marginToRgb(margin_db[r][c]);
    return [red, green, blue, 255];
  });
}

function setCoverageRaster(raster) {
  if (!raster) {
    if (map.getLayer("coverage-raster-layer")) map.setLayoutProperty("coverage-raster-layer", "visibility", "none");
    return;
  }
  const url = buildCoverageDataUrl(raster);
  if (map.getSource("coverage-raster")) {
    map.getSource("coverage-raster").updateImage({ url, coordinates: raster.corners });
    map.setLayoutProperty("coverage-raster-layer", "visibility", "visible");
  } else {
    map.addSource("coverage-raster", { type: "image", url, coordinates: raster.corners });
    // Inserted below "roads-casing" (same insertion point as the hillshade layer) so roads still
    // draw on top of the heatmap.
    const beforeId = map.getLayer("roads-casing") ? "roads-casing" : undefined;
    map.addLayer(
      { id: "coverage-raster-layer", type: "raster", source: "coverage-raster", paint: { "raster-opacity": 0.75, "raster-resampling": "linear" } },
      beforeId
    );
  }
}

const map = new maplibregl.Map({
  container: "map",
  style: {
    version: 8,
    sources: {
      roads: { type: "geojson", data: { type: "FeatureCollection", features: [] } },
    },
    layers: [
      { id: "basemap", type: "background", paint: { "background-color": "#1B1B1A" } },
      {
        id: "roads-casing",
        type: "line",
        source: "roads",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": "#0a0a0a",
          "line-width": ["interpolate", ["linear"], ["zoom"], 9, 1.3, 12, 2.4, 15, 4.5, 18, 7.5],
          "line-opacity": 0.85,
        },
      },
      {
        id: "roads",
        type: "line",
        source: "roads",
        layout: { "line-cap": "round", "line-join": "round" },
        paint: {
          "line-color": ["coalesce", ["get", "color"], "#707070"],
          "line-width": ["interpolate", ["linear"], ["zoom"], 9, 0.5, 12, 1.1, 15, 2.2, 18, 3.8],
          "line-opacity": 1,
        },
      },
    ],
  },
  center: [18.0, 59.5],
  zoom: 10,
});

map.addControl(new maplibregl.NavigationControl(), "top-right");

// --- Relay / observation placement -----------------------------------------------------------

const modeRelayBtn = document.getElementById("mode-relay");
const modeObserveBtn = document.getElementById("mode-observe");
const rssiInput = document.getElementById("rssi-input");
const resetBtn = document.getElementById("reset-btn");

const clickState = { mode: null }; // "relay" | "observe" | null

function setMode(mode) {
  clickState.mode = clickState.mode === mode ? null : mode;
  modeRelayBtn.classList.toggle("active", clickState.mode === "relay");
  modeObserveBtn.classList.toggle("active", clickState.mode === "observe");
}

function setToolbarDisabled(disabled) {
  modeRelayBtn.disabled = disabled;
  modeObserveBtn.disabled = disabled;
  resetBtn.disabled = disabled;
}

let relayMarker = null;
let observationMarkers = [];

function clearRelayAndObservations() {
  if (relayMarker) relayMarker.remove();
  relayMarker = null;
  observationMarkers.forEach((m) => m.remove());
  observationMarkers = [];
}

function setRelayMarker(pos) {
  if (relayMarker) relayMarker.remove();
  relayMarker = new maplibregl.Marker({ color: "#FFF9AA" }).setLngLat([pos.lon, pos.lat]).addTo(map);
}

function addObservationMarker(pos, rssiDbm) {
  const marker = new maplibregl.Marker({ color: "#C5C5C5" })
    .setLngLat([pos.lon, pos.lat])
    .setPopup(new maplibregl.Popup({ offset: 12 }).setHTML(`RSSI: ${rssiDbm} dBm`))
    .addTo(map);
  observationMarkers.push(marker);
}

async function placeRelay(pos) {
  setStatus("scanning…");
  setToolbarDisabled(true);
  try {
    const res = await fetch("/api/relay", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(pos),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `relay: ${res.status}`);
    clearRelayAndObservations();
    setRelayMarker(data.relay);
    setCoverageRaster(data.raster);
    setStatus("");
  } catch (err) {
    setStatus(`relay placement failed: ${err.message}`);
  } finally {
    setToolbarDisabled(false);
  }
}

async function placeObservation(pos, rssiDbm) {
  if (!relayMarker) {
    setStatus("place a relay first");
    return;
  }
  setStatus("updating…");
  setToolbarDisabled(true);
  try {
    const res = await fetch("/api/observe", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ lon: pos.lon, lat: pos.lat, rssi_dbm: rssiDbm }),
    });
    const data = await res.json();
    if (!res.ok) throw new Error(data.detail || `observe: ${res.status}`);
    addObservationMarker(pos, rssiDbm);
    setCoverageRaster(data.raster);
    setStatus("");
  } catch (err) {
    setStatus(`observation failed: ${err.message}`);
  } finally {
    setToolbarDisabled(false);
  }
}

async function resetAll() {
  setToolbarDisabled(true);
  try {
    await fetch("/api/reset", { method: "POST" });
    clearRelayAndObservations();
    setCoverageRaster(null);
    setStatus("");
  } catch (err) {
    setStatus(`reset failed: ${err.message}`);
  } finally {
    setToolbarDisabled(false);
  }
}

modeRelayBtn.addEventListener("click", () => setMode("relay"));
modeObserveBtn.addEventListener("click", () => {
  if (rssiInput.value === "") {
    setStatus("enter an RSSI value first");
    return;
  }
  setMode("observe");
});
resetBtn.addEventListener("click", resetAll);

map.on("click", (e) => {
  if (!clickState.mode) return;
  const pos = { lon: e.lngLat.lng, lat: e.lngLat.lat };
  if (clickState.mode === "relay") placeRelay(pos);
  else if (clickState.mode === "observe") placeObservation(pos, parseFloat(rssiInput.value));
  setMode(null); // one-shot: disarms after a single placement
});

// --- Initial load: terrain, roads, and any relay/observations already on the server ------------

map.on("load", async () => {
  const problems = [];

  try {
    const hillshade = await fetch("/api/hillshade").then((r) => {
      if (!r.ok) throw new Error(`hillshade: ${r.status}`);
      return r.json();
    });
    map.addSource("hillshade", { type: "image", url: buildHillshadeDataUrl(hillshade), coordinates: hillshade.corners });
    map.addLayer({ id: "hillshade-layer", type: "raster", source: "hillshade", paint: { "raster-opacity": 0.85 } }, "roads-casing");
    map.fitBounds(boundsFromCorners(hillshade.corners), { padding: 20, duration: 0 });
  } catch (err) {
    problems.push(`no terrain (${err.message})`);
  }

  try {
    const roads = await fetch("/api/roads").then((r) => {
      if (!r.ok) throw new Error(`roads: ${r.status}`);
      return r.json();
    });
    map.getSource("roads").setData(roads);
  } catch (err) {
    problems.push(`no roads (${err.message})`);
  }

  try {
    const saved = await fetch("/api/state").then((r) => r.json());
    if (saved.relay) {
      setRelayMarker(saved.relay);
      (saved.observations || []).forEach((obs) => addObservationMarker(obs, obs.rssi_dbm));
      setCoverageRaster(saved.raster);
    }
  } catch (err) {
    problems.push(`no saved state (${err.message})`);
  }

  setStatus(problems.length ? `simulation_tool: ${problems.join(" · ")} — see README.md` : "");
});
