// Arena of Agents: the 3D scene. Loaded after the first paint; exposes window.Arena3D.
// Encoding (same as the 2D view): colour = species, height = ahead/behind the S&P 500 (the water),
// size = portfolio value. Monkeys are grey stones on the inner ring; the equal-weight benchmark is the white ring.
import {
  WebGLRenderer, Scene, PerspectiveCamera, Color, Fog, Group, Mesh, MeshStandardMaterial, MeshBasicMaterial,
  OctahedronGeometry, DodecahedronGeometry, CylinderGeometry, CircleGeometry, RingGeometry, TorusGeometry,
  PlaneGeometry, BufferGeometry, Float32BufferAttribute, LineBasicMaterial, LineSegments, Line,
  HemisphereLight, DirectionalLight, PointLight, Raycaster, Vector2, Vector3, DoubleSide, AdditiveBlending,
  SRGBColorSpace, ACESFilmicToneMapping, Clock, MathUtils, CanvasTexture, Sprite, SpriteMaterial,
} from "three";
import { OrbitControls } from "three/examples/jsm/controls/OrbitControls.js";

const R_AGENTS = 6.2, R_MONKEYS = 3.1, H_MAX = 3.2;

function glowTexture() {
  const c = document.createElement("canvas"); c.width = c.height = 64;
  const g = c.getContext("2d"), grd = g.createRadialGradient(32, 32, 0, 32, 32, 32);
  grd.addColorStop(0, "rgba(255,255,255,1)"); grd.addColorStop(0.35, "rgba(255,255,255,.35)"); grd.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = grd; g.fillRect(0, 0, 64, 64);
  const t = new CanvasTexture(c); t.colorSpace = SRGBColorSpace; return t;
}

function medalTexture(rank) {
  const c = document.createElement("canvas"); c.width = c.height = 96;
  const g = c.getContext("2d"), col = ["", "#ffd34d", "#dfe6f0", "#d99a5b"][rank];
  g.beginPath(); g.arc(48, 48, 40, 0, Math.PI * 2); g.fillStyle = col; g.fill();
  g.lineWidth = 5; g.strokeStyle = "rgba(255,255,255,.65)"; g.stroke();
  g.fillStyle = "rgba(0,0,0,.72)"; g.font = "800 50px system-ui,Segoe UI,sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(String(rank), 48, 52);
  const t = new CanvasTexture(c); t.colorSpace = SRGBColorSpace; return t;
}

