// The living 3D world (Ultra / High tiers). Same encoding as the 2D view:
// colour = species, height = ahead/behind the S&P 500 (the water), size = money, glow = traded at the
// last open, grey shell = the luck band (where 90% of the random monkeys end up).
import { Canvas, useFrame, useThree, type ThreeEvent } from "@react-three/fiber";
import { OrbitControls, PerformanceMonitor, Sparkles, Stars } from "@react-three/drei";
import { Bloom, EffectComposer } from "@react-three/postprocessing";
import { useEffect, useMemo, useRef } from "react";
import * as THREE from "three";
import { COLOR, colorOf, type Model, type Participant } from "../data";
import type { Tier } from "../quality";

performance.mark("arena:world-chunk");
const FLAGS = new URLSearchParams(location.search);   // test switches: ?fx=0 (no bloom), ?tx=0 (no glass)

const R_AGENTS = 6.2, R_MONKEYS = 3.1, H_MAX = 3.2, R_WORLD = 9.5;
const reduce = typeof matchMedia !== "undefined" && matchMedia("(prefers-reduced-motion: reduce)").matches;

type Props = {
  M: Model; i: number; tier: Tier; paused: boolean; hover: string | null;
  onPick: (id: string) => void; onHover: (id: string | null, x?: number, y?: number) => void;
  onReady: (w: "3d") => void; onDegrade: () => void;
};

export default function World(props: Props) {
  const { tier, paused } = props;
  return (
    <Canvas
      frameloop={paused ? "never" : "always"}
      dpr={tier === "ultra" ? [1, 2] : [1, 1.5]}
      gl={{ antialias: false, powerPreference: "high-performance", alpha: false, stencil: false }}
      camera={{ fov: 40, near: 0.1, far: 200, position: [0, 8, 18] }}
      onCreated={({ gl }) => { gl.toneMapping = THREE.ACESFilmicToneMapping; gl.toneMappingExposure = 1.05; }}
      style={{ position: "absolute", inset: 0 }}
    >
      <PerformanceMonitor onDecline={props.onDegrade} flipflops={2} />
      <Scene {...props} />
      {FLAGS.get("fx") !== "0" && <EffectComposer multisampling={0} enableNormalPass={false}>
        <Bloom mipmapBlur intensity={tier === "ultra" ? 1.15 : 0.8} luminanceThreshold={0.55} luminanceSmoothing={0.2} radius={0.75} />
      </EffectComposer>}
    </Canvas>
  );
}

