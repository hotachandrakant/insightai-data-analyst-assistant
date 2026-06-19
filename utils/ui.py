"""Reusable Streamlit UI helpers for InsightAI.

Keeps presentation concerns (CSS injection, KPI cards, insight callouts,
section headers) out of the business-logic modules.
"""
from __future__ import annotations

from pathlib import Path

import plotly.graph_objects as go
import plotly.io as pio
import streamlit as st
import streamlit.components.v1 as components

from utils.config import load_config

_cfg = load_config()


def inject_css() -> None:
    """Load and inject the corporate stylesheet once per session."""
    css_path = _cfg.assets_dir / "style.css"
    if css_path.exists():
        st.markdown(f"<style>{css_path.read_text()}</style>", unsafe_allow_html=True)


def register_plotly_theme() -> None:
    """Register a branded dark Plotly template and set it as default.

    Tuned for the cinematic dark UI: transparent backgrounds (so charts sit on
    the glass panels), light text, faint grid lines and a vibrant colorway.
    """
    grid = "rgba(148,163,184,0.14)"
    template = go.layout.Template()
    template.layout = go.Layout(
        font=dict(family="Inter, Segoe UI, sans-serif", color="#CBD5E1", size=13),
        colorway=list(_cfg.plotly_palette),
        paper_bgcolor="rgba(0,0,0,0)",
        plot_bgcolor="rgba(0,0,0,0)",
        margin=dict(l=40, r=20, t=54, b=40),
        title=dict(font=dict(size=18, family="Inter", color="#F8FAFC")),
        xaxis=dict(gridcolor=grid, zerolinecolor=grid, linecolor=grid,
                   tickfont=dict(color="#94A3B8")),
        yaxis=dict(gridcolor=grid, zerolinecolor=grid, linecolor=grid,
                   tickfont=dict(color="#94A3B8")),
        legend=dict(bgcolor="rgba(0,0,0,0)", font=dict(color="#CBD5E1")),
        colorscale=dict(sequential=[[0, "#0B0E16"], [0.5, "#6366F1"], [1, "#22D3EE"]]),
        hoverlabel=dict(bgcolor="#0B0E16", bordercolor="#6366F1",
                        font=dict(color="#F8FAFC")),
    )
    pio.templates["insightai"] = template
    # Compose with Plotly's dark base for sensible defaults, then our overrides.
    pio.templates.default = "plotly_dark+insightai"


def hero(title: str, subtitle: str) -> None:
    """Render the gradient hero banner."""
    st.markdown(
        f"""
        <div class="ia-hero">
            <h1>{title}</h1>
            <p>{subtitle}</p>
        </div>
        """,
        unsafe_allow_html=True,
    )


def hero_3d(title: str, subtitle: str, height: int = 440) -> None:
    """Render an interactive 3D animated hero using Three.js.

    A rotating, mouse-reactive "data constellation" (particles connected by
    edges) renders on a WebGL canvas inside a Streamlit component iframe, with
    the product title overlaid. Falls back gracefully to the CSS hero on
    browsers without WebGL.

    Args:
        title: Main headline (HTML allowed).
        subtitle: Supporting line beneath the headline.
        height: Iframe height in pixels.
    """
    html = (
        _HERO_3D_TEMPLATE
        .replace("__TITLE__", title)
        .replace("__SUBTITLE__", subtitle)
    )
    components.html(html, height=height, scrolling=False)


def page_banner(icon: str, title: str, subtitle: str = "") -> None:
    """Render a classy animated banner for the top of a feature page.

    Args:
        icon: An emoji or short glyph shown in the gradient tile.
        title: Page title.
        subtitle: Supporting description.
    """
    st.markdown(
        f'<div class="ia-page-banner"><div class="ia-pb-content">'
        f'<div class="ia-pb-icon">{icon}</div>'
        f'<div><div class="ia-pb-title">{title}</div>'
        f'<div class="ia-pb-sub">{subtitle}</div></div></div></div>',
        unsafe_allow_html=True,
    )


