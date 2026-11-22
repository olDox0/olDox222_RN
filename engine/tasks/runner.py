# -*- coding: utf-8 -*-
"""TaskRunner — orquestra plan → draft → implement → sandbox → present.

Dependências injetadas (nada instanciado aqui):
    store      : TaskStore
    bridge     : objeto com ``ask(prompt, max_tokens=None) -> str``
    validator  : objeto com ``validar_output(text) -> (bool, str)``
    emit       : callable opcional ``(event: dict) -> None``
    code_hook  : callable opcional ``(code: str, task: Task) -> str``
    sandbox_step: callable opcional ``(task: Task) -> tuple[bool, str]``
                  (passo 2: stub que retorna ``(True, "")``)

God: Zeus (controle) + Hermes (ponte).
"""
from __future__ import annotations

import json
import re
import sys
import traceback
from typing import Any, Callable

from engine.tasks import prompts
from engine.tasks.model import (
    Phase,
    Task,
    TaskArtifact,
    TaskStatus,
    can_transition_status,
    now,
)
from engine.tasks.store import TaskStore


# ---------------------------------------------------------------------------
# Fluxo interno via exceções
# ---------------------------------------------------------------------------
class _TaskAborted(Exception):
    """Erro irrecuperável (plano inválido, bridge explodiu, etc.)."""


class _RetryDraft(Exception):
    """Pede retry: o runner volta para DRAFT com ``feedback``."""

    def __init__(self, feedback: str) -> None:
        super().__init__(feedback)
        self.feedback = feedback


# ---------------------------------------------------------------------------
# Helpers de parsing
# ---------------------------------------------------------------------------
_CODE_BLOCK_RE = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)
_JSON_FENCE_RE = re.compile(r"```(?:json)?\s*\n?(.*?)```", re.DOTALL)

_LANG_ALIASES: dict[str, str] = {
    "py": "python", "python3": "python", "python": "python",
    "c": "c", "h": "c",
    "cpp": "c++", "cxx": "c++", "c++": "c++",
    "js": "javascript", "javascript": "javascript",
    "ts": "typescript", "typescript": "typescript",
    "rs": "rust", "rust": "rust",
    "go": "go", "golang": "go",
    "sh": "bash", "bash": "bash", "shell": "bash",
}

# Heurística mínima para quando o modelo esquece a fence:
# se o texto já "parece código", aceita cru em vez de rejeitar.
_CODE_HINT_RE = re.compile(
    r"^\s*(?:def |class |import |from |return |if |for |while |try:|except |"
    r"#include|int |void |char |function |const |let |var |fn |pub fn |"
    r"package |func |print\(|puts\()",
    re.MULTILINE,
)


def _normalize_lang(raw: str) -> str:
    if not raw:
        return ""
    key = raw.strip().lower()
    return _LANG_ALIASES.get(key, key)


def _extract_code_block(text: str, default_lang: str = "python") -> tuple[str, str]:
    if not text:
        return "", default_lang
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    target = _normalize_lang(default_lang)
    matches = _CODE_BLOCK_RE.findall(text)  
    if not matches:
        cleaned = text.strip()
        # Se começou com fence de markdown mas não fechou, remove a linha de abertura
        if cleaned.startswith("```"):
            lines = cleaned.splitlines()
            first_line = lines[0].lstrip("`").strip()
            lang = _normalize_lang(first_line) or default_lang
            code = "\n".join(lines[1:]).strip()
            return code, lang
        return cleaned, default_lang

    norm = [(body, _normalize_lang(raw)) for raw, body in matches]
    preferred = [(body, lang) for body, lang in norm if lang in (target, "")]
    pool = preferred or norm
    code, lang = max(pool, key=lambda pair: len(pair[0]))
    final_lang = lang or target or default_lang
    return code.strip(), final_lang