function Scene({ M, i, tier, hover, onPick, onHover, onReady }: Props) {
  const { size, camera, scene } = useThree();
  const moved = useRef(false);
  const ready = useRef(false);

  // background + fog
  useEffect(() => {
    scene.background = new THREE.Color("#03060f");
    scene.fog = new THREE.Fog("#03060f", 20, 48);
  }, [scene]);

  // frame the whole arena for any screen shape; phones look down more steeply
  useEffect(() => {
    const cam = camera as THREE.PerspectiveCamera;
    const aspect = size.width / Math.max(size.height, 1), tall = aspect < 0.8;
    cam.fov = tall ? 50 : 40; cam.aspect = aspect; cam.updateProjectionMatrix();
    if (moved.current) return;
    const v = THREE.MathUtils.degToRad(cam.fov) / 2, h = Math.atan(Math.tan(v) * aspect);
    const d = Math.max((tall ? 8.2 : 10.5) / Math.tan(h), 7 / Math.tan(v));
    cam.position.copy(new THREE.Vector3(0, tall ? 0.75 : 0.5, 1).normalize().multiplyScalar(d));
    const f = scene.fog as THREE.Fog | null; if (f) { f.near = d * 1.25; f.far = d * 2.8; }
  }, [size, camera, scene]);

  // first frame callback runs before the first draw; the next animation frame means it is on screen
  useFrame(() => { if (!ready.current) { ready.current = true; onReady("3d"); requestAnimationFrame(() => { performance.mark("arena:3d-drawn"); (window as unknown as { __arenaReport?: () => void }).__arenaReport?.(); }); } });

  // height scale: the largest gap over the whole season maps to H_MAX, so replayed days are comparable
  const yOf = (g: number) => THREE.MathUtils.clamp(g / M.span, -1, 1) * H_MAX;
  const band = M.luckAt(i), active = M.activeAt(i), rk = M.rankAt(i).rank, started = i > 0 && M.moved;

  const placed = useMemo(() => {
    const per: Record<string, Participant[]> = {};
    M.A.p.filter(p => p.type === "agent").forEach(p => (per[p.sp || ""] ||= []).push(p));
    const out: { p: Participant; pos: [number, number, number] }[] = [];
    const S = M.species;
    S.forEach((sp, si) => {
      const list = per[sp] || [], n = list.length, w = (Math.PI * 2) / S.length, a0 = (si / S.length) * Math.PI * 2 - Math.PI / 2;
      list.forEach((p, k) => {
        const a = a0 + w * (0.18 + 0.64 * (n === 1 ? 0.5 : k / (n - 1)));
        out.push({ p, pos: [Math.cos(a) * R_AGENTS, 0, Math.sin(a) * R_AGENTS] });
      });
    });
    M.A.p.filter(p => p.type === "monkey").forEach((p, i, arr) => {
      const a = (i / arr.length) * Math.PI * 2 + 0.3;
      out.push({ p, pos: [Math.cos(a) * R_MONKEYS, 0, Math.sin(a) * R_MONKEYS] });
    });
    if (M.equal) out.push({ p: M.equal, pos: [0, 0, 0] });
    return out;
  }, [M]);

  const pointer = {
    onPointerOver: (e: ThreeEvent<PointerEvent>, id: string) => { e.stopPropagation(); document.body.style.cursor = "pointer"; onHover(id, e.nativeEvent.clientX, e.nativeEvent.clientY); },
    onPointerMove: (e: ThreeEvent<PointerEvent>, id: string) => { e.stopPropagation(); onHover(id, e.nativeEvent.clientX, e.nativeEvent.clientY); },
    onPointerOut: () => { document.body.style.cursor = ""; onHover(null); },
    onClick: (e: ThreeEvent<MouseEvent>, id: string) => { e.stopPropagation(); if (e.delta < 6) onPick(id); },
  };

  return (
    <>
      <hemisphereLight args={["#9fb8ff", "#0b0f1a", 0.9]} />
      <directionalLight position={[6, 12, 8]} intensity={2.4} />
      <pointLight position={[-8, 4, -6]} intensity={30} distance={30} color="#4fd1ff" />
      <pointLight position={[8, 3, 6]} intensity={14} distance={26} color="#b07cff" />
      <Stars radius={60} depth={30} count={tier === "ultra" ? 2500 : 1000} factor={3} saturation={0} fade speed={reduce ? 0 : 0.4} />
      {tier === "ultra" && !reduce && <Sparkles count={60} scale={[18, 6, 18]} size={2} speed={0.25} opacity={0.35} color="#9fd8ff" />}
      <Floor />
      <Water />
      <LuckBand lo={band ? yOf(band[0]) : 0} hi={band ? yOf(band[1]) : 0} on={!!band} />
      {placed.map(({ p, pos }) => (
        <Figure key={p.id} p={p} pos={pos} y={yOf(M.gapAt(p, i))} value={M.valueAt(p, i)} tier={tier} active={active.has(p.id)} rank={started && p.type === "agent" ? rk[p.id] : 0}
          capital={M.A.meta.capital} hot={hover === p.id} handlers={pointer} />
      ))}
      <SpeciesLabels M={M} />
      <OrbitControls makeDefault enablePan={false} enableDamping dampingFactor={0.08} minDistance={7} maxDistance={45}
        minPolarAngle={0.35} maxPolarAngle={1.45} autoRotate={!reduce} autoRotateSpeed={0.35} target={[0, 0.4, 0]}
        onStart={(e) => { moved.current = true; if (e?.target) (e.target as unknown as { autoRotate: boolean }).autoRotate = false; }} />
    </>
  );
}

