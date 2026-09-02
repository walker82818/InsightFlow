"""P2：Artifact 无头截图服务（Playwright）。

加载主应用的 ``runtime.html``，以 standalone 模式（URL 查询参数 ``?spec=<base64url>``
注入 ArtifactSpec）渲染，等待 ``window.__ARTIFACT_DONE`` 后截取 PNG。
供报告导出（快照嵌入）与前端「保存为图片」复用。

浏览器策略：优先复用本机系统 Edge（``channel="msedge"``，Windows/macOS 通常
免安装），失败则回退到 Playwright 自带 Chromium（需 ``playwright install chromium``）。
"""
from __future__ import annotations

import asyncio
import base64
import json
import logging
import threading
from typing import Any

from app.core.config import settings

logger = logging.getLogger("insightflow")

_browser: Any = None
_pw: Any = None
_start_lock = asyncio.Lock()

# Windows 下 uvicorn（尤其 --reload / --workers）会选用 SelectorEventLoop，
# 而该 loop 不支持起子进程（Playwright 浏览器），抛 NotImplementedError。
# 因此截图统一在专用线程的常驻事件循环里执行：`asyncio.new_event_loop()`
# 在 Windows 默认即 ProactorEventLoop，Linux 上同为普通 asyncio loop，无副作用。
_shooter_loop: asyncio.AbstractEventLoop | None = None
_shooter_loop_lock = threading.Lock()


def _get_shooter_loop() -> asyncio.AbstractEventLoop:
    """获取常驻截图事件循环（首次启动守护线程）。"""
    global _shooter_loop
    with _shooter_loop_lock:
        if _shooter_loop is None or _shooter_loop.is_closed():
            loop = asyncio.new_event_loop()
            threading.Thread(
                target=loop.run_forever,
                name="artifact-shooter",
                daemon=True,
            ).start()
            _shooter_loop = loop
        return _shooter_loop


def shoot_sync(
    spec: dict[str, Any],
    *,
    width: int = 960,
    timeout_s: float = 45.0,
) -> bytes:
    """同步入口：在专用事件循环线程中执行截图。

    供 API worker 的任意事件循环（即使 SelectorEventLoop）通过线程调用，
    规避 uvicorn 在 Windows 上选错 loop 的问题。
    """
    loop = _get_shooter_loop()
    future = asyncio.run_coroutine_threadsafe(
        _shot_artifact(spec, width=width, timeout_s=timeout_s), loop
    )
    return future.result()


async def _get_browser() -> Any:
    """Lazy 单例浏览器（进程内复用，避免每次截图都启动 chromium）。"""
    global _browser, _pw
    if _browser is not None:
        return _browser
    async with _start_lock:
        if _browser is not None:
            return _browser
        from playwright.async_api import async_playwright

        _pw = await async_playwright().start()
        try:
            _browser = await _pw.chromium.launch(channel="msedge")
        except Exception:
            # 无系统 Edge 时回退到内置 Chromium
            _browser = await _pw.chromium.launch()
        logger.info("artifact shooter: playwright browser ready")
    return _browser


def _runtime_url(spec: dict[str, Any]) -> str:
    # spec 走 URL **fragment**（#spec=）而不是查询串（?spec=）：
    # fragment 不会随 HTTP 请求发送到服务端，因此不受 Next dev server
    # （Node 默认 maxHeaderSize=16KB）等中间件的请求行长度限制——
    # 用 ?spec= 时，稍长的图表代码就会触发 431 Request Header Fields Too Large，
    # Playwright 侧表现为 net::ERR_HTTP_RESPONSE_CODE_FAILURE，截图 503。
    # ensure_ascii=False：中文按 UTF-8 原样编码，比 \uXXXX 转义节省一半以上体积。
    payload = base64.urlsafe_b64encode(
        json.dumps(spec, ensure_ascii=False).encode("utf-8")
    ).decode("ascii")
    base = settings.artifact_runtime_url.rstrip("/")
    sep = "&" if "#" in base else "#"
    return f"{base}{sep}spec={payload}"


async def shot_artifact(
    spec: dict[str, Any],
    *,
    width: int = 960,
    timeout_s: float = 45.0,
) -> bytes:
    """异步入口：渲染一个 ArtifactSpec 并返回 PNG 字节。

    内部转交专用事件循环线程执行（见 :func:`shoot_sync`），规避 uvicorn
    在 Windows 上使用 SelectorEventLoop 导致 Playwright 无法启动的问题。
    渲染失败（编译错误 / 运行时异常 / 超时）抛 ``RuntimeError``。
    """
    return await asyncio.to_thread(
        shoot_sync, spec, width=width, timeout_s=timeout_s
    )


async def _shot_artifact(
    spec: dict[str, Any],
    *,
    width: int = 960,
    timeout_s: float = 45.0,
) -> bytes:
    """在专用事件循环线程中执行的实际截图逻辑。"""
    browser = await _get_browser()
    page = await browser.new_page(
        viewport={"width": max(320, int(width)), "height": 640},
        device_scale_factor=2,
    )
    try:
        await page.goto(_runtime_url(spec), wait_until="load", timeout=30_000)
        # runtime 页有严格 CSP（无 unsafe-eval），wait_for_function 内部依赖 eval 会被拦截，
        # 因此用轮询 page.evaluate 代替。
        done = None
        deadline = asyncio.get_event_loop().time() + timeout_s
        while asyncio.get_event_loop().time() < deadline:
            done = await page.evaluate("window.__ARTIFACT_DONE")
            if done is not None:
                break
            await asyncio.sleep(0.2)
        if not done or not done.get("ok"):
            err = (done or {}).get("error") or "渲染超时"
            raise RuntimeError(f"artifact 渲染失败：{err}")
        # 等 echarts 动画 / 布局稳定后再截图
        await page.wait_for_timeout(1_200)
        # 报告为白底，覆盖 runtime 透明背景
        await page.evaluate("document.body.style.background = 'rgb(255,255,255)'")
        return await page.screenshot(type="png", full_page=True)
    finally:
        await page.close()


async def snapshot_charts(charts: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """报告导出预截图：对每个含 ``code`` 的 ArtifactSpec 生成 base64 PNG 快照。

    单个截图失败时**保留原 spec**（渲染层回退到占位），不阻塞整个导出。
    """
    out: list[dict[str, Any]] = []
    for spec in charts:
        if not spec.get("code"):
            out.append(spec)
            continue
        try:
            png = await shot_artifact(spec, width=settings.artifact_shot_width)
            snap = "data:image/png;base64," + base64.b64encode(png).decode("ascii")
            spec = {**spec, "_snapshot": snap}
        except Exception as exc:  # noqa: BLE001 - 单图失败不阻塞导出
            logger.warning("artifact snapshot failed: %s", exc)
        out.append(spec)
    return out
