"""Sandbox runner for LLM-generated Python analysis code.

Runs inside the isolated Docker container. The user's code is written to
``/work/user_code.py`` by the host; this runner executes it with a small set
of injected helpers:

    DATA_PATH  - absolute path to the (read-only) dataset file
    pd, np     - pandas / numpy
    submit(obj)- hand a JSON-serializable result back to the host (preferred)

The result is written to ``/work/result.json`` which the host reads back.
A SIGTERM (sent by the host on timeout) aborts execution cleanly.
"""
from __future__ import annotations

import json
import os
import signal
import sys
import traceback

RESULT_PATH = os.environ.get("RESULT_PATH", "/work/result.json")
USER_CODE_PATH = os.environ.get("USER_CODE_PATH", "/work/user_code.py")


def _submit(obj):
    try:
        with open(RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump(obj, f, ensure_ascii=False, default=str)
    except Exception as exc:  # noqa: BLE001
        with open(RESULT_PATH, "w", encoding="utf-8") as f:
            json.dump({"error": f"submit failed: {exc}"}, f, ensure_ascii=False)


def _timeout(signum, frame):
    raise TimeoutError("execution exceeded the time limit")


def main() -> int:
    signal.signal(signal.SIGTERM, _timeout)

    data_path = os.environ.get("DATA_PATH", "")
    code_path = USER_CODE_PATH
    if not os.path.exists(code_path):
        _submit({"error": "user_code.py not found in sandbox"})
        return 1

    ns: dict = {
        "__name__": "__main__",
        "DATA_PATH": data_path,
        "submit": _submit,
    }
    try:
        import numpy as np  # noqa: F401
        import pandas as pd  # noqa: F401

        ns["pd"] = pd
        ns["np"] = np
    except Exception:  # noqa: BLE001
        pass

    try:
        with open(code_path, "r", encoding="utf-8") as f:
            user_code = f.read()
        exec(compile(user_code, code_path, "exec"), ns)  # noqa: S102
    except TimeoutError:
        _submit({"error": "execution exceeded the time limit"})
        return 2
    except Exception:  # noqa: BLE001
        _submit({"error": traceback.format_exc(limit=5)})
        return 3

    # If the user never called submit(), try to recover stdout JSON.
    if not os.path.exists(RESULT_PATH):
        raw = "".join(sys.stdout.getvalue() if hasattr(sys.stdout, "getvalue") else [])
        _submit({"raw_stdout": raw})
    return 0


if __name__ == "__main__":
    sys.exit(main())