function Floor() {
  return (
    <group position={[0, -H_MAX - 0.6, 0]}>
      <mesh rotation-x={-Math.PI / 2}><circleGeometry args={[R_WORLD, 96]} /><meshStandardMaterial color="#0a1020" roughness={0.9} metalness={0.15} /></mesh>
      {[R_MONKEYS, R_AGENTS, 8.6].map((r, i) => (
        <mesh key={r} rotation-x={-Math.PI / 2} position-y={0.01}><ringGeometry args={[r - 0.015, r + 0.015, 128]} /><meshBasicMaterial color="#2a3a60" transparent opacity={i === 2 ? 0.5 : 0.85} /></mesh>
      ))}
    </group>
  );
}

// The S&P 500 as a living water surface: ripples and a bright shore.
function Water() {
  const mat = useMemo(() => new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, side: THREE.DoubleSide,
    uniforms: { uTime: { value: 0 }, uColor: { value: new THREE.Color(COLOR.index) } },
    vertexShader: `varying vec2 vP; void main(){ vP = position.xy; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `uniform float uTime; uniform vec3 uColor; varying vec2 vP;
      void main(){
        float r = length(vP) / ${R_WORLD.toFixed(1)};
        float rip = 0.5 + 0.5 * sin(r * 46.0 - uTime * 1.4);
        float rings = smoothstep(0.92, 1.0, rip) * 0.22 * (1.0 - r);
        float shore = smoothstep(0.965, 0.995, r) * (1.0 - smoothstep(0.995, 1.0, r));
        float a = 0.12 + rings + shore * 0.6;
        vec3 c = uColor * (0.5 + rings * 2.0) + vec3(0.6, 0.9, 1.0) * shore * 0.9;
        gl_FragColor = vec4(c, a);
      }`,
  }), []);
  useFrame((_, dt) => { if (!reduce) mat.uniforms.uTime.value += dt; });
  return <mesh rotation-x={-Math.PI / 2} material={mat}><circleGeometry args={[R_WORLD, 128]} /></mesh>;
}

// Luck band: a translucent shell between the 5th and 95th percentile of the monkeys, with glowing edges.
function LuckBand({ lo, hi, on }: { lo: number; hi: number; on: boolean }) {
  const r = R_AGENTS + 0.9;
  const shell = useRef<THREE.Mesh>(null), top = useRef<THREE.Mesh>(null), bottom = useRef<THREE.Mesh>(null), grp = useRef<THREE.Group>(null);
  const cur = useRef({ lo, hi });
  const mat = useMemo(() => new THREE.ShaderMaterial({
    transparent: true, depthWrite: false, side: THREE.DoubleSide, uniforms: { uTime: { value: 0 } },
    vertexShader: `varying vec2 vUv; void main(){ vUv = uv; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`,
    fragmentShader: `uniform float uTime; varying vec2 vUv;
      void main(){
        float scan = smoothstep(0.0, 0.02, abs(fract(vUv.y * 6.0 - uTime * 0.15) - 0.5) - 0.48);
        float edge = smoothstep(0.08, 0.0, vUv.y) + smoothstep(0.92, 1.0, vUv.y);
        gl_FragColor = vec4(vec3(0.72, 0.76, 0.85), 0.045 + edge * 0.18 + (1.0 - scan) * 0.03);
      }`,
  }), []);
  useFrame((_, dt) => {
    if (!reduce) mat.uniforms.uTime.value += dt;
    const c = cur.current, k = reduce ? 1 : Math.min(1, dt * 6);
    c.lo += (lo - c.lo) * k; c.hi += (hi - c.hi) * k;
    const h = Math.max(c.hi - c.lo, 0.04);
    if (shell.current) { shell.current.position.y = c.lo + h / 2; shell.current.scale.y = h; }
    if (bottom.current) bottom.current.position.y = c.lo;
    if (top.current) top.current.position.y = c.lo + h;
    if (grp.current) grp.current.visible = on;
  });
  return (
    <group ref={grp}>
      <mesh ref={shell} material={mat}><cylinderGeometry args={[r, r, 1, 128, 1, true]} /></mesh>
      {[bottom, top].map((ref, k) => (
        <mesh key={k} ref={ref} rotation-x={-Math.PI / 2}><ringGeometry args={[r - 0.025, r + 0.025, 160]} /><meshBasicMaterial color="#b9c2d6" transparent opacity={0.3} /></mesh>
      ))}
    </group>
  );
}

const crystalGeo = (() => { const g = new THREE.OctahedronGeometry(0.42, 0); g.scale(1, 1.55, 1); return g; })();
const stoneGeo = new THREE.DodecahedronGeometry(0.26, 0);
const stemGeo = (() => { const g = new THREE.CylinderGeometry(0.012, 0.012, 1, 6, 1, true); g.translate(0, 0.5, 0); return g; })();

function Figure({ p, pos, y, value, tier, active, rank, capital, hot, handlers }: {
  p: Participant; pos: [number, number, number]; y: number; value: number; tier: Tier; active: boolean; rank: number; capital: number; hot: boolean;
  handlers: {
    onPointerOver: (e: ThreeEvent<PointerEvent>, id: string) => void; onPointerMove: (e: ThreeEvent<PointerEvent>, id: string) => void;
    onPointerOut: () => void; onClick: (e: ThreeEvent<MouseEvent>, id: string) => void;
  };
}) {
  const holder = useRef<THREE.Group>(null), body = useRef<THREE.Mesh>(null), stem = useRef<THREE.Mesh>(null);
  const curY = useRef(0);
  const col = useMemo(() => new THREE.Color(colorOf(p)), [p]);
  const s = p.type === "agent" ? THREE.MathUtils.clamp(Math.pow((value || capital) / capital, 2.2), 0.6, 1.8) : 1;
  const phase = useMemo(() => Math.random() * Math.PI * 2, []);
  const t0 = useRef(performance.now());
  useFrame((st, dt) => {
    const e = reduce ? 1 : 1 - Math.pow(1 - Math.min(1, (performance.now() - t0.current) / 1400), 3);
    curY.current += (y - curY.current) * (reduce ? 1 : Math.min(1, dt * 7));   // glide to the replayed day
    const yy = curY.current * e;
    if (holder.current) holder.current.position.y = yy + (reduce ? 0 : Math.sin(st.clock.elapsedTime * 1.1 + phase) * 0.05);
    if (stem.current) { stem.current.scale.y = Math.max(Math.abs(yy), 0.001); stem.current.rotation.x = yy < 0 ? Math.PI : 0; }
    if (body.current) {
      if (!reduce) body.current.rotation.y += dt * 0.35;
      const target = s * (hot ? 1.25 : 1);
      body.current.scale.setScalar(THREE.MathUtils.lerp(body.current.scale.x, target, 0.2));
      if (p.type === "agent") {
        const m = body.current.material as THREE.MeshStandardMaterial;
        m.emissiveIntensity = active && !reduce ? 1.1 + 0.6 * Math.sin(st.clock.elapsedTime * 2.4 + phase) : active ? 1.4 : (tier === "ultra" ? 0.55 : 0.35);
      }
    }
  });
  const ev = {
    onPointerOver: (e: ThreeEvent<PointerEvent>) => handlers.onPointerOver(e, p.id),
    onPointerMove: (e: ThreeEvent<PointerEvent>) => handlers.onPointerMove(e, p.id),
    onPointerOut: handlers.onPointerOut,
    onClick: (e: ThreeEvent<MouseEvent>) => handlers.onClick(e, p.id),
  };
  return (
    <group position={pos}>
      <group ref={holder}>
        {p.type === "agent" ? (
          <mesh ref={body} geometry={crystalGeo} {...ev}>
            {tier === "ultra" && FLAGS.get("tx") !== "0"
              ? <meshPhysicalMaterial color={col} emissive={col} emissiveIntensity={active ? 1.4 : 0.55} roughness={0.12} metalness={0.05}
                  transmission={0.3} thickness={0.5} ior={1.6} iridescence={0.6} iridescenceIOR={1.3} clearcoat={1} flatShading transparent opacity={0.95} />
              : <meshStandardMaterial color={col} emissive={col} emissiveIntensity={active ? 1.4 : 0.35} roughness={0.18} metalness={0.1} flatShading />}
          </mesh>
        ) : p.type === "monkey" ? (
          <mesh ref={body} geometry={stoneGeo} {...ev}><meshStandardMaterial color={col} roughness={0.75} metalness={0.1} flatShading /></mesh>
        ) : (
          <mesh ref={body} rotation-x={Math.PI / 2} {...ev}><torusGeometry args={[0.55, 0.06, 16, 80]} /><meshStandardMaterial color="#ffffff" emissive="#ffffff" emissiveIntensity={0.9} toneMapped={false} /></mesh>
        )}
        {rank > 0 && rank <= 3 && <Medal rank={rank} y={1.05 * s} />}
      </group>
      <mesh ref={stem} geometry={stemGeo}>
        <meshBasicMaterial color={col} transparent opacity={0.45} toneMapped={false} />
      </mesh>
      <mesh rotation-x={-Math.PI / 2} position-y={0.01}><circleGeometry args={[0.09, 20]} /><meshBasicMaterial color={col} transparent opacity={0.85} toneMapped={false} /></mesh>
    </group>
  );
}

function canvasTexture(w: number, h: number, draw: (g: CanvasRenderingContext2D) => void) {
  const c = document.createElement("canvas"); c.width = w; c.height = h; draw(c.getContext("2d")!);
  const t = new THREE.CanvasTexture(c); t.colorSpace = THREE.SRGBColorSpace; return t;
}

function Medal({ rank, y }: { rank: number; y: number }) {
  const tex = useMemo(() => canvasTexture(96, 96, g => {
    g.beginPath(); g.arc(48, 48, 40, 0, Math.PI * 2); g.fillStyle = ["", COLOR.gold, COLOR.silver, COLOR.bronze][rank]; g.fill();
    g.lineWidth = 5; g.strokeStyle = "rgba(255,255,255,.7)"; g.stroke();
    g.fillStyle = "rgba(0,0,0,.72)"; g.font = "700 50px 'Geist Mono Variable', ui-monospace, monospace"; g.textAlign = "center"; g.textBaseline = "middle"; g.fillText(String(rank), 48, 52);
  }), [rank]);
  return <sprite position-y={y} scale={0.42}><spriteMaterial map={tex} transparent depthWrite={false} toneMapped={false} /></sprite>;
}

function SpeciesLabels({ M }: { M: Model }) {
  const S = M.species;
  return <>{S.map((sp, si) => <SpeciesLabel key={sp} text={(M.A.species[sp]?.label || sp).toUpperCase()} color={colorOf({ type: "agent", sp } as Participant)} angle={((si + 0.5) / S.length) * Math.PI * 2 - Math.PI / 2} />)}</>;
}
function SpeciesLabel({ text, color, angle }: { text: string; color: string; angle: number }) {
  const tex = useMemo(() => canvasTexture(512, 96, g => {
    g.font = "600 44px 'Geist Variable', system-ui, sans-serif"; g.textAlign = "center"; g.textBaseline = "middle";
    g.shadowColor = color; g.shadowBlur = 18; g.fillStyle = color; g.letterSpacing = "10px"; g.fillText(text, 256, 48);
  }), [text, color]);
  return <sprite position={[Math.cos(angle) * 8.9, 0.35, Math.sin(angle) * 8.9]} scale={[3.2, 0.6, 1]}>
    <spriteMaterial map={tex} transparent depthWrite={false} depthTest={false} toneMapped={false} />
  </sprite>;
}
