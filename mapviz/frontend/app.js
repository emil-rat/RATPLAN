// RATPLAN mapviz -- terrain hillshade + road network, nothing else. See
// architecture.md §9 for scope. Modeled on rattfallan-demo's own
// buildHillshadeDataUrl/style-building conventions, simplified: no live
// viewport-bboxed refetching (a snapshot's road set is small enough to load
// once), no placement/routing/coverage layers.

const statusEl = document.getElementById("status");

function setStatus(text) {
  statusEl.textContent = text;
}

// Shared by any image-source layer this app builds client-side (just the
// hillshade for now) -- paints a canvas pixel-by-pixel via
// pixelAt(row, col) -> [r, g, b, a] and returns a data URL MapLibre's
// `image` source can use directly as its `url`. Same helper rattfallan-demo's
// app.js uses for its own hillshade/coverage layers.
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

const map = new maplibregl.Map({
  container: "map",
  style: {
    version: 8,
    sources: {
      roads: { type: "geojson", data: { type: "FeatureCollection", features: [] } },
    },
    layers: [
      { id: "basemap", type: "background", paint: { "background-color": "#171a15" } },
      // Casing underneath + a bright centerline on top, same convention
      // rattfallan-demo/scenario_builder's layers.js uses so roads read
      // against any background, not just terrain shading that happens to
      // be lighter/darker at a given spot.
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

map.on("load", async () => {
  const problems = [];

  try {
    const hillshade = await fetch("/api/hillshade").then((r) => {
      if (!r.ok) throw new Error(`hillshade: ${r.status}`);
      return r.json();
    });
    map.addSource("hillshade", { type: "image", url: buildHillshadeDataUrl(hillshade), coordinates: hillshade.corners });
    // Inserted below "roads-casing" so roads still draw on top of terrain.
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

  setStatus(problems.length ? `mapviz: ${problems.join(" · ")} — see README.md` : "");
});
