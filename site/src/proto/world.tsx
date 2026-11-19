// Prototype B — "The Living World". The same creatures, the same answer sentence and stories as A,
// but the picture is a calm 3D meadow you zoom through without changing page:
// World (everyone) → a species' meadow → one creature (its Story opens beside it).
// Left/right = behind/ahead of the market (the blue river), the grey field = could be luck.
import "@fontsource-variable/geist";
import "./proto.css";
import { Canvas, useFrame, useThree } from "@react-three/fiber";
import { Html } from "@react-three/drei";
import { memo, useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import * as THREE from "three";
import { buildModel, loadArena, type Arena, type Model, type Participant } from "../data";
import { bodyPoints, capital, creatureFill, creatureOf, euro, SPECIES_HUE, STRATEGY } from "./common";
import { Story, useClock } from "./Story";
import { Bar, Head, Stories, TimeBar, useDay, useTheme } from "./shell";

const W = 6.5;            // half-width of the meadow: ±W = the furthest any agent got from the market
const ROW = 2.4;        // distance between species meadows

function App() {
  const [A, setA] = useState<Arena | null>(null);
  useEffect(() => { loadArena().then(setA).catch(() => setA(null)); }, []);
  if (!A) return <div className="app"><p className="quiet">Loading the world…</p></div>;
  return <LivingWorld M={buildModel(A)} />;
}

type Focus = { level: "world" } | { level: "species"; sp: string } | { level: "creature"; sp: string; id: string };

function LivingWorld({ M }: { M: Model }) {
  const [dark, setDark] = useTheme();
  const [focus, setFocus] = useState<Focus>({ level: "world" });
  const up = useCallback(() => setFocus(f => f.level === "creature" ? { level: "species", sp: f.sp } : { level: "world" }), []);
  const { i, setI, playing, setPlaying } = useDay(M, up);
  const t = useClock(focus.level !== "creature");
  const [hover, setHover] = useState<string | null>(null);
  const species = useMemo(() => Object.keys(SPECIES_HUE).filter(s => M.agents.some(p => p.sp === s)), [M]);
  const span = Math.max(.02, M.span);
  const X = useCallback((g: number) => Math.max(-1, Math.min(1, g / span)) * W, [span]);
  const open = useCallback((id: string) => { const p = M.byId[id]; if (p) setFocus({ level: "creature", sp: p.sp || species[0], id }); }, [M, species]);
  const toSpecies = useCallback((sp: string) => setFocus({ level: "species", sp }), []);
  const name = (sp: string) => STRATEGY[sp] || sp;
  const crumbs = focus.level === "world" ? [] : [<button key="w" onClick={() => setFocus({ level: "world" })}>Everyone</button>,
    <button key="s" onClick={() => setFocus({ level: "species", sp: focus.sp })}>{name(focus.sp)}</button>];
  // wheel: zooming out climbs one level; zooming in on the world opens the meadow under the pointer
  const wheel = (e: React.WheelEvent) => { if (e.deltaY > 0 && focus.level !== "world") up(); else if (e.deltaY < 0 && focus.level === "world" && hover) open(hover); };

  return (
    <div className="app">
      <Bar dark={dark} setDark={setDark} />
      <Head M={M} i={i} />
      <div className="main">
        <section className="race card world" aria-label="The living world" onWheel={wheel}>
          <div className="legend">
            <span>← Behind the market</span>
            <span className="crumbs3">{crumbs.length ? crumbs : <span className="quiet">Tap a meadow or a creature to zoom in</span>}</span>
            <span>Ahead of the market →</span>
          </div>
          <div className="stage">
            <Canvas dpr={[1, 2]} camera={{ position: [0, 7.5, 13.5], fov: 34 }} gl={{ antialias: true, alpha: false }} flat shadows={false}>
              <Scene M={M} i={i} dark={dark} X={X} species={species} focus={focus} hover={hover} setHover={setHover}
                onSpecies={toSpecies} onPick={open} />
            </Canvas>
            <div className="luckkey floating"><i />Grey field: could be luck<b className="sep" /><span style={{ color: "var(--market)" }}>Blue line: the market</span></div>
          </div>
          <TimeBar M={M} i={i} setI={setI} playing={playing} setPlaying={setPlaying} />
        </section>
        <Stories M={M} i={i} dark={dark} t={t} onOpen={open} />
        {focus.level === "creature" && M.byId[focus.id] &&
          <Story M={M} p={M.byId[focus.id]} i={i} dark={dark} onClose={up} crumbs={["Everyone", name(focus.sp)]} />}
      </div>
    </div>
  );
}

type SceneProps = {
  M: Model; i: number; dark: boolean; X: (g: number) => number; species: string[]; focus: Focus; hover: string | null;
  setHover: (id: string | null) => void; onSpecies: (sp: string) => void; onPick: (id: string) => void;
};

const Scene = memo(function Scene({ M, i, dark, X, species, focus, hover, setHover, onSpecies, onPick }: SceneProps) {
  const bg = dark ? "#0e1118" : "#f6f7f9";
  const rowZ = (sp: string) => (species.indexOf(sp) - (species.length - 1) / 2) * ROW;
  const band = M.luckAt(i);
  const cap = capital(M.A);
  // where each creature stands: x from the gap, z from its meadow, nudged so neighbours don't overlap
  const spots = useMemo(() => {
    const out: Record<string, [number, number]> = {};
    for (const sp of species) {
      const ps = M.agents.filter(p => p.sp === sp).sort((a, b) => M.gapAt(a, i) - M.gapAt(b, i));
      ps.forEach((p, k) => { out[p.id] = [X(M.gapAt(p, i)), rowZ(sp) + ((k % 3) - 1) * 0.55]; });
    }
    return out;
  }, [M, i, species]); // eslint-disable-line react-hooks/exhaustive-deps
  const target = useMemo(() => {
    if (focus.level === "creature") { const [x, z] = spots[focus.id] || [0, 0]; return { pos: new THREE.Vector3(x + 1.2, 3.4, z + 4.6), look: new THREE.Vector3(x + 1.5, 0.3, z - 0.2) }; }
    if (focus.level === "species") { const z = rowZ(focus.sp); return { pos: new THREE.Vector3(0, 8.5, z + 8.5), look: new THREE.Vector3(0, 0, z + 0.4) }; }
    return { pos: new THREE.Vector3(0, 8 + species.length * 0.6, 10 + species.length * 1.35), look: new THREE.Vector3(0, 0, 1.4) };
  }, [focus, spots]); // eslint-disable-line react-hooks/exhaustive-deps
  const zFar = species.length * ROW / 2 + 1.2;
  return (
    <>
      <color attach="background" args={[bg]} />
      <fog attach="fog" args={[bg, 26, 46]} />
      <hemisphereLight args={[dark ? "#c9d6ff" : "#ffffff", dark ? "#1a1f2b" : "#d9dde6", dark ? 1.1 : 1.5]} />
      <directionalLight position={[4, 8, 6]} intensity={dark ? 1.2 : 1.6} />
      <Camera target={target} />
      {/* the meadow */}
      <mesh rotation-x={-Math.PI / 2} position={[0, -0.01, 0]}><planeGeometry args={[80, 80]} /><meshBasicMaterial color={bg} /></mesh>
      <Html position={[0, -50, 0]}><span /></Html>{/* the first label placed at start-up gets dropped; this empty one takes that place */}
      {species.map(sp => (
        <group key={sp} position={[0, 0, rowZ(sp)]}>
          <mesh rotation-x={-Math.PI / 2} position={[0, 0.002, 0]} onClick={e => { e.stopPropagation(); onSpecies(sp); }}>
            <planeGeometry args={[W * 2 + 2, ROW * 0.86]} />
            <meshBasicMaterial color={`hsl(${SPECIES_HUE[sp]}, ${dark ? 20 : 45}%, ${dark ? 14 : 95}%)`} />
          </mesh>
          <Html position={[-W - 1, 0.05, ROW * 0.12]} zIndexRange={[20, 10]}>
            <button className="meadow" onClick={() => onSpecies(sp)} style={{ borderColor: `hsl(${SPECIES_HUE[sp]}, 50%, 55%)` }}>{STRATEGY[sp]}</button>
          </Html>
        </group>
      ))}
      {/* could be luck: the field where 90% of random monkeys end up */}
      {band && <LuckField x0={X(band[0])} x1={X(band[1])} depth={zFar * 2} dark={dark} />}
      {/* the market: a blue river at zero */}
      <mesh rotation-x={-Math.PI / 2} position={[X(0), 0.012, 0]}><planeGeometry args={[0.12, zFar * 2]} /><meshBasicMaterial color={dark ? "#6ea0ff" : "#2563eb"} /></mesh>
      {M.monkeys.map((m, k) => <mesh key={m.id} position={[X(M.gapAt(m, i)), 0.08, ((k * 37) % 100) / 100 * zFar * 2 - zFar]}><sphereGeometry args={[0.07, 10, 8]} /><meshStandardMaterial color={dark ? "#5c6577" : "#a9b0bd"} /></mesh>)}
      {M.agents.map(p => {
        const at = spots[p.id]; if (!at) return null;
        const show = focus.level !== "world" ? focus.sp === p.sp : hover === p.id;
        const g = M.gapAt(p, i);
        return <Creature3D key={p.id} p={p} x={at[0]} z={at[1]} dark={dark} hot={hover === p.id || (focus.level === "creature" && focus.id === p.id)}
          dim={focus.level !== "world" && focus.sp !== p.sp}
          label={show ? <><b>{p.name}</b><span className={g >= 0 ? "gain" : "loss"}>{euro(Math.abs(g * cap))} {g >= 0 ? "ahead" : "behind"}</span></> : null}
          onOver={() => setHover(p.id)} onOut={() => setHover(null)} onPick={() => onPick(p.id)} />;
      })}
    </>
  );
});

function Camera({ target }: { target: { pos: THREE.Vector3; look: THREE.Vector3 } }) {
  const look = useRef(target.look.clone());
  const { camera } = useThree();
  useFrame((_s, dt) => {
    const k = 1 - Math.exp(-dt * 3.2);                         // ~250 ms to settle most of the way
    camera.position.lerp(target.pos, k); look.current.lerp(target.look, k); camera.lookAt(look.current);
  });
  return null;
}

function LuckField({ x0, x1, depth, dark }: { x0: number; x1: number; depth: number; dark: boolean }) {
  const ref = useRef<THREE.Mesh>(null);
  useFrame((_s, dt) => {
    const m = ref.current!; const k = 1 - Math.exp(-dt * 6), w = Math.max(0.05, x1 - x0);
    m.position.x += ((x0 + x1) / 2 - m.position.x) * k; m.scale.x += (w - m.scale.x) * k;
  });
  return <mesh ref={ref} rotation-x={-Math.PI / 2} position={[(x0 + x1) / 2, 0.006, 0]} scale={[Math.max(0.05, x1 - x0), 1, 1]}>
    <planeGeometry args={[1, depth]} /><meshBasicMaterial color={dark ? "#aab2c3" : "#78808f"} transparent opacity={dark ? 0.1 : 0.12} depthWrite={false} />
  </mesh>;
}

let blobTex: THREE.Texture | null = null;
/** One soft round texture shared by every creature's shadow (cheaper than real shadows, and calmer). */
function blob() {
  if (blobTex) return blobTex;
  const cv = document.createElement("canvas"); cv.width = cv.height = 64; const g = cv.getContext("2d")!;
  const gr = g.createRadialGradient(32, 32, 0, 32, 32, 32); gr.addColorStop(0, "rgba(255,255,255,1)"); gr.addColorStop(1, "rgba(255,255,255,0)");
  g.fillStyle = gr; g.fillRect(0, 0, 64, 64); blobTex = new THREE.CanvasTexture(cv); return blobTex;
}

type CProps = { p: Participant; x: number; z: number; dark: boolean; hot: boolean; dim: boolean; label: React.ReactNode; onOver: () => void; onOut: () => void; onPick: () => void };

function Creature3D({ p, x, z, dark, hot, dim, label, onOver, onOut, onPick }: CProps) {
  const c = useMemo(() => creatureOf(p), [p]);
  const R = 0.42, D = 0.26;
  const geo = useMemo(() => {
    const s = new THREE.Shape(bodyPoints(c, R, 0, 64).map(([a, b]) => new THREE.Vector2(a, -b)));
    const g = new THREE.ExtrudeGeometry(s, { depth: D, bevelEnabled: true, bevelThickness: 0.12, bevelSize: 0.08, bevelSegments: 5, curveSegments: 2 });
    g.translate(0, 0, -D / 2); g.computeVertexNormals(); return g;
  }, [c]);
  useEffect(() => () => geo.dispose(), [geo]);
  const color = useMemo(() => new THREE.Color(creatureFill(c, dark)), [c, dark]);
  const ref = useRef<THREE.Group>(null);
  useFrame(({ clock }, dt) => {
    const gr = ref.current!; const k = 1 - Math.exp(-dt * 5);
    gr.position.x += (x - gr.position.x) * k; gr.position.z += (z - gr.position.z) * k;
    const tt = clock.elapsedTime, br = c.stone ? 1 : 1 + 0.035 * Math.sin((tt / c.breath) * Math.PI * 2);
    const s = (hot ? 1.18 : 1) * br; gr.scale.x += (s - gr.scale.x) * k; gr.scale.y = gr.scale.z = gr.scale.x;
    gr.position.y = R * 1.05 + (c.stone ? 0 : Math.abs(Math.sin(tt * 1.4 + c.seed)) * 0.05);
  });
  const shadow = useRef<THREE.Mesh>(null);
  useFrame(() => { const g = ref.current!, m = shadow.current!; m.position.set(g.position.x, 0.02, g.position.z + 0.05); m.scale.set(c.elong * g.scale.x, 1, 0.6); });
  const eyeX = R * 0.55 * c.elong, eyeY = R * 0.18, front = D / 2 + 0.11;
  return (<>
    <mesh ref={shadow} rotation-x={-Math.PI / 2} position={[x, 0.02, z]}><circleGeometry args={[R * 1.1, 32]} /><meshBasicMaterial map={blob()} color="#000" transparent opacity={dark ? 0.5 : 0.22} depthWrite={false} /></mesh>
    <group ref={ref} position={[x, R, z]}>
      <mesh geometry={geo} onPointerOver={e => { e.stopPropagation(); onOver(); document.body.style.cursor = "pointer"; }}
        onPointerOut={() => { onOut(); document.body.style.cursor = ""; }} onClick={e => { e.stopPropagation(); onPick(); }}>
        <meshStandardMaterial color={color} roughness={0.5} metalness={0} transparent opacity={dim ? 0.18 : 1} />
      </mesh>
      {!c.stone && !dim && <group position={[eyeX, eyeY, front]}>
        <mesh><sphereGeometry args={[R * 0.13, 16, 12]} /><meshStandardMaterial color={dark ? "#0b0f19" : "#ffffff"} roughness={0.3} /></mesh>
        <mesh position={[R * 0.03, 0, R * 0.09]}><sphereGeometry args={[R * 0.06, 12, 10]} /><meshBasicMaterial color={dark ? "#ffffff" : "#1b2030"} /></mesh>
      </group>}
      {label && <Html position={[0, -R * 1.25, 0]} center zIndexRange={[30, 21]} style={{ pointerEvents: "none" }}><div className="tag">{label}</div></Html>}
    </group>
  </>);
}

createRoot(document.getElementById("root")!).render(<App />);
