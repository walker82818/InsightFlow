// Structured chart specification shared between backend (generator) and
// frontend (renderer: echarts-for-react for 2D, react-three-fiber for 3D).

export type Renderer = "echarts" | "r3f";

export type Chart2DType =
  | "line"
  | "bar"
  | "scatter"
  | "pie"
  | "heatmap"
  | "area"
  | "histogram"
  | "boxplot"
  | "radar"
  | "funnel"
  | "gauge";

export type Chart3DType = "3d_scatter" | "3d_bar" | "3d_surface" | "3d_map";

export type ChartType = Chart2DType | Chart3DType;

export interface ChartSpec {
  /** 区分 2D (echarts) 与 3D (react-three-fiber) 渲染器 */
  renderer: Renderer;
  type: ChartType;
  title: string;
  xField: string;
  yField: string;
  /** 3D 图表专用 */
  zField?: string;
  data: Array<Record<string, unknown>>;
}