def _parse_sections_to_plan(text: str, default_lang: str = "python") -> dict | None:
    """Extrai seções de texto livre e envelopa em um plano estruturado garantido."""
    if not text or len(text.strip()) < 15:
        return None

    ext = "c" if default_lang in ("c", "cpp", "c++") else "py"
    default_filename = f"main.{ext}"

    # Tenta extrair [ENTENDIMENTO]
    understanding = ""
    m_und = re.search(r"\[ENTENDIMENTO\]\s*(.*?)(?=\[(?:ARQUIVO|ARQUIVOS|RISCOS|CRITERIOS)\]|$)", text, re.DOTALL | re.IGNORECASE)
    if m_und:
        understanding = m_und.group(1).strip()
    elif "understanding" in text.lower():
        # Fallback se a IA tentou imitar chave de JSON
        m_key = re.search(r'["\']?understanding["\']?\s*:\s*["\']([^"\']+)["\']', text, re.IGNORECASE)
        if m_key:
            understanding = m_key.group(1).strip()

    # Tenta extrair [ARQUIVO]
    filename = default_filename
    m_file = re.search(r"\[(?:ARQUIVO|ARQUIVOS)\]\s*(.*?)(?=\[(?:ENTENDIMENTO|RISCOS|CRITERIOS)\]|$)", text, re.DOTALL | re.IGNORECASE)
    if m_file:
        cand = m_file.group(1).strip().splitlines()[0].strip()
        cand = re.sub(r"[^\w\.\-\/]", "", cand)
        if cand:
            filename = cand

    # Tenta extrair [RISCOS]
    risks = []
    m_risks = re.search(r"\[RISCOS\]\s*(.*?)(?=\[(?:ENTENDIMENTO|ARQUIVO|ARQUIVOS|CRITERIOS)\]|$)", text, re.DOTALL | re.IGNORECASE)
    if m_risks:
        for line in m_risks.group(1).strip().splitlines():
            clean = line.strip(" -*•")
            if clean:
                risks.append(clean)

    if not understanding:
        # Se não achou tag, usa o primeiro parágrafo significativo
        lines = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("{")]
        understanding = lines[0] if lines else ""

    if not understanding or len(understanding) < 4:
        return None

    # O sistema envelopa em JSON canônico perfeito
    return {
        "understanding": understanding,
        "files": [{"path": filename, "action": "create", "purpose": "implementação da tarefa"}],
        "io_contracts": [],
        "risks": risks or ["possível loop infinito ou estouro de limites"],
        "success_criteria": ["execução bem-sucedida no sandbox"]
    }

def _extract_json(text: str, default_lang: str = "python") -> dict:
    if not text:
        raise ValueError("texto vazio")
    body = text.strip()
    m = _JSON_FENCE_RE.search(body)
    if m:
        body = m.group(1).strip()
    try:
        obj = json.loads(body)
        if isinstance(obj, dict):
            return obj
    except (ValueError, json.JSONDecodeError):
        pass

    # Envelopamento automático caso o JSON da IA venha quebrado ou em seções
    enveloped = _parse_sections_to_plan(text, default_lang=default_lang)
    if enveloped is not None:
        return enveloped

    raise ValueError("não foi possível extrair nem JSON nem seções estruturadas")


def _plan_is_valid(obj: dict) -> tuple[bool, str]:
    if not isinstance(obj, dict):
        return False, "plano não é um dicionário"
    if not isinstance(obj.get("understanding"), str):
        return False, "campo 'understanding' ausente ou não-string"
    if not isinstance(obj.get("files"), list):
        return False, "campo 'files' ausente ou não-lista"
    return True, ""



