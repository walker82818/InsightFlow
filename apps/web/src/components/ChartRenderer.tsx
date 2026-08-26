"use client";

import { useEffect, useRef } from "react";
import * as echarts from "echarts";
import dynamic from "next/dynamic";
import type { ChartSpec } from "@/types/analysis";

// 三维图表依赖 WebGL，仅在客户端渲染
const Chart3D = dynamic(() => import("./three/Chart3D"), { ssr: false });

function Echarts2D({ spec }: { spec: ChartSpec }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current) return;
    const chart = echarts.init(ref.current);
    const option = toEchartsOption(spec);
    chart.setOption(option);
    const onResize = () => chart.resize();
    window.addEventListener("resize", onResize);
    return () => {
      window.removeEventListener("resize", onResize);
      chart.dispose();
    };
  }, [spec]);

  return <div ref={ref} className="h-[320px] w-full" />;
}

function toEchartsOption(spec: ChartSpec): echarts.EChartsOption {
  const { type, title, xField, yField, data } = spec;
  const xf = Array.isArray(xField) ? xField[0] : xField;
  const yf = Array.isArray(yField) ? yField[0] : yField;
  const categories = data.map((d) => String(d[xf!] ?? ""));
  const values = data.map((d) => Number(d[yf!] ?? 0));

  if (type === "pie") {
    return {
      title: { text: title, left: "center" },
      tooltip: { trigger: "item" },
      series: [
        {
          type: "pie",
          radius: "60%",
          data: categories.map((c, i) => ({ name: c, value: values[i] })),
        },
      ],
    };
  }

  const seriesType =
    type === "line" || type === "area" ? "line" : type === "scatter" ? "scatter" : "bar";
  const areaStyle = type === "area" ? {} : undefined;

  return {
    title: { text: title, left: "center" },
    tooltip: { trigger: "axis" },
    xAxis: { type: "category", data: categories, axisLabel: { rotate: 30 } },
    yAxis: { type: "value" },
    series: [{ type: seriesType, data: values, areaStyle }],
  };
}

export default function ChartRenderer({ spec }: { spec: ChartSpec }) {
  if (spec.renderer === "r3f") {
    return <Chart3D spec={spec} />;
  }
  return <Echarts2D spec={spec} />;
}
