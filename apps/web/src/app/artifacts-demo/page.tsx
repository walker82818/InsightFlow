"use client";

import { useState } from "react";
import ArtifactViewer, { type ArtifactError } from "@/components/ArtifactViewer";

const FIXTURES = [
  {
    id: "echarts-line",
    name: "ECharts 折线图（CDN import）",
    spec: {
      title: "季度销量趋势",
      code: `import * as echarts from "echarts";
import { useEffect, useRef } from "react";

export default function App({ data }) {
  const ref = useRef(null);
  useEffect(() => {
    const chart = echarts.init(ref.current);
    chart.setOption({
      title: { text: data.title, left: "center", textStyle: { fontSize: 14 } },
      tooltip: { trigger: "axis" },
      grid: { left: 48, right: 24, top: 48, bottom: 32 },
      xAxis: { type: "category", data: data.categories },
      yAxis: { type: "value" },
      series: [
        {
          type: "line",
          data: data.values,
          smooth: true,
          symbolSize: 8,
          lineStyle: { width: 3 },
          areaStyle: { opacity: 0.15 },
        },
      ],
    });
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, []);
  return <div ref={ref} style={{ height: 320, width: "100%" }} />;
}`,
      data: {
        title: "季度销量",
        categories: ["Q1", "Q2", "Q3", "Q4"],
        values: [120, 200, 150, 80],
      },
    },
  },
  {
    id: "table",
    name: "数据表格（React + data）",
    spec: {
      title: "订单明细",
      code: `export default function App({ data }) {
  return (
    <div style={{ padding: 16, fontFamily: "ui-sans-serif, system-ui" }}>
      <h3 style={{ margin: "0 0 12px", fontSize: 15, fontWeight: 600 }}>{data.title}</h3>
      <table style={{ width: "100%", borderCollapse: "collapse", fontSize: 13 }}>
        <thead>
          <tr>
            {data.columns.map((c) => (
              <th key={c} style={{ textAlign: "left", padding: "8px 10px", borderBottom: "2px solid #d8c9b8", color: "#8a6f55" }}>{c}</th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.rows.map((row, i) => (
            <tr key={i}>
              {data.columns.map((c) => (
                <td key={c} style={{ padding: "8px 10px", borderBottom: "1px solid #eee3d6" }}>{String(row[c])}</td>
              ))}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}`,
      data: {
        title: "Top 订单",
        columns: ["order_id", "region", "amount", "status"],
        rows: [
          { order_id: "A1024", region: "华东", amount: 3200, status: "已发货" },
          { order_id: "A1025", region: "华南", amount: 1850, status: "待支付" },
          { order_id: "A1026", region: "华北", amount: 5600, status: "已完成" },
        ],
      },
    },
  },
  {
    id: "kpi",
    name: "KPI 卡片（自定义样式）",
    spec: {
      title: "关键指标",
      code: `export default function App({ data }) {
  return (
    <div style={{ display: "grid", gridTemplateColumns: "repeat(3, 1fr)", gap: 12, padding: 16 }}>
      {data.map((kpi) => (
        <div key={kpi.label} style={{ borderRadius: 14, border: "1px solid #eee3d6", padding: "14px 16px", background: "#fffdfa" }}>
          <div style={{ fontSize: 12, color: "#8a6f55" }}>{kpi.label}</div>
          <div style={{ fontSize: 26, fontWeight: 700, marginTop: 4, color: "#2c2a28" }}>
            {kpi.value}
            {kpi.unit && <span style={{ fontSize: 13, fontWeight: 500, color: "#8a6f55", marginLeft: 4 }}>{kpi.unit}</span>}
          </div>
          <div style={{ fontSize: 12, marginTop: 4, color: kpi.delta >= 0 ? "#2e7d4f" : "#b3261e" }}>
            {kpi.delta >= 0 ? "▲" : "▼"} {Math.abs(kpi.delta)}% 环比
          </div>
        </div>
      ))}
    </div>
  );
}`,
      data: [
        { label: "总销售额", value: "¥128.4万", unit: "", delta: 12.5 },
        { label: "订单数", value: "3,286", unit: "单", delta: -3.2 },
        { label: "客单价", value: "¥390", unit: "", delta: 8.9 },
      ],
    },
  },
  {
    id: "error",
    name: "运行时错误（自愈通道）",
    spec: {
      title: "故意报错",
      code: `export default function App() {
  throw new Error("boom: 演示运行时错误上报");
}`,
    },
  },
  {
    id: "illegal-import",
    name: "白名单拦截（axios）",
    spec: {
      title: "非法 import",
      code: `import axios from "axios";
export default function App() {
  return <div>不应渲染</div>;
}`,
    },
  },
] as const;

export default function ArtifactsDemoPage() {
  const [errors, setErrors] = useState<Record<string, ArtifactError | undefined>>(
    {},
  );

  return (
    <div className="space-y-8">
      <div>
        <div className="eyebrow">Agent2UI · P0 冒烟</div>
        <h1 className="mt-1 font-display text-2xl font-bold text-ink">
          Artifact 沙箱渲染演示
        </h1>
        <p className="mt-2 max-w-2xl text-sm leading-relaxed text-muted">
          手写 TSX → 严格隔离 iframe（esbuild-wasm 编译）→ React 挂载。验证
          echarts CDN import、数据注入、运行时错误回传、白名单拦截四条链路。
        </p>
      </div>

      <div className="grid gap-5 lg:grid-cols-2">
        {FIXTURES.map((f) => (
          <section key={f.id} className="card flex flex-col p-5">
            <div className="mb-3 flex items-center justify-between">
              <h2 className="font-display text-sm font-semibold text-ink">
                {f.name}
              </h2>
              {errors[f.id] && (
                <span className="tag bg-danger/10 text-danger">有错误</span>
              )}
            </div>
            <ArtifactViewer
              spec={f.spec}
              minHeight={180}
              onError={(e) =>
                setErrors((prev) => ({ ...prev, [f.id]: e }))
              }
            />
            {errors[f.id] && (
              <div className="mt-3 rounded-xl border border-danger/20 bg-danger/5 px-3 py-2.5 font-mono text-xs leading-relaxed text-danger">
                {errors[f.id]?.message}
                {errors[f.id]?.line ? ` (line ${errors[f.id]?.line})` : ""}
              </div>
            )}
          </section>
        ))}
      </div>
    </div>
  );
}