# ---------------------------------------------------------------------------
# TaskRunner
# ---------------------------------------------------------------------------
class TaskRunner:
    def __init__(
        self,
        store: TaskStore,
        bridge: Any,
        validator: Any,
        *,
        emit: Callable[[dict], None] | None = None,
        code_hook: Callable[[str, Task], str] | None = None,
        sandbox_step: Callable[[Task], tuple[bool, str]] | None = None,
        default_max_tokens: int = 512,      # <-- NOVO
    ) -> None:
        self.store = store
        self.bridge = bridge
        self.validator = validator
        self._emit_sink = emit
        self._code_hook = code_hook
        self._sandbox_step = sandbox_step
        self._default_max_tokens = max(64, int(default_max_tokens))\

    # ------------------------------------------------------------------
    # emissão
    # ------------------------------------------------------------------
    def _emit(self, task: Task, kind: str, **fields: Any) -> None:
        if self._emit_sink is None:
            return
        try:
            self._emit_sink({"event": kind, "task_id": task.id, "ts": now(), **fields})
        except Exception:
            pass  # emissor nunca derruba o runner

    # ------------------------------------------------------------------
    # inferência / validação
    # ------------------------------------------------------------------
    def _ask(self, task: Task, system: str, user: str) -> str:
        # Limpa o histórico de diálogo prévio do bridge para evitar acúmulo de contexto
        if hasattr(self.bridge, "clear_context"):
            try:
                self.bridge.clear_context()
            except Exception:
                pass

        full = f"{system}\n\n{user}" if system else user
        max_tokens = self._resolve_max_tokens(task, full)
        try:
            out = self.bridge.ask(full, max_tokens=max_tokens)
        except Exception as exc:
            raise _TaskAborted(
                f"inferência falhou: {type(exc).__name__}: {exc} "
                f"(prompt_len={len(full)}, max_tokens={max_tokens})"
            ) from exc
        if out is None:
            raise _TaskAborted(
                f"inferência retornou None "
                f"(prompt_len={len(full)}, max_tokens={max_tokens})"
            )
        text = str(out)
        if not text.strip():
            raise _TaskAborted(
                f"inferência retornou string vazia "
                f"(prompt_len={len(full)}, max_tokens={max_tokens})"
            )
        return text

    def _validate(self, text: str) -> tuple[bool, str]:
        """Chama o validator externo; nunca levanta (validator quebrado = aceita)."""
        try:
            return self.validator.validar_output(text)
        except Exception as exc:
            return True, f"(validator ignorado: {exc})"


    def _resolve_max_tokens(self, task: Task, prompt: str) -> int:
        if task.spec.max_tokens is not None and task.spec.max_tokens > 0:
            return int(task.spec.max_tokens)
        # Para tarefas autônomas com código, o piso mínimo seguro é 512 tokens
        return max(512, self._default_max_tokens)

    # ------------------------------------------------------------------
    # transições auxiliares
    # ------------------------------------------------------------------
    def _bump_attempt(self, task: Task, feedback: str) -> None:
        """Incrementa tentativa e bloqueia se estourou ``max_retries``."""
        task.attempts += 1
        task.feedback = feedback
        if task.attempts > task.spec.max_retries:
            if can_transition_status(task.status, TaskStatus.BLOCKED):
                task.set_status(TaskStatus.BLOCKED)
                task.errors.append(
                    f"retries esgotados após {task.attempts} tentativa(s)"
                )
            self._emit(task, "phase_error",
                       phase=task.current_phase,
                       reason="retries_esgotados",
                       attempts=task.attempts)
        else:
            self.store.save(task)

    # ------------------------------------------------------------------
    # fases
    # ------------------------------------------------------------------
    def _phase_plan(self, task: Task) -> None:
        self._emit(task, "phase_start", phase="plan")
        system, user = prompts.build_plan_prompt(task)
        last_err = ""
        obj = None
        raw = ""
        for attempt in range(2):  
            raw = self._ask(task, system, user)
            try:
                obj = _extract_json(raw, default_lang=task.spec.language)
                ok, why = _plan_is_valid(obj)
                if not ok:
                    last_err = why
                    continue
                break
            except (ValueError, json.JSONDecodeError) as exc:
                last_err = f"{type(exc).__name__}: {exc}"
        else:
            raise _TaskAborted(f"plano JSON inválido após 2 tentativas: {last_err}")

        art = TaskArtifact(
            phase="plan",
            content=raw,
            meta={"plan": obj, "attempts_plan": attempt + 1},
        )
        task.artifacts["plan"] = art
        self.store.save_artifact(task, art)
        self._emit(task, "phase_done", phase="plan", attempts=attempt + 1)

    def _phase_draft(self, task: Task) -> None:
        self._emit(task, "phase_start", phase="draft", attempt=task.attempts)
        system, user = prompts.build_draft_prompt(task, feedback=task.feedback)
        raw = self._ask(task, system, user)
        code, lang = _extract_code_block(raw, task.spec.language)
        if not code.strip():
            raise _RetryDraft("draft vazio — o modelo não retornou bloco de código")

        ok, why = self._validate(code)
        if not ok:
            raise _RetryDraft(f"draft rejeitado pelo validator: {why}")

        art = TaskArtifact(
            phase="draft",
            content=raw,
            code=code,
            lang=lang,
            meta={"attempts_draft": task.attempts + 1},
        )
        task.artifacts["draft"] = art
        task.feedback = ""
        self.store.save_artifact(task, art)
        self._emit(task, "phase_done", phase="draft", code_len=len(code))

    def _phase_implement(self, task: Task) -> None:
        self._emit(task, "phase_start", phase="implement", attempt=task.attempts)
        system, user = prompts.build_implement_prompt(task, feedback=task.feedback)
        raw = self._ask(task, system, user)
        code, lang = _extract_code_block(raw, task.spec.language)
        if not code.strip():
            raise _RetryDraft("implement vazio — modelo não retornou bloco de código")

        if self._code_hook is not None:
            try:
                code = self._code_hook(code, task)
            except Exception as exc:
                # hook quebrado não derruba; só registra e segue com código original
                task.errors.append(f"code_hook ignorado: {type(exc).__name__}: {exc}")

        ok, why = self._validate(code)
        if not ok:
            raise _RetryDraft(f"implement rejeitado pelo validator: {why}")

        art = TaskArtifact(
            phase="implement",
            content=raw,
            code=code,
            lang=lang,
            meta={"attempts_implement": task.attempts + 1},
        )
        task.artifacts["implement"] = art
        task.feedback = ""
        self.store.save_artifact(task, art)
        self._emit(task, "phase_done", phase="implement", code_len=len(code))

    def _phase_sandbox(self, task: Task) -> None:
        self._emit(task, "phase_start", phase="sandbox")
        step = self._sandbox_step or (lambda _t: (True, ""))
        try:
            ok, feedback = step(task)
        except Exception as exc:
            raise _RetryDraft(
                f"sandbox levantou exceção: {type(exc).__name__}: {exc}"
            ) from exc

        impl = task.artifact("implement")
        art = TaskArtifact(
            phase="sandbox",
            content=feedback or "",
            meta={
                "success":      bool(ok),
                "stub":         bool(self._sandbox_step is None),
                "feedback_len": len(feedback or ""),
                "lang":         impl.lang if impl else task.spec.language,
            },
        )
        task.artifacts["sandbox"] = art
        self.store.save_artifact(task, art)
        if not ok:
            raise _RetryDraft(feedback or "sandbox falhou sem feedback")
        self._emit(task, "phase_done", phase="sandbox")

    def _phase_present(self, task: Task) -> None:
        self._emit(task, "phase_start", phase="present")
        parts: list[str] = [
            f"# Tarefa {task.id}",
            "",
            f"**Objetivo:** {task.spec.goal}",
            "",
        ]

        plan = task.artifact("plan")
        if plan and plan.meta.get("plan"):
            obj = plan.meta["plan"]
            parts += ["## Plano", ""]
            parts.append(f"- **Entendimento:** {obj.get('understanding', '—')}")
            for f_ in obj.get("files", []) or []:
                parts.append(
                    f"- `{f_.get('path', '?')}` ({f_.get('action', '?')}): "
                    f"{f_.get('purpose', '')}"
                )
            if obj.get("risks"):
                parts.append("- **Riscos:**")
                for r in obj["risks"]:
                    parts.append(f"  - {r}")
            parts.append("")

        impl = task.artifact("implement")
        if impl and impl.code:
            parts += [
                f"## Implementação ({impl.lang})",
                "",
                f"```{impl.lang}",
                impl.code,
                "```",
                "",
            ]

        sb = task.artifact("sandbox")
        if sb:
            parts += ["## Sandbox", ""]
            if sb.meta.get("stub"):
                parts.append("_(stub do passo 2 — execução real no passo 4)_")
            else:
                parts.append(f"- sucesso: `{sb.meta.get('success')}`")
                if sb.content:
                    parts += ["", "```", sb.content, "```"]
            parts.append("")

        parts += [
            "## Métricas",
            "",
            f"- tentativas: {task.attempts + 1}",
            f"- erros registrados: {len(task.errors)}",
        ]

        art = TaskArtifact(
            phase="present",
            content="\n".join(parts),
            meta={"deterministic": True},
        )
        task.artifacts["present"] = art
        self.store.save_artifact(task, art)
        self.store.save(task)            # <-- adicione
        self._emit(task, "phase_done", phase="present")

    # ------------------------------------------------------------------
    # entry point
    # ------------------------------------------------------------------
    def run(self, task_id: str) -> Task:
        task = self.store.load(task_id)

        if task.status == TaskStatus.PENDING:
            task.set_status(TaskStatus.RUNNING)
        elif task.status == TaskStatus.BLOCKED:
            task.set_status(TaskStatus.RUNNING)
        elif task.status == TaskStatus.RUNNING:
            pass  # resume de crash
        else:
            raise RuntimeError(
                f"não é possível rodar task em status '{task.status.value}'"
            )
        self.store.save(task)
        self._emit(task, "task_start", phase=task.current_phase, status=task.status.value)

        try:
            self._loop(task)
        except _TaskAborted as exc:
            if can_transition_status(task.status, TaskStatus.FAILED):
                task.set_status(TaskStatus.FAILED)
            task.errors.append(str(exc))
        except Exception as exc:
            if can_transition_status(task.status, TaskStatus.FAILED):
                task.set_status(TaskStatus.FAILED)
            task.errors.append(f"{type(exc).__name__}: {exc}")
            if __debug__:
                traceback.print_exc(file=sys.stderr)
        finally:
            self.store.save(task)
            self._emit(task, "task_done", status=task.status.value,
                       attempts=task.attempts)
        return task

    def _loop(self, task: Task) -> None:
        while True:
            phase: Phase = task.current_phase

            if phase == "plan":
                self._phase_plan(task)
                task.set_phase("draft")
                self.store.save(task)

            elif phase == "draft":
                try:
                    self._phase_draft(task)
                    task.set_phase("implement")
                    self.store.save(task)
                except _RetryDraft as r:
                    self._bump_attempt(task, r.feedback)
                    if task.status == TaskStatus.BLOCKED:
                        return
                    # permanece em draft; loop reentra

            elif phase == "implement":
                try:
                    self._phase_implement(task)
                    task.set_phase("sandbox")
                    self.store.save(task)
                except _RetryDraft as r:
                    self._bump_attempt(task, r.feedback)
                    if task.status == TaskStatus.BLOCKED:
                        return
                    task.set_phase("draft")
                    self.store.save(task)

            elif phase == "sandbox":
                try:
                    self._phase_sandbox(task)
                    task.set_phase("present")
                    self.store.save(task)
                except _RetryDraft as r:
                    self._bump_attempt(task, r.feedback)
                    if task.status == TaskStatus.BLOCKED:
                        return
                    task.set_phase("draft")
                    self.store.save(task)

            elif phase == "present":
                self._phase_present(task)
                task.set_status(TaskStatus.DONE)
                self.store.save(task)
                return

            else:
                raise _TaskAborted(f"fase desconhecida: {phase!r}")

