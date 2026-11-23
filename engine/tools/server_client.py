# -*- coding: utf-8 -*-
from __future__ import annotations
import json, socket
from typing import Any

HOST = "127.0.0.1"
PORT = 8371

def task_send(cmd: str, *, workspace: str | None = None, **kwargs) -> dict:
    payload = {"task": cmd, **kwargs}
    if workspace:
        payload["workspace"] = workspace   # F3=C
    return _sandbox_call(payload, wait=kwargs.pop("wait", 600.0))

def is_server_online() -> bool:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(1.0)
            s.connect((HOST, PORT))
        return True
    except (ConnectionRefusedError, OSError):
        return False

def status() -> dict[str, Any] | None:
    return _raw_query(b"STATUS\n")

def query(prompt: str, max_tokens: int = 4096) -> dict[str, Any] | None:
    payload = (json.dumps({"prompt": prompt, "max_tokens": max_tokens}) + "\n").encode("utf-8")
    return _raw_query(payload)

def ask(prompt: str, max_tokens: int = 4096) -> str | None:
    resp = query(prompt, max_tokens=max_tokens)
    if resp is None or resp.get("error"):
        return None
    output = str(resp.get("output", ""))
    try:
        from engine.thinking.code_hook import apply_code_hook
        class ServerBridge:
            def ask(self, p: str, max_tokens: int = 4096, **kwargs) -> str:
                r = query(p, max_tokens=max_tokens)
                return r.get("output", "") if r else ""
        class DummyValidator:
            def validar_output(self, text: str, lang: str | None = None):
                return True, ""
        output = apply_code_hook(
            output=output,
            task=prompt,
            bridge=ServerBridge(),
            validator=DummyValidator(),
            max_retries=1,
            run_isolated=True,
        )
    except Exception as e:
        output += f"\n\n[AVISO] Falha ao acionar CodeHook local: {e}"
    return output

def decide(question: str, server_ask_fn) -> str | None:
    response = server_ask_fn(question)
    if response is None:
        return None
    if isinstance(response, str):
        response = {"output": response, "elapsed_s": 0, "error": None}
    if not isinstance(response, dict):
        response = {"output": str(response), "elapsed_s": 0, "error": None}
    if response.get("error"):
        return None
    return response.get("output", "").strip() or None

def _raw_query(payload: bytes) -> dict[str, Any] | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            s.settimeout(60.0)
            s.connect((HOST, PORT))
            s.settimeout(None)
            s.sendall(payload)
            data = bytearray()
            while True:
                chunk = s.recv(65536)
                if not chunk:
                    break
                data.extend(chunk)
                if data.endswith(b"\n"):
                    break
        resp = json.loads(data.decode("utf-8").strip())
        return resp if isinstance(resp, dict) else None
    except Exception:
        return None

def _sandbox_call(payload: dict, wait: float = 600.0) -> dict:
    try:
        with socket.create_connection((HOST, PORT), timeout=5) as s:
            s.settimeout(wait)
            s.sendall((json.dumps(payload) + "\n").encode("utf-8"))
            buf = bytearray()
            while not buf.endswith(b"\n"):
                chunk = s.recv(65536)
                if not chunk:
                    break
                buf.extend(chunk)
        return json.loads(buf.decode("utf-8"))
    except Exception as exc:
        return {"error": str(exc)}


def sandbox_run(code, lang="python", args=None, timeout=30, wait=600.0):
    return _sandbox_call({"sandbox": "run", "code": code, "lang": lang,
                          "args": args or [], "timeout": timeout}, wait)


def sandbox_shell(cmd, timeout=30):
    return _sandbox_call({"sandbox": "shell", "cmd": cmd, "timeout": timeout},
                         wait=timeout + 600)


def sandbox_status() -> dict:
    return _sandbox_call({"sandbox": "status"}, wait=30)
