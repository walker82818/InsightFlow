// Agent2UI 共享契约：ArtifactSpec 与 iframe 沙箱 postMessage 协议。
// 后端（P1）用 pydantic 对齐此契约；本文件为 TS/zod 侧权威定义。
import { z } from "zod";

/** 生成代码允许 import 的模块白名单（iframe 内由 importmap 解析） */
export const ARTIFACT_IMPORT_WHITELIST = [
  "react",
  "react-dom/client",
  "echarts",
  "three",
  "react/jsx-runtime",
  "/_artifacts/insight-ui.js",
] as const;

/** 生成代码体积上限（防 token 炸弹 / 超长编译） */
export const ARTIFACT_MAX_CODE_BYTES = 32 * 1024;

/** Agent 输出的可执行 UI 规格 */
export const ArtifactSpecSchema = z.object({
  title: z.string().default(""),
  /** 单文件 React TSX 源码，默认导出 `App({ data, theme })` */
  code: z
    .string()
    .max(ARTIFACT_MAX_CODE_BYTES, "artifact code exceeds 32KB limit"),
  /** 显式声明的 import，用于快速白名单校验（也可靠运行时 importmap 天然拦截） */
  imports: z.array(z.string()).optional(),
  /** 注入给组件的查询结果数据 */
  data: z.unknown().optional(),
  /** 主题名，缺省跟随应用 */
  theme: z.enum(["light", "dark"]).optional(),
});

export type ArtifactSpec = z.infer<typeof ArtifactSpecSchema>;

/** 主页面 → iframe 消息 */
export const ParentToFrameSchema = z.discriminatedUnion("type", [
  z.object({
    type: z.literal("mount"),
    code: z.string().max(ARTIFACT_MAX_CODE_BYTES),
    data: z.unknown().optional(),
    theme: z.enum(["light", "dark"]).optional(),
  }),
  z.object({ type: z.literal("unmount") }),
]);

export type ParentToFrameMessage = z.infer<typeof ParentToFrameSchema>;

/** iframe → 主页面消息 */
export const FrameToParentSchema = z.discriminatedUnion("type", [
  z.object({ type: z.literal("ready"), height: z.number().finite() }),
  z.object({ type: z.literal("resize"), height: z.number().finite() }),
  z.object({
    type: z.literal("error"),
    error: z.object({
      message: z.string(),
      line: z.number().optional(),
      column: z.number().optional(),
    }),
  }),
  z.object({
    type: z.literal("event"),
    name: z.string(),
    payload: z.unknown().optional(),
  }),
]);

export type FrameToParentMessage = z.infer<typeof FrameToParentSchema>;

/** 校验生成代码里的 import 是否全部在白名单内；返回不合规的 import 列表（空 = 通过） */
export function assertImportsWhitelisted(
  imports: string[] | undefined,
): string[] {
  if (!imports?.length) return [];
  return imports.filter(
    (m) => !(ARTIFACT_IMPORT_WHITELIST as readonly string[]).includes(m),
  );
}