def section_header(title: str, description: str = "") -> None:
    """Render a consistent section title with optional description."""
    st.markdown(f"### {title}")
    if description:
        st.caption(description)


def kpi_cards(metrics: list[dict]) -> None:
    """Render a responsive grid of KPI cards.

    Args:
        metrics: list of dicts with keys ``label``, ``value`` and optional
            ``delta`` (str) and ``direction`` ("up"/"down").
    """
    cards = []
    for m in metrics:
        delta_html = ""
        if m.get("delta"):
            cls = "delta-up" if m.get("direction", "up") == "up" else "delta-down"
            arrow = "▲" if m.get("direction", "up") == "up" else "▼"
            delta_html = f'<div class="{cls}">{arrow} {m["delta"]}</div>'
        cards.append(
            f'<div class="ia-kpi"><div class="label">{m["label"]}</div>'
            f'<div class="value">{m["value"]}</div>{delta_html}</div>'
        )
    st.markdown(
        f'<div class="ia-kpi-grid">{"".join(cards)}</div>', unsafe_allow_html=True
    )


def insight(text: str, kind: str = "info") -> None:
    """Render a coloured insight callout.

    Args:
        text: The insight body (may contain inline HTML/markdown bold).
        kind: One of ``info``, ``good``, ``warn``, ``bad``.
    """
    css_class = {"info": "", "good": "good", "warn": "warn", "bad": "bad"}.get(kind, "")
    st.markdown(
        f'<div class="ia-insight {css_class}">{text}</div>', unsafe_allow_html=True
    )


def card_open(title: str = "") -> None:
    """Open a styled card container (pair with :func:`card_close`)."""
    heading = f"<h3>{title}</h3>" if title else ""
    st.markdown(f'<div class="ia-card">{heading}', unsafe_allow_html=True)


def card_close() -> None:
    """Close a styled card container."""
    st.markdown("</div>", unsafe_allow_html=True)


def footer() -> None:
    """Render the product footer."""
    st.markdown(
        f"""
        <div class="ia-footer">
            {_cfg.app_name} v{_cfg.version} · {_cfg.tagline}<br/>
            Built with Streamlit · Pandas · Plotly · Scikit-Learn
        </div>
        """,
        unsafe_allow_html=True,
    )


def require_data() -> bool:
    """Guard for pages that need an uploaded dataset.

    Returns:
        True if a dataframe is available in session state, else renders a
        friendly prompt and returns False.
    """
    if st.session_state.get("df") is None:
        st.info("📂 Please upload a dataset from the **Data Upload** page to begin.")
        return False
    return True