export function mount(host, model, opts) {
  const { colors, onPick, onHover } = opts;
  const reduce = matchMedia("(prefers-reduced-motion: reduce)").matches;
  const renderer = new WebGLRenderer({ antialias: true, alpha: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(devicePixelRatio || 1, 2));
  renderer.outputColorSpace = SRGBColorSpace;
  renderer.toneMapping = ACESFilmicToneMapping;
  renderer.toneMappingExposure = 1.1;
  host.appendChild(renderer.domElement);

  const scene = new Scene();
  scene.fog = new Fog(0x05070d, 18, 40);
  const camera = new PerspectiveCamera(42, 1, 0.1, 100);
  // Frame the whole arena for any screen shape (phone portrait looks down more steeply).
  let moved = false;
  const home = () => {
    const tall = camera.aspect < 0.8, v = MathUtils.degToRad(camera.fov) / 2, h = Math.atan(Math.tan(v) * camera.aspect);
    const d = Math.max((tall ? 8.2 : 10.5) / Math.tan(h), 7.0 / Math.tan(v));
    return new Vector3(0, tall ? 0.75 : 0.5, 1).normalize().multiplyScalar(d);
  };

  const controls = new OrbitControls(camera, renderer.domElement);
  controls.target.set(0, 0.4, 0);
  controls.enableDamping = true; controls.dampingFactor = 0.08;
  controls.enablePan = false;
  controls.minDistance = 7; controls.maxDistance = 45;
  controls.minPolarAngle = 0.35; controls.maxPolarAngle = 1.45;
  controls.autoRotate = !reduce; controls.autoRotateSpeed = 0.35;

  scene.add(new HemisphereLight(0x9fb8ff, 0x0b0f1a, 1.1));
  const key = new DirectionalLight(0xffffff, 2.2); key.position.set(6, 12, 8); scene.add(key);
  const rim = new PointLight(0x4fd1ff, 18, 30); rim.position.set(-8, 4, -6); scene.add(rim);

  // Floor: dark disc with rings, under the water.
  const floor = new Mesh(new CircleGeometry(9.5, 96), new MeshStandardMaterial({ color: 0x0b1020, roughness: 0.9, metalness: 0.1 }));
  floor.rotation.x = -Math.PI / 2; floor.position.y = -H_MAX - 0.6; scene.add(floor);
  const rings = new Group();
  [R_MONKEYS, R_AGENTS, 8.6].forEach((r, i) => {
    const m = new Mesh(new RingGeometry(r - 0.015, r + 0.015, 128), new MeshBasicMaterial({ color: 0x2a3550, transparent: true, opacity: i === 2 ? 0.5 : 0.8, side: DoubleSide }));
    m.rotation.x = -Math.PI / 2; m.position.y = -H_MAX - 0.59; rings.add(m);
  });
  scene.add(rings);

  // The water = the S&P 500. Agents above it are beating the index.
  const waterMat = new MeshStandardMaterial({ color: 0x1fb6ff, emissive: 0x0a4a7a, emissiveIntensity: 0.6, transparent: true, opacity: 0.22, roughness: 0.15, metalness: 0.2, side: DoubleSide, depthWrite: false });
  const water = new Mesh(new CircleGeometry(9.5, 96), waterMat);
  water.rotation.x = -Math.PI / 2; scene.add(water);
  const shore = new Mesh(new RingGeometry(9.42, 9.5, 128), new MeshBasicMaterial({ color: 0x5fd4ff, transparent: true, opacity: 0.9, side: DoubleSide }));
  shore.rotation.x = -Math.PI / 2; shore.position.y = 0.005; scene.add(shore);
  // Faint ripple rings on the water
  const ripples = new Group();
  for (let i = 1; i <= 4; i++) {
    const m = new Mesh(new RingGeometry(i * 2 - 0.01, i * 2 + 0.01, 128), new MeshBasicMaterial({ color: 0x7fdcff, transparent: true, opacity: 0.12, side: DoubleSide, depthWrite: false }));
    m.rotation.x = -Math.PI / 2; m.position.y = 0.004; ripples.add(m);
  }
  scene.add(ripples);

  // Height scale: the largest gap to the index maps to H_MAX (at least ±4% so day zero is calm).
  const gaps = model.items.map(it => Math.abs(it.gap || 0));
  const span = Math.max(0.04, ...gaps);
  const yOf = gap => MathUtils.clamp((gap || 0) / span, -1, 1) * H_MAX;
  const cap = model.capital;
  const sizeOf = v => MathUtils.clamp(Math.pow((v || cap) / cap, 2.2), 0.6, 1.8);

  const glowTex = glowTexture();
  const crystal = new OctahedronGeometry(0.42, 0); crystal.scale(1, 1.55, 1);
  const stone = new DodecahedronGeometry(0.26, 0);
  const stemGeo = new CylinderGeometry(0.012, 0.012, 1, 6, 1, true); stemGeo.translate(0, 0.5, 0);
  const pickables = [];
  const objs = new Map();

  const sectors = model.speciesOrder;
  model.items.forEach(it => {
    let pos;
    if (it.type === "agent") {
      const si = Math.max(0, sectors.indexOf(it.sp)), n = model.perSpecies[it.sp] || 1, k = it.slot;
      const a0 = (si / sectors.length) * Math.PI * 2 - Math.PI / 2, w = (Math.PI * 2) / sectors.length;
      const a = a0 + w * (0.18 + 0.64 * (n === 1 ? 0.5 : k / (n - 1)));
      pos = new Vector3(Math.cos(a) * R_AGENTS, 0, Math.sin(a) * R_AGENTS);
    } else if (it.type === "monkey") {
      const a = (it.slot / model.monkeys) * Math.PI * 2 + 0.3;
      pos = new Vector3(Math.cos(a) * R_MONKEYS, 0, Math.sin(a) * R_MONKEYS);
    } else if (it.type === "equal") {
      pos = new Vector3(0, 0, 0);
    } else return; // the index is the water itself
    const y = yOf(it.gap), col = new Color(colors[it.type === "agent" ? it.sp : it.type]);
    const g = new Group(); g.position.copy(pos);
    let body;
    if (it.type === "equal") {
      body = new Mesh(new TorusGeometry(0.55, 0.06, 12, 64), new MeshStandardMaterial({ color: 0xffffff, emissive: 0xffffff, emissiveIntensity: 0.35, roughness: 0.3 }));
      body.rotation.x = Math.PI / 2;
    } else if (it.type === "monkey") {
      body = new Mesh(stone, new MeshStandardMaterial({ color: col, roughness: 0.75, metalness: 0.05, flatShading: true }));
    } else {
      body = new Mesh(crystal, new MeshStandardMaterial({ color: col, emissive: col, emissiveIntensity: 0.35, roughness: 0.18, metalness: 0.1, flatShading: true, transparent: true, opacity: 0.92 }));
    }
    const s = it.type === "agent" ? sizeOf(it.value) : 1;
    body.scale.setScalar(s);
    body.userData.id = it.id;
    const holder = new Group(); holder.add(body); holder.position.y = y; g.add(holder);
    // stem from the water to the figure: shows "how far above/below the index"
    const stem = new Mesh(stemGeo, new MeshBasicMaterial({ color: col, transparent: true, opacity: 0.5 }));
    stem.scale.y = Math.max(Math.abs(y), 0.001); if (y < 0) stem.rotation.x = Math.PI;
    g.add(stem);
    // contact point on the water
    const dot = new Mesh(new CircleGeometry(0.09, 20), new MeshBasicMaterial({ color: col, transparent: true, opacity: 0.85, side: DoubleSide }));
    dot.rotation.x = -Math.PI / 2; dot.position.y = 0.01; g.add(dot);
    if (it.type === "agent") {
      const glow = new Sprite(new SpriteMaterial({ map: glowTex, color: col, transparent: true, opacity: 0.55, blending: AdditiveBlending, depthWrite: false }));
      glow.scale.setScalar(1.9 * s); holder.add(glow);
    }
    if (it.rank && it.rank <= 3) { // podium medal floating above the crystal
      const medal = new Sprite(new SpriteMaterial({ map: medalTexture(it.rank), transparent: true, depthWrite: false }));
      medal.scale.setScalar(0.42); medal.position.y = 1.05 * s; holder.add(medal);
    }
    g.userData = { id: it.id, holder, body, y, phase: Math.random() * Math.PI * 2, base: s };
    holder.position.y = reduce ? y : 0; // intro: rise from the water
    scene.add(g); pickables.push(body); objs.set(it.id, g);
  });

  // Species labels on the floor rim (2-4 words total, no clutter)
  sectors.forEach((sp, si) => {
    const a = ((si + 0.5) / sectors.length) * Math.PI * 2 - Math.PI / 2;
    const c = document.createElement("canvas"); c.width = 512; c.height = 96;
    const g = c.getContext("2d"); g.font = "700 46px system-ui,Segoe UI,sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
    g.shadowColor = "rgba(0,0,0,.8)"; g.shadowBlur = 10;
    g.fillStyle = colors[sp]; g.fillText(model.speciesLabel[sp].toUpperCase(), 256, 48);
    const t = new CanvasTexture(c); t.colorSpace = SRGBColorSpace;
    const spr = new Sprite(new SpriteMaterial({ map: t, transparent: true, depthWrite: false, depthTest: false }));
    spr.scale.set(3.2, 0.6, 1); spr.position.set(Math.cos(a) * 8.9, 0.35, Math.sin(a) * 8.9); scene.add(spr);
  });

  // Picking
  const ray = new Raycaster(), ptr = new Vector2();
  let hovered = null, downAt = null;
  function pick(ev) {
    const r = renderer.domElement.getBoundingClientRect();
    ptr.set(((ev.clientX - r.left) / r.width) * 2 - 1, -((ev.clientY - r.top) / r.height) * 2 + 1);
    ray.setFromCamera(ptr, camera);
    const hit = ray.intersectObjects(pickables, false)[0];
    return hit ? hit.object.userData.id : null;
  }
  const el = renderer.domElement;
  el.addEventListener("pointermove", ev => {
    if (ev.pointerType !== "mouse") return;
    const id = pick(ev);
    if (id !== hovered) { hovered = id; el.style.cursor = id ? "pointer" : ""; onHover && onHover(id, ev); setHover(id); }
    else if (id) onHover && onHover(id, ev);
  });
  el.addEventListener("pointerleave", () => { if (hovered) { hovered = null; onHover && onHover(null); setHover(null); } });
  el.addEventListener("pointerdown", ev => { downAt = [ev.clientX, ev.clientY]; });
  el.addEventListener("pointerup", ev => {
    if (!downAt || Math.hypot(ev.clientX - downAt[0], ev.clientY - downAt[1]) > 6) return;
    const id = pick(ev); if (id) onPick(id);
  });
  controls.addEventListener("start", () => { controls.autoRotate = false; moved = true; });

  let focus = null;
  function setHover(id) {
    focus = id;
    objs.forEach((g, k) => { g.userData.body.scale.setScalar(g.userData.base * (k === id ? 1.25 : 1)); });
  }

  function resize() {
    const w = host.clientWidth, h = host.clientHeight;
    renderer.setSize(w, h, false); camera.aspect = w / Math.max(h, 1);
    camera.fov = camera.aspect < 0.8 ? 50 : 40; camera.updateProjectionMatrix();
    if (!moved) camera.position.copy(home());
    const d = camera.position.length(); scene.fog.near = d * 1.25; scene.fog.far = d * 2.8;
  }
  const ro = new ResizeObserver(resize); ro.observe(host); resize();
  if (/[?&]debug(&|$)/.test(location.search)) window.__arena = { camera, scene, controls, renderer };

  const clock = new Clock();
  let running = true, intro = reduce ? 1 : 0, raf = 0;
  const t0 = performance.now();
  function frame() {
    raf = requestAnimationFrame(frame);
    if (!running) return;
    const dt = Math.min(clock.getDelta(), 0.05), t = clock.elapsedTime;
    if (intro < 1) intro = Math.min(1, (performance.now() - t0) / 1400);
    const e = 1 - Math.pow(1 - intro, 3);
    objs.forEach(g => {
      const u = g.userData;
      u.holder.position.y = u.y * e + (reduce ? 0 : Math.sin(t * 1.1 + u.phase) * 0.05);
      if (!reduce) u.body.rotation.y += dt * 0.35;
    });
    ripples.children.forEach((m, i) => { m.scale.setScalar(1 + ((t * 0.08 + i * 0.25) % 1) * 0.15); });
    controls.update();
    renderer.render(scene, camera);
  }
  frame();
  const onVis = () => { running = !document.hidden; clock.getDelta(); };
  document.addEventListener("visibilitychange", onVis);

  return {
    pause(p) { running = !p && !document.hidden; if (running) clock.getDelta(); },
    highlight(id) { setHover(id); },
    resetView() { moved = false; camera.position.copy(home()); controls.target.set(0, 0.4, 0); controls.autoRotate = !reduce; },
    destroy() {
      cancelAnimationFrame(raf); ro.disconnect(); document.removeEventListener("visibilitychange", onVis);
      controls.dispose(); renderer.dispose(); el.remove();
    },
  };
}

window.Arena3D = { mount };
