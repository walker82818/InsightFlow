"use client";

import { useMemo } from "react";
import { Canvas } from "@react-three/fiber";
import { OrbitControls, Grid, Text } from "@react-three/drei";
import type { ChartSpec } from "@/types/analysis";

type Triple = [number, number, number];

function toNum(v: unknown): number {
  const n = Number(v);
  return Number.isFinite(n) ? n : 0;
}

// 将一组数值线性映射到 [minOut, maxOut]
function normalize(values: number[], minOut: number, maxOut: number): number[] {
  if (values.length === 0) return [];
  const min = Math.min(...values);
  const max = Math.max(...values);
  const span = max - min || 1;
  return values.map((v) => minOut + ((v - min) / span) * (maxOut - minOut));
}

// 高度（0..1）映射到颜色，低->蓝 高->红
function colorRamp(t: number): string {
  const c = Math.max(0, Math.min(1, t));
  const r = Math.round(40 + c * 215);
  const g = Math.round(120 - Math.abs(c - 0.5) * 160);
  const b = Math.round(220 - c * 180);
  return `rgb(${r}, ${Math.max(0, g)}, ${Math.max(0, b)})`;
}

function usePoints(spec: ChartSpec): Triple[] {
  const { xField, yField, zField, data } = spec;
  const xf = Array.isArray(xField) ? xField[0] : xField;
  const yf = Array.isArray(yField) ? yField[0] : yField;
  return useMemo(() => {
    const capped = data.slice(0, 150);
    const xs = normalize(capped.map((d) => toNum(d[xf!])), -4, 4);
    const ys = normalize(capped.map((d) => toNum(d[yf!])), -4, 4);
    const zs = zField
      ? normalize(capped.map((d) => toNum(d[zField])), -4, 4)
      : capped.map(() => 0);
    return capped.map((_, i) => [xs[i], ys[i], zs[i]] as Triple);
  }, [spec]);
}

function Scatter3D({ spec }: { spec: ChartSpec }) {
  const points = usePoints(spec);
  return (
    <>
      {points.map((p, i) => (
        <mesh key={i} position={p}>
          <sphereGeometry args={[0.12, 16, 16]} />
          <meshStandardMaterial color={colorRamp((i % 30) / 30)} />
        </mesh>
      ))}
    </>
  );
}

function Bar3D({ spec }: { spec: ChartSpec }) {
  const points = usePoints(spec);
  // 在 XZ 平面铺成网格，柱高取 Y
  const side = Math.ceil(Math.sqrt(points.length));
  return (
    <>
      {points.map((p, i) => {
        const gx = (i % side) - side / 2;
        const gz = Math.floor(i / side) - side / 2;
        const h = (p[1] + 4) / 8; // 0..1
        const height = 0.2 + h * 4;
        return (
          <mesh key={i} position={[gx * 0.7, height / 2 - 2, gz * 0.7]}>
            <boxGeometry args={[0.5, height, 0.5]} />
            <meshStandardMaterial color={colorRamp(h)} />
          </mesh>
        );
      })}
    </>
  );
}

export default function Chart3D({ spec }: { spec: ChartSpec }) {
  const isBar = spec.type === "3d_bar";
  return (
    <div className="h-[340px] w-full rounded-lg bg-gradient-to-b from-slate-900 to-slate-800">
      <Canvas camera={{ position: [7, 6, 7], fov: 45 }}>
        <ambientLight intensity={0.7} />
        <directionalLight position={[5, 10, 7]} intensity={1.1} />
        <axesHelper args={[5]} />
        <Grid
          args={[10, 10]}
          position={[0, -2, 0]}
          cellColor="#334155"
          sectionColor="#475569"
          cellSize={1}
          sectionSize={5}
          infiniteGrid={false}
        />
        {isBar ? <Bar3D spec={spec} /> : <Scatter3D spec={spec} />}
        <Text position={[0, 4.6, 0]} fontSize={0.35} color="#e2e8f0" anchorX="center">
          {spec.title ?? "3D 可视化"}
        </Text>
        <OrbitControls enablePan enableZoom enableRotate />
      </Canvas>
    </div>
  );
}
