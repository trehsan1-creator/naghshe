import { useMemo, useRef } from "react";
import { Canvas } from "@react-three/fiber";
import { Grid, OrbitControls } from "@react-three/drei";
import * as THREE from "three";
import { useWorkspace } from "../store/workspace";
import { elevationColor, extentOfPoints } from "../lib/plot";

interface SceneFrame {
  cx: number;
  cy: number;
  zMin: number;
  span: number;
  exaggeration: number;
}

function useFrame3D(): SceneFrame | null {
  const surface = useWorkspace((s) => s.surface);
  const points = useWorkspace((s) => s.points);
  const exaggeration = useWorkspace((s) => s.verticalExaggeration);

  return useMemo(() => {
    const extent =
      surface?.extent
        ? {
            minX: surface.extent.min_x,
            maxX: surface.extent.max_x,
            minY: surface.extent.min_y,
            maxY: surface.extent.max_y,
            minZ: surface.extent.min_z ?? 0,
            maxZ: surface.extent.max_z ?? 1,
          }
        : extentOfPoints(points);
    if (!extent) return null;
    return {
      cx: (extent.minX + extent.maxX) / 2,
      cy: (extent.minY + extent.maxY) / 2,
      zMin: extent.minZ,
      span: Math.max(extent.maxX - extent.minX, extent.maxY - extent.minY, 1),
      exaggeration,
    };
  }, [surface, points, exaggeration]);
}

const toLocal = (frame: SceneFrame, x: number, y: number, z: number): [number, number, number] => [
  x - frame.cx,
  (z - frame.zMin) * frame.exaggeration,
  -(y - frame.cy),
];

