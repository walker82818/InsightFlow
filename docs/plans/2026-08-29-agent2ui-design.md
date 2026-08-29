# InsightFlow Agent2UI 设计（2026-08-29）

> 背景：现有可视化链路是「LLM 生成 `ChartSpec` 枚举 → 前端按类型硬映射 `toEchartsOption` /
> `Chart3D`」，加一种图 = 加枚举 + 加转换函数 + 加组件，数据格式一多样就表达不了。
> 本设计改为 **Agent 直接生成 React TSX，前端在严格隔离 iframe 内编译渲染（Artifacts 模式）**，
> 全量替换 ChartSpec，表达力不再受固定封装限制。

---

## 0. 决策汇总（已与用户确认）

| # | 决策点 | 结论 |
|---|--------|------|
| 1 | 形态 | **代码生成 + 沙箱**：Agent 输出 React TSX |
| 2 | 执行运行时 | **浏览器内编译 React**：iframe 内 esbuild-wasm 编译 TSX，挂载 React 根节点 |
| 3 | 沙箱隔离 | **严格隔离**：`allow-scripts` 不带 `allow-same-origin`；React/echarts 走 CDN；数据/消息全走 postMessage |
| 4 | 与 ChartSpec 关系 | **全量替换**：ChartSpec 废弃，所有图表/结果展示走 TSX 生成 |
| 5 | 报告快照 | **后端 Playwright 截图服务**：导出 PDF 时渲染 artifact 截图嵌入 |

---

## 1. 核心链路

```
后端 LangGraph Agent（保留上下文，负责生成）
  └─ ArtifactSpec { title, code: string(TSX), imports: string[], data?: unknown }
       ↓ 作为新消息内容类型存入会话（新增 message.kind = "artifact"）
前端 ArtifactViewer
  ├─ <iframe sandbox="allow-scripts" src="/_artifacts/runtime.html">
  │    runtime 内：esbuild-wasm 编译 TSX → import 白名单库 → ReactDOM.createRoot 挂载
  ├─ postMessage 下发 { type:"mount", code, data, theme }
  └─ 接收 iframe 回传 { type:"ready"|"error"|"resize"|"event", ... }
```

```
postMessage 协议（主页面 → iframe）
  { type:"mount", code:string, data:unknown, theme:string }
  { type:"unmount" }

postMessage 协议（iframe → 主页面）
  { type:"ready", height:number }
  { type:"error", error:{ message, line, column } }
  { type:"resize", height:number }
  { type:"event", name:string, payload?:unknown }   // 可选：artifact 交互事件上报（埋点/评估用）
```

---

## 2. Agent 输出契约（ArtifactSpec）

- TSX 必须**单文件**、默认导出组件：`export default function App({ data, theme })`。
- `import` 受**白名单**约束：
  - 允许：`react`、`echarts`、`three`、`/@artifacts/insight-ui.js`（项目内置组件库，含现有 3D 封装）。
  - 禁止：`node:` 系列、`fs`、`http(s)`、`localStorage`、`fetch`（跨域本地访问）、任意未知包。
- 代码体积上限 **32KB**（防 token 炸弹 / 超长编译）。
- 契约校验：后端 pydantic + 前端 zod 双重校验；非法 import 直接拒收并触发自愈重试。

### 内置组件库 `/_artifacts/insight-ui.js`
- 把项目已写好的封装（如 `Chart3D` r3f 散点/柱体/地图、主题样式）编译成**独立 ESM bundle**，
  挂在主应用静态目录，iframe 内可 `import { Chart3D } from "/@artifacts/insight-ui.js"`。
- 保留已有 3D 封装价值，同时渲染仍由 TSX 生成驱动（全量替换语义不变）。

---

## 3. 运行时与沙箱（严格隔离落地）

- `<iframe sandbox="allow-scripts">`，**不带** `allow-same-origin` → iframe origin 变 opaque，
  运行时代码物理上拿不到主页面 Cookie / Storage / 父级 DOM。
- runtime.html 由主应用静态服务提供，CSP 只放行白名单 CDN 域名（unpkg/jsdelivr 等）。
- **esbuild-wasm（约 4MB）放 runtime 内按需加载**，不撑大主 bundle。
- 所有进出数据走 `postMessage`，主页面侧校验 `event.origin`。
- 编译 / 渲染 **10s 超时 kill**。

---

## 4. 错误自愈（Artifacts 标配）

1. iframe 内编译失败或运行时异常 → 回传 `{ type:"error", error:{ message, line, column } }`。
2. 主页面把报错文本**追加进 Agent 会话** → Agent **自动修复重试，最多 3 轮**（改完重新下发编译）。
3. 修不动时展示错误卡片 + 「重新生成」按钮。
4. 超时 / 非法 import 同样进入自愈通道。

---

## 5. 报告快照（Playwright 截图服务）

- 新增独立截图服务（Docker 容器，复用 Python 沙箱基建）：`POST /shot { code, data, width, height }`
  → Playwright 加载 runtime 页 → 注入 → 等 `ready` → 截图 PNG 返回。
- 导出 PDF 时逐 artifact 调用，PNG 嵌入报告。
- 本地开发同时提供「保存为图片」按钮复用该服务。

---

## 6. 测试策略

- **契约测试**：ArtifactSpec schema 校验（体积上限、import 白名单、默认导出）。
- **fixture 冒烟**：样例 TSX 集（echarts 图、3D 散点、表格、含错误场景）在 CI 验证
  编译 + 渲染 + 自愈重试链路。
- **Playwright E2E**：真实 iframe 沙箱、postMessage 协议、超时与 origin 校验。

---

## 7. 安全清单（固化到 runtime）

- `import` 白名单（拒绝 `node:` / `fs` / `http(s)` / `localStorage` / `fetch` 本地访问）。
- iframe 不带 `allow-same-origin`；主页面校验 `event.origin`。
- runtime.html CSP 只放行白名单 CDN 域名。
- 代码体积上限 + 编译/渲染超时。

---

## 8. 迁移影响（全量替换）

| 位置 | 现状 | 改动 |
|------|------|------|
| `packages/chart-schema` | ChartSpec 枚举 | **废弃**，新建 `packages/artifact-schema`（ArtifactSpec） |
| 后端 Agent | 生成 ChartSpec | 可视化节点改为生成 ArtifactSpec（TSX）；数据由上下文注入 |
| 前端 `ChartRenderer.tsx` | echarts/r3f 分发 | 移除，新增 `ArtifactViewer.tsx`（iframe + postMessage bridge） |
| 前端 `components/three/*` | Chart3D 等封装 | 编译进 `/_artifacts/insight-ui.js` 内置组件库 |
| 报告导出 | 用 spec 渲染 | 接 Playwright 截图服务 |
| 共享类型 `shared-types` | `AnalysisReport` 含 evidence | 新增 `ArtifactSpec` 消息类型；`AnalysisEvent` 兼容 |

---

## 9. 实施阶段建议

1. **P0 骨架**：`packages/artifact-schema` + runtime.html + esbuild-wasm 编译管线 + ArtifactViewer
   + postMessage 协议 + fixture 冒烟（先跑通「手写 TSX → iframe 渲染」）。
2. **P1 后端生成**：Agent 可视化节点输出 ArtifactSpec，接入错误自愈重试循环（3 轮）。
3. **P2 报告快照**：Playwright 截图服务 + 导出集成。
4. **P3 清理**：移除 ChartSpec 相关代码与 `toEchartsOption` 硬映射，内置组件库打包上线。