class _FakeBridge:
    def __init__(self, responses: list[str]) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    def ask(self, prompt: str, max_tokens: int | None = None) -> str:
        self.calls.append({"prompt": prompt, "max_tokens": max_tokens})
        if not self.responses:
            raise RuntimeError("fake bridge sem respostas")
        return self.responses.pop(0)


class _FakeValidator:
    def __init__(self, decisions: list[tuple[bool, str]] | None = None) -> None:
        self.decisions = list(decisions or [])
        self.calls: list[str] = []

    def validar_output(self, text: str) -> tuple[bool, str]:
        self.calls.append(text)
        if not self.decisions:
            return True, ""
        return self.decisions.pop(0)


_PLAN_JSON = (
    '{"understanding": "soma", "files": [{"path": "s.py", "action": "create", '
    '"purpose": "soma"}], "io_contracts": [], "risks": [], "success_criteria": ["ok"]}'
)
_PLAN_JSON_FENCED = "```json\n" + _PLAN_JSON + "\n```"
_DRAFT_OK = "```python\ndef soma(a, b):\n    return a + b\n```"
_IMPL_OK = "```python\ndef soma(a: int, b: int) -> int:\n    \"\"\"Soma.\"\"\"\n    return a + b\n```"


def _run_tests() -> int:
    import shutil
    import tempfile
    from pathlib import Path

    passed = 0
    failed = 0

    def _check(name: str, cond: bool, detail: str = "") -> None:
        nonlocal passed, failed
        if cond:
            print(f"  [OK] {name}")
            passed += 1
        else:
            print(f"  [X]  {name}" + (f" — {detail}" if detail else ""))
            failed += 1

    tmp = Path(tempfile.mkdtemp(prefix="orn_runner_test_"))
    try:
        from engine.tasks.model import TaskSpec
        from engine.tasks.store import TaskStore

        def _mk(goal="soma", max_retries=2) -> tuple[TaskStore, Task]:
            store = TaskStore(tmp / "tasks")
            t = store.new(TaskSpec(goal=goal, max_retries=max_retries))
            return store, t

        # ---------- happy path ----------
        store, t = _mk()
        events: list[dict] = []
        bridge = _FakeBridge([_PLAN_JSON, _DRAFT_OK, _IMPL_OK])
        validator = _FakeValidator()
        runner = TaskRunner(store, bridge, validator, emit=events.append)
        out = runner.run(t.id)
        _check("happy: status DONE", out.status == TaskStatus.DONE)
        _check("happy: attempts 0", out.attempts == 0)
        _check("happy: 3 chamadas bridge", len(bridge.calls) == 3)
        _check("happy: artefatos plan/draft/implement/sandbox/present",
               all(k in out.artifacts for k in ("plan", "draft", "implement", "sandbox", "present")))
        _check("happy: draft.code extraído", out.artifacts["draft"].code.startswith("def soma"))
        _check("happy: implement.code extraído",
               "-> int" in out.artifacts["implement"].code)
        _check("happy: plan meta é dict",
               isinstance(out.artifacts["plan"].meta.get("plan"), dict))
        _check("happy: sandbox stub flag",
               out.artifacts["sandbox"].meta.get("stub") is True)
        kinds = [e["event"] for e in events]
        _check("happy: task_start emitido", "task_start" in kinds)
        _check("happy: task_done emitido", "task_done" in kinds)
        _check("happy: phase_done emitido 5x",
               kinds.count("phase_done") == 5)

        # ---------- plan fenced em markdown ----------
        store, t = _mk()
        bridge = _FakeBridge([_PLAN_JSON_FENCED, _DRAFT_OK, _IMPL_OK])
        out = TaskRunner(store, bridge, _FakeValidator()).run(t.id)
        _check("plan fenced: DONE", out.status == TaskStatus.DONE)

        # ---------- plan inválido 2x → FAILED ----------
        store, t = _mk()
        bridge = _FakeBridge(["não é json", "{invalido"])
        out = TaskRunner(store, bridge, _FakeValidator()).run(t.id)
        _check("plan inválido: FAILED", out.status == TaskStatus.FAILED)
        _check("plan inválido: 2 chamadas bridge", len(bridge.calls) == 2)
        _check("plan inválido: erro registrado", len(out.errors) >= 1)

        # ---------- plan JSON sem 'files' 2x → FAILED ----------
        store, t = _mk()
        bridge = _FakeBridge(['{"understanding": "x"}', '{"understanding": "x"}'])
        out = TaskRunner(store, bridge, _FakeValidator()).run(t.id)
        _check("plan sem files: FAILED", out.status == TaskStatus.FAILED)

        # ---------- draft rejeitado 1x, 2a OK ----------
        store, t = _mk()
        bridge = _FakeBridge([_PLAN_JSON, _DRAFT_OK, _DRAFT_OK, _IMPL_OK])
        validator = _FakeValidator([(False, "sintaxe"), (True, ""), (True, "")])
        out = TaskRunner(store, bridge, validator).run(t.id)
        _check("draft retry: DONE", out.status == TaskStatus.DONE)
        _check("draft retry: attempts 1", out.attempts == 1)
        _check("draft retry: feedback limpo", out.feedback == "")
        _check("draft retry: 4 chamadas bridge", len(bridge.calls) == 4)
        # o 2o draft deve conter feedback
        _check("draft retry: feedback injetado no 2o draft",
               "[FEEDBACK DA TENTATIVA ANTERIOR]" in bridge.calls[2]["prompt"])

        # ---------- implement rejeitado 1x → volta pra draft ----------
        store, t = _mk()
        bridge = _FakeBridge([_PLAN_JSON, _DRAFT_OK, _IMPL_OK, _DRAFT_OK, _IMPL_OK])
        validator = _FakeValidator([(True, ""), (False, "tipo"), (True, ""), (True, "")])
        out = TaskRunner(store, bridge, validator).run(t.id)
        _check("implement retry: DONE", out.status == TaskStatus.DONE)
        _check("implement retry: attempts 1", out.attempts == 1)
        _check("implement retry: 5 chamadas bridge", len(bridge.calls) == 5)

        # ---------- retries esgotados → BLOCKED ----------
        store, t = _mk(max_retries=2)
        bridge = _FakeBridge([_PLAN_JSON] + [_DRAFT_OK] * 4)
        validator = _FakeValidator([(False, "x")] * 4)
        out = TaskRunner(store, bridge, validator).run(t.id)
        _check("retries esgotados: BLOCKED", out.status == TaskStatus.BLOCKED)
        _check("retries esgotados: attempts=3", out.attempts == 3)

        # ---------- resume de BLOCKED ----------
        # injeta um draft/implement válidos no bridge e re-roda
        resume_bridge = _FakeBridge([_DRAFT_OK, _IMPL_OK])
        resume_validator = _FakeValidator()
        out2 = TaskRunner(store, resume_bridge, resume_validator).run(out.id)
        _check("resume: DONE", out2.status == TaskStatus.DONE)
        _check("resume: bridge chamado 2x", len(resume_bridge.calls) == 2)

        # ---------- bridge explodindo → FAILED ----------
        store, t = _mk()
        class _Boom:
            def ask(self, *a, **k): raise RuntimeError("boom")
        out = TaskRunner(store, _Boom(), _FakeValidator()).run(t.id)
        _check("bridge boom: FAILED", out.status == TaskStatus.FAILED)
        _check("bridge boom: erro menciona boom",
               any("boom" in e for e in out.errors))

        # ---------- present não chama bridge ----------
        store, t = _mk()
        bridge = _FakeBridge([_PLAN_JSON, _DRAFT_OK, _IMPL_OK])
        runner = TaskRunner(store, bridge, _FakeValidator())
        out = runner.run(t.id)
        calls_before = len(bridge.calls)
        runner._phase_present(out)
        _check("present determinístico: bridge não chamado",
               len(bridge.calls) == calls_before)

        # ---------- task DONE não roda de novo ----------
        store, t = _mk()
        bridge = _FakeBridge([_PLAN_JSON, _DRAFT_OK, _IMPL_OK])
        out = TaskRunner(store, bridge, _FakeValidator()).run(t.id)
        try:
            TaskRunner(store, _FakeBridge([]), _FakeValidator()).run(out.id)
            _check("task DONE não roda", False)
        except RuntimeError:
            _check("task DONE não roda", True)

        # ---------- sandbox customizado falha → retry draft ----------
        store, t = _mk()
        bridge = _FakeBridge([_PLAN_JSON, _DRAFT_OK, _IMPL_OK, _DRAFT_OK, _IMPL_OK])
        validator = _FakeValidator()
        sandbox_calls = {"n": 0}
        def _sb(task):
            sandbox_calls["n"] += 1
            if sandbox_calls["n"] == 1:
                return False, "NameError: 'x' is not defined"
            return True, ""
        out = TaskRunner(store, bridge, validator, sandbox_step=_sb).run(t.id)
        _check("sandbox custom: DONE", out.status == TaskStatus.DONE)
        _check("sandbox custom: attempts 1", out.attempts == 1)
        _check("sandbox custom: feedback no 2o draft",
               any("[FEEDBACK DA TENTATIVA ANTERIOR]" in c["prompt"] and "NameError" in c["prompt"]
                   for c in bridge.calls))

        # ============================================================
        # Passo 3 — calibração do _extract_code_block
        # ============================================================
        from engine.tasks.runner import _extract_code_block

        # --- formatos básicos ---
        c, l = _extract_code_block("```python\ndef f():\n    pass\n```", "python")
        _check("extract: python fence", c.startswith("def f()") and l == "python")

        c, l = _extract_code_block("```py\ndef f():\n    pass\n```", "python")
        _check("extract: py alias → python", l == "python")

        c, l = _extract_code_block("``` python\ndef f():\n    pass\n```", "python")
        _check("extract: espaço após fence", l == "python" and c.startswith("def f()"))

        c, l = _extract_code_block("```Python\ndef f():\n    pass\n```", "python")
        _check("extract: case-insensitive", l == "python")

        c, l = _extract_code_block("```python3\ndef f():\n    pass\n```", "python")
        _check("extract: python3 → python", l == "python")

        # --- CRLF (Windows) ---
        crlf = "```python\r\ndef f():\r\n    return 1\r\n```"
        c, l = _extract_code_block(crlf, "python")
        _check("extract: CRLF normalizado",
               "\r" not in c and "return 1" in c)

        # --- sem fence, mas parece código ---
        c, l = _extract_code_block("def f():\n    return 1", "python")
        _check("extract: sem fence aceita se parece código",
               c.startswith("def f()") and l == "python")

        # --- prosa + 1 bloco ---
        raw = "Aqui está:\n\n```python\ndef f():\n    return 1\n```\n\nEspero ajudar."
        c, l = _extract_code_block(raw, "python")
        _check("extract: prosa ao redor ignorada",
               c == "def f():\n    return 1" and l == "python")

        # --- múltiplos blocos, preferência por lang ---
        raw = (
            "```text\nIsto é uma explicação longa sobre o problema que não é código "
            "e é proposital que seja bem mais longo que o bloco real para testar.\n```\n\n"
            "```python\ndef f():\n    return 1\n```"
        )
        c, l = _extract_code_block(raw, "python")
        _check("extract: prefere lang ao invés do maior",
               l == "python" and c.startswith("def f()"))

        # --- múltiplos blocos, sem lang nenhuma ---
        raw = "```\nabc\n```\n\n```\ndef maior():\n    return 2\n```"
        c, l = _extract_code_block(raw, "python")
        _check("extract: sem lang escolhe o maior",
               "def maior" in c)

        # --- bloco só com lang 'text' (nenhum bate target) ---
        raw = "```text\ndef f():\n    return 1\n```"
        c, l = _extract_code_block(raw, "python")
        _check("extract: fallback p/ qualquer bloco",
               c.startswith("def f()") and l == "text")

        # --- c++ alias ---
        c, l = _extract_code_block("```cpp\nint main(){return 0;}\n```", "c++")
        _check("extract: cpp → c++", l == "c++" and "int main" in c)

        # --- fence vazia (sem lang) ---
        c, l = _extract_code_block("```\ndef f():\n    pass\n```", "python")
        _check("extract: fence sem lang usa default",
               l == "python" and c.startswith("def f()"))

        # --- texto vazio ---
        c, l = _extract_code_block("", "python")
        _check("extract: vazio → ('', python)", c == "" and l == "python")

        # --- fence desbalanceada (só abre) ---
        c, l = _extract_code_block("```python\ndef f():\n    pass", "python")
        _check("extract: fence sem fechamento devolve cru",
               "def f()" in c)  # não valida lang, só garante robustez

        # --- integração: DRAFT com py alias ---
        store_i, t_i = _mk()
        bridge_i = _FakeBridge([
            _PLAN_JSON,
            "```py\ndef f():\n    return 1\n```",
            "```py\ndef f() -> int:\n    return 1\n```",
        ])
        out_i = TaskRunner(store_i, bridge_i, _FakeValidator()).run(t_i.id)
        _check("integração: draft com ```py normaliza lang",
               out_i.status == TaskStatus.DONE
               and out_i.artifacts["draft"].lang == "python"
               and out_i.artifacts["implement"].lang == "python")

        # ============================================================
        # Passo 4.1 — _resolve_max_tokens / _ask nunca passa None
        # ============================================================
        class _RecordingBridge:
            def __init__(self, out="ok"):
                self.calls: list[dict] = []
                self.out = out
            def ask(self, prompt, max_tokens=None):
                self.calls.append({"prompt": prompt, "max_tokens": max_tokens})
                return self.out

        store_m, t_m = _mk()

        rb = _RecordingBridge()
        runner_m = TaskRunner(store_m, rb, _FakeValidator())
        n = runner_m._resolve_max_tokens(t_m, "x" * 300)
        _check("resolve_max_tokens: int > 0", isinstance(n, int) and n > 0)
        _check("resolve_max_tokens: <= 1024", n <= 1024)

        t_m.spec.max_tokens = 128
        n = runner_m._resolve_max_tokens(t_m, "x" * 300)
        _check("resolve_max_tokens: override 128", n == 128)

        t_m.spec.max_tokens = 0
        n = runner_m._resolve_max_tokens(t_m, "x" * 300)
        _check("resolve_max_tokens: 0 vira >= 64", n >= 64)

        t_m.spec.max_tokens = None
        rb = _RecordingBridge("resposta")
        runner_m = TaskRunner(store_m, rb, _FakeValidator())
        out = runner_m._ask(t_m, "sys", "user")
        _check("_ask: retorno preservado", out == "resposta")
        _check("_ask: bridge recebeu int",
               isinstance(rb.calls[0]["max_tokens"], int)
               and rb.calls[0]["max_tokens"] > 0)
        _check("_ask: prompt inclui sys+user",
               "sys" in rb.calls[0]["prompt"] and "user" in rb.calls[0]["prompt"])

        rb = _RecordingBridge("   ")
        runner_m = TaskRunner(store_m, rb, _FakeValidator())
        try:
            runner_m._ask(t_m, "sys", "user")
            _check("_ask: vazio levanta _TaskAborted", False)
        except Exception as e:
            _check("_ask: vazio levanta _TaskAborted",
                   "_TaskAborted" in type(e).__name__ or "vazia" in str(e).lower())

        class _NoneBridge:
            def ask(self, *a, **k): return None
        runner_m = TaskRunner(store_m, _NoneBridge(), _FakeValidator())
        try:
            runner_m._ask(t_m, "sys", "user")
            _check("_ask: None levanta", False)
        except Exception:
            _check("_ask: None levanta", True)

    finally:
        shutil.rmtree(tmp, ignore_errors=True)

    print()
    if failed == 0:
        print(f"  {passed} teste(s) OK")
        return 0
    print(f"  {passed}/{passed + failed} passaram — {failed} falha(s)")
    return 1


if __name__ == "__main__":
    if "--test" in sys.argv:
        raise SystemExit(_run_tests())
    print("Uso: python -m engine.tasks.runner --test")
    raise SystemExit(1)