function TinMesh({ frame }: { frame: SceneFrame }) {
  const surface = useWorkspace((s) => s.surface);
  const visible = useWorkspace((s) => s.layers.tin);

  const geometry = useMemo(() => {
    if (!surface) return null;
    const { vertices, faces } = surface.mesh;
    const positions: number[] = [];
    const colors: number[] = [];
    const minZ = surface.stats.min_z as number;
    const maxZ = surface.stats.max_z as number;
    for (const face of faces) {
      const [a, b, c] = face;
      for (const index of [a, b, c]) {
        const vertex = vertices[index];
        const [x, y, z] = toLocal(frame, vertex[0], vertex[1], vertex[2]);
        positions.push(x, y, z);
        const [r, g, bl] = elevationColor(vertex[2], minZ, maxZ);
        colors.push(r / 255, g / 255, bl / 255);
      }
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geom.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    geom.computeVertexNormals();
    geom.computeBoundingSphere();
    return geom;
  }, [surface, frame]);

  if (!geometry || !visible) return null;
  return (
    <mesh geometry={geometry} castShadow={false} receiveShadow={false}>
      <meshStandardMaterial
        vertexColors
        flatShading
        side={THREE.DoubleSide}
        roughness={0.86}
        metalness={0.08}
        polygonOffset
        polygonOffsetFactor={1}
        polygonOffsetUnits={1}
      />
    </mesh>
  );
}

function Wireframe({ frame }: { frame: SceneFrame }) {
  const surface = useWorkspace((s) => s.surface);
  const visible = useWorkspace((s) => s.layers.tin);

  const geometry = useMemo(() => {
    if (!surface) return null;
    const { vertices, faces } = surface.mesh;
    const seen = new Set<string>();
    const positions: number[] = [];
    const add = (i: number, j: number) => {
      const key = i < j ? `${i}_${j}` : `${j}_${i}`;
      if (seen.has(key)) return;
      seen.add(key);
      const p = toLocal(frame, vertices[i][0], vertices[i][1], vertices[i][2]);
      const q = toLocal(frame, vertices[j][0], vertices[j][1], vertices[j][2]);
      positions.push(...p, ...q);
    };
    for (const face of faces) {
      add(face[0], face[1]);
      add(face[1], face[2]);
      add(face[2], face[0]);
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    return geom;
  }, [surface, frame]);

  if (!geometry || !visible) return null;
  return (
    <lineSegments geometry={geometry}>
      <lineBasicMaterial color="#1f3b4d" transparent opacity={0.55} />
    </lineSegments>
  );
}

function ContourLines({ frame }: { frame: SceneFrame }) {
  const surface = useWorkspace((s) => s.surface);
  const layers = useWorkspace((s) => s.layers);

  const groups = useMemo(() => {
    if (!surface) return [];
    return surface.contours
      .filter((c) => (c.is_major ? layers.contoursMajor : layers.contoursMinor))
      .map((contour) => {
        const positions: number[] = [];
        for (let i = 1; i < contour.points.length; i += 1) {
          const p = contour.points[i - 1];
          const q = contour.points[i];
          positions.push(...toLocal(frame, p[0], p[1], p[2]), ...toLocal(frame, q[0], q[1], q[2]));
        }
        const geom = new THREE.BufferGeometry();
        geom.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
        return { geom, major: contour.is_major, id: `${contour.index}-${contour.elevation}` };
      });
  }, [surface, frame, layers.contoursMajor, layers.contoursMinor]);

  return (
    <group>
      {groups.map((group) => (
        <lineSegments key={group.id} geometry={group.geom} position={[0, 0.02, 0]}>
          <lineBasicMaterial
            color={group.major ? "#E879F9" : "#5F6C7E"}
            transparent
            opacity={group.major ? 0.95 : 0.6}
          />
        </lineSegments>
      ))}
    </group>
  );
}

function PointCloud({ frame }: { frame: SceneFrame }) {
  const points = useWorkspace((s) => s.points);
  const visible = useWorkspace((s) => s.layers.points);

  const geometry = useMemo(() => {
    if (!points.length) return null;
    const positions: number[] = [];
    const colors: number[] = [];
    const extent = extentOfPoints(points);
    for (const point of points) {
      const [x, y, z] = toLocal(frame, point.easting, point.northing, point.elevation ?? frame.zMin);
      positions.push(x, y, z);
      const [r, g, b] = elevationColor(
        point.elevation ?? frame.zMin,
        extent?.minZ ?? 0,
        extent?.maxZ ?? 1,
      );
      colors.push(r / 255, g / 255, b / 255);
    }
    const geom = new THREE.BufferGeometry();
    geom.setAttribute("position", new THREE.Float32BufferAttribute(positions, 3));
    geom.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    return geom;
  }, [points, frame]);

  if (!geometry || !visible) return null;
  return (
    <points geometry={geometry} position={[0, 0.03, 0]}>
      <pointsMaterial size={Math.max(frame.span * 0.008, 0.15)} vertexColors sizeAttenuation />
    </points>
  );
}

function Stage({ frame }: { frame: SceneFrame }) {
  const groupRef = useRef<THREE.Group>(null);
  return (
    <group ref={groupRef}>
      <TinMesh frame={frame} />
      <Wireframe frame={frame} />
      <ContourLines frame={frame} />
      <PointCloud frame={frame} />
      <Grid
        position={[0, -0.35, 0]}
        args={[frame.span * 1.6, frame.span * 1.6]}
        cellSize={5}
        cellThickness={0.5}
        cellColor="#1b2a36"
        sectionSize={25}
        sectionThickness={1}
        sectionColor="#24506a"
        fadeDistance={frame.span * 3}
        fadeStrength={1.4}
        infiniteGrid
      />
    </group>
  );
}

export default function Scene3D() {
  const frame = useFrame3D();
  const surface = useWorkspace((s) => s.surface);
  const exaggeration = useWorkspace((s) => s.verticalExaggeration);
  const pointCount = useWorkspace((s) => s.points.length);

  if (!frame) {
    return (
      <div className="absolute inset-0 flex items-center justify-center text-xs text-muted">
        نقطه‌ای برای نمایش نیست — ابتدا فایل برداشت را وارد کنید.
      </div>
    );
  }

  const distance = frame.span * 0.85;
  const camera: [number, number, number] = [distance * 0.6, distance * 0.55, distance * 0.75];

  return (
    <div className="absolute inset-0">
      <Canvas
        dpr={[1, 2]}
        camera={{ position: camera, fov: 45, near: 0.1, far: frame.span * 40 }}
        gl={{ antialias: true, logarithmicDepthBuffer: true }}
      >
        <color attach="background" args={["#0d0f12"]} />
        <fog attach="fog" args={["#0d0f12", frame.span * 1.8, frame.span * 5]} />
        <ambientLight intensity={0.75} />
        <hemisphereLight args={["#8fd6ff", "#101418", 0.55]} />
        <directionalLight position={[frame.span, frame.span * 1.4, frame.span * 0.8]} intensity={1.35} />
        <directionalLight position={[-frame.span, frame.span * 0.6, -frame.span]} intensity={0.35} color="#f472b6" />
        <OrbitControls
          makeDefault
          enableDamping
          dampingFactor={0.08}
          target={[0, frame.span * 0.04, 0]}
          maxPolarAngle={Math.PI / 2.05}
          minDistance={frame.span * 0.15}
          maxDistance={frame.span * 6}
        />
        <Stage frame={frame} />
        <axesHelper args={[Math.max(frame.span * 0.12, 2)]} />
      </Canvas>

      <div className="absolute top-3 start-3 panel bg-panel/90 px-2.5 py-1.5 text-[9px] font-mono text-muted leading-relaxed pointer-events-none">
        <div className="text-cyan">
          سطح سه‌بعدی · {surface ? `موتور ${surface.mesh.stats.engine}` : "فقط نقاط"}
        </div>
        <div>
          {surface
            ? `${surface.mesh.stats.triangles} مثلث · ${surface.contours.length} خط تراز`
            : `${pointCount} نقطه`}
        </div>
        <div>اغراق ارتفاع ×{exaggeration.toFixed(1)} · چرخش با درگ · زوم با اسکرول</div>
      </div>

      <div className="absolute bottom-3 start-3 panel bg-panel/90 px-2.5 py-1.5 flex items-center gap-3 text-[9px] font-mono text-muted">
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-sm" style={{ background: "#38BDF8" }} /> کمینه ارتفاع
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-sm" style={{ background: "#A3E635" }} /> میانه
        </span>
        <span className="flex items-center gap-1">
          <span className="w-2 h-2 rounded-sm" style={{ background: "#F472B6" }} /> بیشینه
        </span>
        <span className="text-edge">|</span>
        <span>محور قائم = ارتفاع (متر × {exaggeration.toFixed(1)})</span>
      </div>
    </div>
  );
}
