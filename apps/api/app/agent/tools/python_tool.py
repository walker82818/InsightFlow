"""Python execution tool (Phase 3).

LLM-generated analysis code runs in an isolated environment. Two backends:

* **Docker** (preferred): the ``insightflow-sandbox`` image (built from
  ``/sandbox/Dockerfile``) with the dataset mounted **read-only**, network
  disabled (``--network=none``) and CPU/memory/time limits.
* **Local fallback**: when the Docker image is not present (e.g. Docker Hub is
  unreachable), code runs via a restricted local subprocess using the same
  ``runner.py``. This keeps pandas/numpy analysis working on machines without a
  pullable image; it is NOT filesystem/network isolated, so it is only a dev
  convenience — production must use the Docker backend.

The runner (``sandbox/runner.py``) exposes ``DATA_PATH``, ``pd``, ``np`` and a
``submit(obj)`` helper; the result is read back from ``result.json``.
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
import shutil
import subprocess
import sys
import tempfile
import threading
from functools import lru_cache
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

from app.core.config import settings
from app.services.duckdb import _resolve_file

RUNNER_PATH = str(Path(__file__).resolve().parents[5] / "sandbox" / "runner.py")

PYTHON_TOOL_SPEC: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "python_execute",
        "description": (
            "Execute Python (pandas/numpy) for statistics or data transforms that "
            "SQL cannot express easily — correlations, regressions, grouping beyond "
            "SQL, etc. Single dataset: read it via the injected variable `DATA_PATH` "
            "(path to the dataset file). Multiple datasets: load each via "
            "`json.loads(os.environ['DATA_TABLES'])` which maps table_name -> file path. "
            "Finish by calling `submit({...})` with a JSON-serializable result dict "
            "(e.g. {'columns': [...], 'rows': [[...]]} or {'summary': {...}})."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "code": {
                    "type": "string",
                    "description": (
                        "Python code. Example:\n"
                        "import pandas as pd\n"
                        "df = pd.read_csv(DATA_PATH)\n"
                        "submit({'columns': ['region','mean_rev'],\n"
                        "        'rows': df.groupby('region')['revenue'].mean().round(2).reset_index().values.tolist()})"
                    ),
                }
            },
            "required": ["code"],
            "additionalProperties": False,
        },
    },
}


def _win_to_docker_path(path: str) -> str:
    """Best-effort conversion of a Windows path for Docker Desktop bind mounts."""
    p = os.path.abspath(path)
    if p[1:2] == ":":  # C:\foo -> /c/foo
        return "/" + (p[0].lower() + p[2:]).replace("\\", "/")
    return p.replace("\\", "/")


@lru_cache(maxsize=1)
def _docker_image_exists() -> bool:
    try:
        r = subprocess.run(
            ["docker", "image", "inspect", settings.sandbox_docker_image],
            capture_output=True,
            timeout=10,
        )
        return r.returncode == 0
    except Exception:  # noqa: BLE001
        return False


def python_sandbox_isolated() -> bool:
    """Whether arbitrary LLM-generated code can run in an isolated sandbox.

    True only when the Docker image is present (network disabled, read-only
    mount, resource limits). When False, running code locally would execute at
    the server's privilege level — a real RCE risk — so the analysis agent must
    NOT offer the python_execute tool (see nodes.analysis_node).
    """
    return _docker_image_exists()


def _read_result(workdir: str) -> dict[str, Any]:
    result_path = os.path.join(workdir, "result.json")
    if os.path.exists(result_path):
        with open(result_path, encoding="utf-8") as f:
            out = json.load(f)
        if "error" in out:
            out["success"] = False
        return out
    return {"success": False, "error": "no result produced by submit()"}


async def _run_docker(
    data_path: str,
    code: str,
    timeout: int,
    workdir: str,
    tables: dict[str, str] | None = None,
) -> dict[str, Any]:
    data_dir = os.path.dirname(data_path)
    data_name = os.path.basename(data_path)
    with open(os.path.join(workdir, "user_code.py"), "w", encoding="utf-8") as f:
        f.write(code)

    if tables is None:
        tables = {os.path.splitext(data_name)[0]: data_path}

    cmd = [
        "docker",
        "run",
        "--rm",
        "--network=none",
        f"--memory={settings.sandbox_memory}",
        f"--cpus={settings.sandbox_cpus}",
        "-v",
        f"{_win_to_docker_path(data_dir)}:/data:ro",
        "-v",
        f"{_win_to_docker_path(workdir)}:/work",
        "-e",
        f"DATA_PATH=/data/{data_name}",
        "-e",
        f"DATA_PATHS={json.dumps([data_path])}",
        "-e",
        f"DATA_TABLES={json.dumps(tables)}",
        settings.sandbox_docker_image,
    ]
    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE
        )
    except FileNotFoundError as exc:
        return {"error": "docker not found", "detail": str(exc)}

    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout + 10)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"error": f"python execution exceeded the {timeout}s timeout"}
    if proc.returncode not in (0, 2, 3):
        return {
            "error": "sandbox exited abnormally",
            "stderr": stderr.decode(errors="replace")[:800],
        }
    return _read_result(workdir)


async def _run_local(
    data_path: str,
    code: str,
    timeout: int,
    workdir: str,
    tables: dict[str, str] | None = None,
) -> dict[str, Any]:
    user_code = os.path.join(workdir, "user_code.py")
    result_path = os.path.join(workdir, "result.json")
    with open(user_code, "w", encoding="utf-8") as f:
        f.write(code)
    if tables is None:
        tables = {os.path.splitext(os.path.basename(data_path))[0]: data_path}
    env = {
        **os.environ,
        "DATA_PATH": data_path,
        "DATA_PATHS": json.dumps([data_path]),
        "DATA_TABLES": json.dumps(tables),
        "USER_CODE_PATH": user_code,
        "RESULT_PATH": result_path,
    }
    try:
        proc = await asyncio.create_subprocess_exec(
            sys.executable,
            RUNNER_PATH,
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError as exc:
        return {"error": "python runtime not found", "detail": str(exc)}

    try:
        _, stderr = await asyncio.wait_for(proc.communicate(), timeout=timeout + 10)
    except asyncio.TimeoutError:
        proc.kill()
        await proc.wait()
        return {"error": f"python execution exceeded the {timeout}s timeout"}
    if proc.returncode not in (0, 2, 3):
        return {
            "error": "local execution failed",
            "stderr": stderr.decode(errors="replace")[:800],
        }
    return _read_result(workdir)


# Windows 下 uvicorn（尤其 --reload）使用 SelectorEventLoop，不支持
# asyncio.create_subprocess_exec → 起 docker / 本地 runner 子进程会抛空消息的
# NotImplementedError。因此 Python 工具统一在专用常驻事件循环线程中执行：
# asyncio.new_event_loop() 在 Windows 默认即 ProactorEventLoop，可正常起子进程。
_executor_loop: asyncio.AbstractEventLoop | None = None
_executor_loop_lock = threading.Lock()


def _get_executor_loop() -> asyncio.AbstractEventLoop:
    global _executor_loop
    with _executor_loop_lock:
        if _executor_loop is None or _executor_loop.is_closed():
            loop = asyncio.new_event_loop()
            threading.Thread(
                target=loop.run_forever,
                name="python-executor",
                daemon=True,
            ).start()
            _executor_loop = loop
        return _executor_loop


async def _run_tool_core(
    datasets: list[dict[str, Any]],
    code: str,
    timeout: int,
) -> dict[str, Any]:
    data_paths = [_resolve_file(d["storage_path"]) for d in datasets]
    data_path = data_paths[0]
    tables = {d["table_name"]: p for d, p in zip(datasets, data_paths)}
    workdir = tempfile.mkdtemp(prefix="insightflow_sbx_")
    try:
        if python_sandbox_isolated():
            return await _run_docker(data_path, code, timeout, workdir, tables)
        return await _run_local(data_path, code, timeout, workdir, tables)
    finally:
        shutil.rmtree(workdir, ignore_errors=True)


async def run_python_tool(
    datasets: list[dict[str, Any]],
    code: str,
    timeout: int | None = None,
) -> dict[str, Any]:
    """Run user code in the sandbox over one or more datasets.

    ``datasets`` is a list of DatasetRef-style dicts. ``DATA_PATH`` points at the
    first file; ``DATA_PATHS`` (JSON list) and ``DATA_TABLES`` (JSON dict mapping
    table_name -> file path) let the code load every dataset for multi-document
    analysis.
    """
    timeout = timeout or settings.sandbox_timeout
    if not datasets:
        return {"error": "no dataset provided"}
    # 安全闸门：无隔离沙箱时，默认拒绝执行 LLM 生成的任意代码（避免服务器级 RCE）。
    # 仅当显式开启 sandbox_allow_local_fallback 时才退化为本地进程（开发便利，非生产）。
    if not python_sandbox_isolated():
        if not settings.sandbox_allow_local_fallback:
            return {
                "error": (
                    "Python 沙箱不可用：未找到 Docker 镜像 "
                    f"{settings.sandbox_docker_image}，且未启用本地降级（安全策略）。"
                    "请用 SQL 完成分析，或由运维构建沙箱镜像后重试。"
                )
            }
        logger.warning(
            "python sandbox image missing; running LLM-generated code as a local "
            "subprocess at server privilege (sandbox_allow_local_fallback=True) — RCE risk"
        )
    # 子进程（docker / 本地 runner）统一转交专用事件循环线程执行，规避 uvicorn
    # 在 Windows 上使用 SelectorEventLoop 导致 NotImplementedError 的问题。
    return await asyncio.to_thread(
        _submit_to_executor, datasets, code, timeout
    )


def _submit_to_executor(
    datasets: list[dict[str, Any]], code: str, timeout: int
) -> dict[str, Any]:
    """把工具执行提交到专用事件循环线程并等待结果（供 asyncio.to_thread 调用）。"""
    loop = _get_executor_loop()
    return asyncio.run_coroutine_threadsafe(
        _run_tool_core(datasets, code, timeout), loop
    ).result()
