// Dashboard controller. Graph labels and dossier text are rendered as text only.
(() => {
  "use strict";

  const POLL_INTERVAL_MS = 2000;
  const SVG_NS = "http://www.w3.org/2000/svg";
  const el = {
    seed: document.getElementById("seed"),
    assertion: document.getElementById("authorization-assertion"),
    btn: document.getElementById("btn"),
    graph: document.getElementById("graph"),
    audit: document.getElementById("tab-audit"),
    dossier: document.getElementById("tab-dossier"),
    json: document.getElementById("json-output"),
  };

  let runId = null;
  let pollTimer = null;
  let graphData = null;

  function svgElement(name, attributes = {}, text = null) {
    const element = document.createElementNS(SVG_NS, name);
    for (const [key, value] of Object.entries(attributes)) {
      element.setAttribute(key, String(value));
    }
    if (text !== null) element.textContent = String(text);
    return element;
  }

  function renderGraph(graph) {
    graphData = graph;
    el.graph.replaceChildren();

    const nodes = graph.nodes ?? [];
    const edges = graph.edges ?? [];
    if (nodes.length === 0) {
      el.graph.setAttribute("viewBox", "0 0 800 500");
      el.graph.append(svgElement("text", { x: 400, y: 250, class: "graph-empty", "text-anchor": "middle" }, "No entities were recorded."));
      return;
    }

    const columns = Math.max(1, Math.ceil(Math.sqrt(nodes.length * 1.4)));
    const rows = Math.ceil(nodes.length / columns);
    const spacingX = 220;
    const spacingY = 130;
    const paddingX = 110;
    const paddingY = 70;
    const width = Math.max(800, columns * spacingX + paddingX * 2);
    const height = Math.max(500, rows * spacingY + paddingY * 2);
    el.graph.setAttribute("viewBox", `0 0 ${width} ${height}`);
    el.graph.setAttribute("preserveAspectRatio", "xMidYMid meet");

    const positions = new Map();
    nodes.forEach((node, index) => {
      const column = index % columns;
      const row = Math.floor(index / columns);
      positions.set(String(node.data.id), {
        x: paddingX + column * spacingX,
        y: paddingY + row * spacingY,
      });
    });

    const edgeLayer = svgElement("g", { class: "graph-edges" });
    for (const edge of edges) {
      const source = positions.get(String(edge.data.source));
      const target = positions.get(String(edge.data.target));
      if (!source || !target) continue;
      const line = svgElement("line", {
        x1: source.x,
        y1: source.y,
        x2: target.x,
        y2: target.y,
        class: "graph-edge",
      });
      line.append(svgElement("title", {}, edge.data.label ?? "relationship"));
      edgeLayer.append(line);
    }
    el.graph.append(edgeLayer);

    const nodeLayer = svgElement("g", { class: "graph-nodes" });
    nodes.forEach((node, index) => {
      const position = positions.get(String(node.data.id));
      const group = svgElement("g", { class: "graph-node", transform: `translate(${position.x} ${position.y})` });
      group.append(svgElement("circle", { r: 23 }));
      const fullLabel = String(node.data.label ?? "");
      const label = fullLabel.length > 28 ? `${fullLabel.slice(0, 25)}…` : fullLabel;
      group.append(svgElement("text", { y: 42, "text-anchor": "middle" }, label));
      group.append(svgElement("title", {}, `${node.data.type ?? "unknown"}: ${fullLabel}`));
      nodeLayer.append(group);
    });
    el.graph.append(nodeLayer);
  }

  document.querySelectorAll(".tab-btn").forEach((button) => {
    button.addEventListener("click", () => {
      const target = button.dataset.tab;
      document.querySelectorAll(".tab-btn").forEach((item) => {
        const selected = item === button;
        item.classList.toggle("active", selected);
        item.setAttribute("aria-selected", String(selected));
      });
      document.querySelectorAll(".tab-panel").forEach((panel) => {
        panel.classList.toggle("active", panel.id === target);
      });
    });
  });

  el.btn.addEventListener("click", launch);
  el.seed.addEventListener("keydown", (event) => {
    if (event.key === "Enter") launch();
  });

  async function launch() {
    if (el.btn.disabled) return;
    const rawSeed = el.seed.value.trim();
    const splitAt = rawSeed.indexOf(":");
    const assertion = el.assertion.value.trim();
    if (splitAt < 1 || splitAt === rawSeed.length - 1) {
      el.audit.textContent = "Enter a typed seed such as username:your_handle.";
      return;
    }
    if (!assertion) {
      el.audit.textContent = "Enter an authorization assertion before starting.";
      return;
    }

    const seed = {
      type: rawSeed.slice(0, splitAt).trim(),
      value: rawSeed.slice(splitAt + 1).trim(),
    };
    if (!seed.value) {
      el.audit.textContent = "The seed value cannot be empty.";
      return;
    }

    el.btn.disabled = true;
    el.audit.textContent = "Submitting investigation…";
    try {
      const response = await fetch("/api/investigate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ seed, authorization_assertion: assertion }),
      });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `HTTP ${response.status}`);
      startRun(payload.run_id);
    } catch (error) {
      el.audit.textContent = `Could not start investigation: ${error.message}`;
      el.btn.disabled = false;
    }
  }

  function startRun(id) {
    if (pollTimer) clearInterval(pollTimer);
    runId = id;
    graphData = null;
    el.graph.replaceChildren();
    el.dossier.textContent = "Investigation is running…";
    el.json.textContent = "";
    el.audit.textContent = `Run ${id} queued.`;
    pollTimer = setInterval(() => checkStatus(id), POLL_INTERVAL_MS);
    checkStatus(id);
  }

  async function checkStatus(id) {
    if (id !== runId) return;
    try {
      const response = await fetch(`/api/run/${id}/status`, { cache: "no-store" });
      const payload = await response.json();
      if (!response.ok) throw new Error(payload.detail ?? `HTTP ${response.status}`);
      if (id !== runId) return;
      const heading = `Status: ${payload.status}${payload.message ? ` — ${payload.message}` : ""}`;
      el.audit.textContent = `${heading}\n\n${payload.audit_tail ?? ""}`;

      if (payload.status === "failed") {
        clearInterval(pollTimer);
        pollTimer = null;
        el.dossier.textContent = `Investigation failed: ${payload.error ?? "See the run artifacts."}`;
        el.btn.disabled = false;
      } else if (payload.status === "complete") {
        clearInterval(pollTimer);
        pollTimer = null;
        await loadResults(id, payload.dossier_error);
        el.btn.disabled = false;
      }
    } catch (error) {
      el.audit.textContent = `Status check failed: ${error.message}`;
    }
  }

  async function loadResults(id, dossierError) {
    try {
      const graphResponse = await fetch(`/api/run/${id}/graph`, { cache: "no-store" });
      if (!graphResponse.ok) throw new Error(`graph HTTP ${graphResponse.status}`);
      const graph = await graphResponse.json();
      if (id !== runId) return;
      renderGraph(graph);
      el.json.textContent = JSON.stringify(graph, null, 2);

      if (dossierError) {
        el.dossier.textContent = `Reports are ready, but the local LLM dossier was not generated: ${dossierError}`;
        return;
      }
      const dossierResponse = await fetch(`/api/run/${id}/dossier`, { cache: "no-store" });
      if (!dossierResponse.ok) {
        const detail = await dossierResponse.text();
        el.dossier.textContent = `Reports are ready, but the dossier is unavailable: ${detail}`;
        return;
      }
      el.dossier.textContent = await dossierResponse.text();
    } catch (error) {
      el.dossier.textContent = `Could not load run results: ${error.message}`;
    }
  }
})();