# ── 3D animated hero (Three.js) ─────────────────────────────────────────
# Self-contained HTML document rendered inside a Streamlit component iframe.
# Placeholders __TITLE__ / __SUBTITLE__ are substituted by ``hero_3d``.
_HERO_3D_TEMPLATE = """
<!DOCTYPE html>
<html>
<head>
<meta charset="utf-8" />
<style>
  * { margin: 0; padding: 0; box-sizing: border-box; }
  html, body { height: 100%; overflow: hidden; font-family: "Inter","Segoe UI",sans-serif; }
  #wrap {
    position: relative; width: 100%; height: 100vh; border-radius: 24px; overflow: hidden;
    background:
      radial-gradient(1100px 480px at 82% -12%, #312e81 0%, #0b0e16 52%, #05060a 100%),
      radial-gradient(700px 420px at 10% 110%, rgba(34,211,238,0.16), transparent 60%);
    box-shadow: inset 0 0 0 1px rgba(148,163,184,0.14), inset 0 -60px 120px rgba(99,102,241,0.12);
  }
  #scene { position: absolute; inset: 0; display: block; }
  #overlay {
    position: absolute; inset: 0; display: flex; flex-direction: column;
    justify-content: center; padding: 0 8%; pointer-events: none; z-index: 2;
  }
  #overlay h1, #overlay p, #overlay .eyebrow, #overlay .cta { font-family: "Space Grotesk","Inter",sans-serif; }
  .eyebrow {
    display: inline-flex; align-items: center; gap: 8px; width: max-content;
    padding: 6px 14px; border-radius: 999px; font-size: 12px; font-weight: 700;
    letter-spacing: 1.2px; text-transform: uppercase; color: #c7d2fe;
    background: rgba(99,102,241,0.16); border: 1px solid rgba(129,140,248,0.45);
    backdrop-filter: blur(6px); margin-bottom: 18px;
    animation: fadeUp 0.8s both;
  }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #fbbf24;
         box-shadow: 0 0 14px #fbbf24; animation: pulse 1.6s infinite; }
  h1 {
    font-size: clamp(30px, 4.6vw, 56px); font-weight: 700; line-height: 1.04;
    letter-spacing: -1.2px; color: #fff; max-width: 18ch;
    text-shadow: 0 8px 40px rgba(99,102,241,0.5); animation: fadeUp 0.9s 0.1s both;
  }
  h1 .grad {
    background: linear-gradient(120deg, #22d3ee, #818cf8 50%, #fbbf24);
    -webkit-background-clip: text; background-clip: text; -webkit-text-fill-color: transparent;
  }
  p.sub {
    margin-top: 16px; max-width: 58ch; font-size: clamp(13px, 1.5vw, 17px);
    color: rgba(226,232,240,0.82); line-height: 1.6; animation: fadeUp 1s 0.2s both;
    font-family: "Inter", sans-serif;
  }
  .cta {
    margin-top: 22px; display: inline-flex; align-items: center; gap: 10px;
    padding: 12px 22px; border-radius: 13px; font-size: 14px; font-weight: 700; color: #fff;
    background: linear-gradient(120deg, #6366f1, #22d3ee); width: max-content;
    box-shadow: 0 12px 34px rgba(99,102,241,0.45); animation: fadeUp 1.05s 0.3s both;
    cursor: pointer; pointer-events: auto; position: relative; overflow: hidden;
    user-select: none; -webkit-tap-highlight-color: transparent;
    transition: transform .15s ease, box-shadow .25s ease;
  }
  .cta:hover { transform: translateY(-2px) scale(1.03); box-shadow: 0 18px 46px rgba(34,211,238,0.55); }
  .cta:active { transform: scale(0.95); }
  .cta .arrow { animation: nudge 1.4s ease-in-out infinite; }
  .ripple { position: absolute; border-radius: 50%; background: rgba(255,255,255,0.55);
            transform: scale(0); animation: rip .6s linear; pointer-events: none; }
  @keyframes rip { to { transform: scale(4); opacity: 0; } }
  @keyframes fadeUp { from { opacity: 0; transform: translateY(22px); } to { opacity: 1; transform: none; } }
  @keyframes pulse { 0%,100% { transform: scale(1); opacity: 1; } 50% { transform: scale(1.6); opacity: 0.5; } }
  @keyframes nudge { 0%,100% { transform: translateX(0); } 50% { transform: translateX(5px); } }
</style>
</head>
<body>
<div id="wrap">
  <canvas id="scene"></canvas>
  <div id="overlay">
    <span class="eyebrow"><span class="dot"></span> AI Powered Analytics Engine</span>
    <h1>__TITLE__</h1>
    <p class="sub">__SUBTITLE__</p>
    <span class="cta">Begin your analysis <span class="arrow">&#8594;</span></span>
  </div>
</div>
<script src="https://cdnjs.cloudflare.com/ajax/libs/three.js/r128/three.min.js"></script>
<script>
(function () {
  var canvas = document.getElementById('scene');
  var wrap = document.getElementById('wrap');
  if (!window.THREE) { return; }  // graceful fallback: gradient + text only

  var W = wrap.clientWidth, H = wrap.clientHeight;
  var renderer = new THREE.WebGLRenderer({ canvas: canvas, antialias: true, alpha: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  renderer.setSize(W, H);

  var scene = new THREE.Scene();
  var camera = new THREE.PerspectiveCamera(60, W / H, 0.1, 1000);
  camera.position.z = 22;

  var group = new THREE.Group();
  scene.add(group);

  // Fibonacci-sphere distribution of nodes.
  var N = 150, R = 11;
  var positions = [];
  for (var i = 0; i < N; i++) {
    var y = 1 - (i / (N - 1)) * 2;
    var radius = Math.sqrt(1 - y * y);
    var theta = Math.PI * (3 - Math.sqrt(5)) * i;
    positions.push(new THREE.Vector3(
      Math.cos(theta) * radius * R, y * R, Math.sin(theta) * radius * R
    ));
  }

  // Glowing point cloud.
  var pGeo = new THREE.BufferGeometry();
  var pArr = new Float32Array(N * 3);
  for (var j = 0; j < N; j++) {
    pArr[j*3] = positions[j].x; pArr[j*3+1] = positions[j].y; pArr[j*3+2] = positions[j].z;
  }
  pGeo.setAttribute('position', new THREE.BufferAttribute(pArr, 3));
  var sprite = makeGlow();
  var points = new THREE.Points(pGeo, new THREE.PointsMaterial({
    size: 1.5, map: sprite, transparent: true, depthWrite: false,
    blending: THREE.AdditiveBlending, color: 0x22d3ee
  }));
  group.add(points);

  // Adjacency + edges between nearby nodes (precomputed once for performance).
  var adj = [], linePos = [], thresh = 4.6;
  for (var k = 0; k < N; k++) { adj.push([]); }
  for (var a = 0; a < N; a++) {
    for (var b = a + 1; b < N; b++) {
      if (positions[a].distanceTo(positions[b]) < thresh) {
        adj[a].push(b); adj[b].push(a);
        linePos.push(positions[a].x, positions[a].y, positions[a].z);
        linePos.push(positions[b].x, positions[b].y, positions[b].z);
      }
    }
  }
  var lGeo = new THREE.BufferGeometry();
  lGeo.setAttribute('position', new THREE.BufferAttribute(new Float32Array(linePos), 3));
  var lines = new THREE.LineSegments(lGeo, new THREE.LineBasicMaterial({
    color: 0x6366f1, transparent: true, opacity: 0.26, blending: THREE.AdditiveBlending
  }));
  group.add(lines);

  // ── Build a greedy "route" through connected nodes (RouteWise nod) ──
  var route = [0], used = {0: true};
  for (var step = 0; step < 60; step++) {
    var cur = route[route.length - 1], next = -1;
    for (var n = 0; n < adj[cur].length; n++) {
      if (!used[adj[cur][n]]) { next = adj[cur][n]; break; }
    }
    if (next === -1) {  // jump to any unused node to keep travelling
      for (var u = 0; u < N; u++) { if (!used[u]) { next = u; break; } }
    }
    if (next === -1) break;
    used[next] = true; route.push(next);
  }
  // Gold comet that travels the route, with a soft trail.
  var comet = new THREE.Sprite(new THREE.SpriteMaterial({
    map: sprite, color: 0xfbbf24, transparent: true, depthWrite: false,
    blending: THREE.AdditiveBlending
  }));
  comet.scale.set(2.4, 2.4, 1);
  group.add(comet);
  var trail = [];
  for (var t = 0; t < 14; t++) {
    var s = new THREE.Sprite(new THREE.SpriteMaterial({
      map: sprite, color: 0xfde68a, transparent: true, opacity: 0, depthWrite: false,
      blending: THREE.AdditiveBlending
    }));
    s.scale.set(1.4, 1.4, 1); group.add(s); trail.push(s);
  }
  var routeProg = 0;  // progress along current segment [0,1)
  var routeIdx = 0;   // current segment start index

  // Floating ambient particles (depth).
  var dustGeo = new THREE.BufferGeometry();
  var dustArr = new Float32Array(220 * 3);
  for (var d = 0; d < 220; d++) {
    dustArr[d*3]   = (Math.random() - 0.5) * 60;
    dustArr[d*3+1] = (Math.random() - 0.5) * 40;
    dustArr[d*3+2] = (Math.random() - 0.5) * 40;
  }
  dustGeo.setAttribute('position', new THREE.BufferAttribute(dustArr, 3));
  var dust = new THREE.Points(dustGeo, new THREE.PointsMaterial({
    size: 0.6, map: sprite, transparent: true, opacity: 0.5, depthWrite: false,
    blending: THREE.AdditiveBlending, color: 0xc084fc
  }));
  scene.add(dust);

  // Mouse parallax.
  var mx = 0, my = 0, tx = 0, ty = 0;
  wrap.addEventListener('mousemove', function (e) {
    var r = wrap.getBoundingClientRect();
    mx = ((e.clientX - r.left) / r.width - 0.5) * 2;
    my = ((e.clientY - r.top) / r.height - 0.5) * 2;
  });

  var trailPos = [];
  function animate() {
    requestAnimationFrame(animate);
    group.rotation.y += 0.0016;
    group.rotation.x += 0.0006;
    dust.rotation.y -= 0.0004;

    // Advance the gold comet along the route.
    if (route.length > 1) {
      routeProg += 0.025;
      if (routeProg >= 1) { routeProg = 0; routeIdx = (routeIdx + 1) % (route.length - 1); }
      var p0 = positions[route[routeIdx]], p1 = positions[route[routeIdx + 1]];
      var pos = p0.clone().lerp(p1, routeProg);
      comet.position.copy(pos);
      trailPos.unshift(pos.clone());
      if (trailPos.length > trail.length) { trailPos.pop(); }
      for (var ti = 0; ti < trailPos.length; ti++) {
        trail[ti].position.copy(trailPos[ti]);
        trail[ti].material.opacity = 0.55 * (1 - ti / trail.length);
      }
    }

    tx += (mx * 0.35 - tx) * 0.05;
    ty += (my * 0.35 - ty) * 0.05;
    camera.position.x = tx * 6;
    camera.position.y = -ty * 6;
    camera.lookAt(scene.position);
    renderer.render(scene, camera);
  }
  animate();

  window.addEventListener('resize', function () {
    W = wrap.clientWidth; H = wrap.clientHeight;
    camera.aspect = W / H; camera.updateProjectionMatrix();
    renderer.setSize(W, H);
  });

  // CTA tap feedback (ripple + bounce). Navigation is handled by the
  // real Streamlit button rendered just below this banner.
  var cta = document.querySelector('.cta');
  if (cta) {
    cta.addEventListener('click', function (e) {
      var ripple = document.createElement('span');
      ripple.className = 'ripple';
      var d = Math.max(cta.clientWidth, cta.clientHeight);
      var rect = cta.getBoundingClientRect();
      ripple.style.width = ripple.style.height = d + 'px';
      ripple.style.left = (e.clientX - rect.left - d / 2) + 'px';
      ripple.style.top = (e.clientY - rect.top - d / 2) + 'px';
      cta.appendChild(ripple);
      setTimeout(function () { ripple.remove(); }, 600);
      try { window.parent.postMessage({ type: 'ia-begin' }, '*'); } catch (_) {}
    });
  }

  // Radial-gradient sprite for soft glowing dots.
  function makeGlow() {
    var c = document.createElement('canvas'); c.width = c.height = 64;
    var ctx = c.getContext('2d');
    var g = ctx.createRadialGradient(32, 32, 0, 32, 32, 32);
    g.addColorStop(0, 'rgba(255,255,255,1)');
    g.addColorStop(0.3, 'rgba(180,210,255,0.85)');
    g.addColorStop(1, 'rgba(180,210,255,0)');
    ctx.fillStyle = g; ctx.fillRect(0, 0, 64, 64);
    var tex = new THREE.Texture(c); tex.needsUpdate = true; return tex;
  }
})();
</script>
</body>
</html>
"""

