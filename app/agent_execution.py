"""
Agent execution mixin — chat loop, tool execution, delegation, and plans.

Extracted from agent.py to reduce file size. The Agent dataclass inherits
from this mixin so all ``self.*`` references resolve at runtime.
"""
from __future__ import annotations
import concurrent.futures
import json
import logging
import os
import threading
import time
import uuid
from typing import Any, TYPE_CHECKING

if TYPE_CHECKING:
    from .agent_types import AgentEvent, AgentTask, ExecutionPlan, ExecutionStep

from .agent_types import _ensure_str_content

logger = logging.getLogger("tudou.agent")


class AgentExecutionMixin:
    """Mixin providing chat loop, tool execution, delegation, and plan management."""

    def _execute_tool_with_policy(self, tool_name: str, arguments: dict,
                                   on_event: Any = None) -> str:
        """Execute a tool, checking policy. May block for approval."""
        # Resolve alias (e.g. "exec" → "bash") BEFORE permission check
        from . import tools
        tool_name = tools._TOOL_ALIASES.get(tool_name, tool_name)

        # Inject agent context for tools that need RAG routing
        if tool_name in ("knowledge_lookup",):
            arguments = dict(arguments)
            arguments["_agent_profile"] = self.profile
            arguments["agent_id"] = self.id

        # Check agent-level denied tools
        if tool_name in self.profile.denied_tools:
            return f"DENIED: Tool '{tool_name}' is not permitted for this agent."

        # Check agent-level allowed tools (empty list = all allowed)
        if self.profile.allowed_tools and tool_name not in self.profile.allowed_tools:
            return f"DENIED: Tool '{tool_name}' is not in this agent's allowed list."

        # Scheduled / background task: skip approval (already authorized at creation)
        if getattr(self, '_scheduled_context', False):
            with self._sandbox_scope():
                result = tools.execute_tool(tool_name, arguments)
            return result

        # Agent-level exec_policy: 'full' = auto-approve all tools
        if self.profile.exec_policy == "full":
            with self._sandbox_scope():
                result = tools.execute_tool(tool_name, arguments)
            return result

        from .auth import get_auth
        auth = get_auth()
        policy = auth.tool_policy

        # Check if this agent auto-approves this tool
        if tool_name in self.profile.auto_approve_tools:
            with self._sandbox_scope():
                result = tools.execute_tool(tool_name, arguments)
            auth.audit("tool_executed", actor=self.name, target=tool_name,
                       detail=result[:200])
            return result

        decision, reason = policy.check_tool(
            tool_name, arguments,
            agent_id=self.id, agent_name=self.name,
            agent_priority=getattr(self.profile, 'priority', 3),
        )

        # MODERATE risk: if agent_approvable and this agent (or a superior)
        # has authority, auto-approve it
        if decision == "agent_approvable":
            agent_pri = getattr(self.profile, 'priority', 3)
            if policy.can_agent_approve(self.id, agent_pri, "moderate"):
                decision = "allow"
                reason = f"Agent-approved (priority={agent_pri})"
                auth.audit("tool_agent_approved", actor=self.name,
                           target=tool_name, detail=reason)
            else:
                # Escalate to human approval
                decision = "needs_approval"

        if decision == "deny":
            auth.audit("tool_denied", actor=self.name, target=tool_name,
                       detail=f"Auto-denied: {reason}", success=False)
            from .agent_types import AgentEvent
            evt = AgentEvent(time.time(), "approval", {
                "tool": tool_name, "status": "denied", "reason": reason,
                "agent_name": self.name,
            })
            self._log(evt.kind, evt.data)
            if on_event:
                on_event(evt)
            return f"DENIED: {reason}. This operation is not allowed for security reasons."

        if decision == "needs_approval":
            from .agent_types import AgentStatus
            self.status = AgentStatus.WAITING_APPROVAL

            # Create the PendingApproval FIRST so approval_id is available
            # for the SSE event (clients need it to call the approve API).
            approval = policy.request_approval(
                tool_name, arguments,
                agent_id=self.id, agent_name=self.name,
                reason=reason,
            )

            from .agent_types import AgentEvent
            evt = AgentEvent(time.time(), "approval", {
                "tool": tool_name, "status": "pending", "reason": reason,
                "arguments": self._truncate_dict(arguments),
                "agent_name": self.name,
                "approval_id": approval.approval_id,
            })
            self._log(evt.kind, evt.data)
            if on_event:
                on_event(evt)

            auth.audit("tool_approval_requested", actor=self.name,
                       target=tool_name,
                       detail=json.dumps(self._truncate_dict(arguments),
                                         ensure_ascii=False)[:300])

            result_status = policy.wait_for_approval(approval)
            from .agent_types import AgentStatus
            self.status = AgentStatus.BUSY

            if result_status != "approved":
                auth.audit("tool_denied", actor=self.name, target=tool_name,
                           detail=f"Human denied/expired: {approval.decided_by}",
                           success=False)
                from .agent_types import AgentEvent
                evt = AgentEvent(time.time(), "approval", {
                    "tool": tool_name, "status": "denied",
                    "reason": f"{result_status} by {approval.decided_by or 'timeout'}",
                "agent_name": self.name,
                })
                self._log(evt.kind, evt.data)
                if on_event:
                    on_event(evt)
                return (f"DENIED: Tool execution was {result_status}. "
                        f"Decided by: {approval.decided_by or 'timeout'}. "
                        f"Please try an alternative approach.")

            auth.audit("tool_approved", actor=self.name, target=tool_name,
                       detail=f"Approved by {approval.decided_by}")
            from .agent_types import AgentEvent
            evt = AgentEvent(time.time(), "approval", {
                "tool": tool_name, "status": "approved",
                "decided_by": approval.decided_by,
                "agent_name": self.name,
            })
            self._log(evt.kind, evt.data)
            if on_event:
                on_event(evt)

        # ── Middleware: PRE_TOOL (lint check, etc.) ──
        try:
            from .middleware import ensure_pipeline, MiddlewareContext, Stage
            pipe = ensure_pipeline()
            pre_ctx = MiddlewareContext(
                agent_id=self.id, agent_name=self.name,
                tool_name=tool_name, tool_arguments=arguments,
            )
            pre_result = pipe.run(Stage.PRE_TOOL, pre_ctx)
            if pre_result.short_circuited:
                return pre_result.value  # Lint check failed — return error to LLM
        except Exception as _mw_err:
            logger.debug("pre_tool middleware skipped: %s", _mw_err)

        with self._sandbox_scope():
            result = tools.execute_tool(tool_name, arguments)

        # ── Middleware: POST_TOOL (truncation, etc.) ──
        try:
            from .middleware import ensure_pipeline, MiddlewareContext, Stage
            pipe = ensure_pipeline()
            post_ctx = MiddlewareContext(
                agent_id=self.id, agent_name=self.name,
                tool_name=tool_name, tool_arguments=arguments,
                tool_result=result,
            )
            post_result = pipe.run(Stage.POST_TOOL, post_ctx)
            if post_ctx.tool_result != result:
                result = post_ctx.tool_result  # middleware modified the result
        except Exception as _mw_err:
            logger.debug("post_tool middleware skipped: %s", _mw_err)

        auth.audit("tool_executed", actor=self.name, target=tool_name,
                   detail=result[:200])
        return result

    def _sandbox_scope(self):
        """Install a sandbox policy rooted at this agent's working_dir."""
        from . import sandbox as _sandbox
        import os as _os
        # Use the agent's working_dir as jail root. Fall back to the per-agent
        # workspace directory if no working_dir is configured.
        root = self.working_dir
        if not root:
            from . import DEFAULT_DATA_DIR as _DEFAULT_DD
            root = _os.path.join(
                _os.environ.get("TUDOU_CLAW_DATA_DIR") or _DEFAULT_DD,
                "workspaces", self.id, "sandbox")
        # Honor per-agent sandbox mode if set on the profile, otherwise
        # use the global default from TUDOU_SANDBOX env var.
        mode = getattr(self.profile, "sandbox_mode", "") or ""
        allow_list = list(getattr(self.profile, "sandbox_allow_commands", []) or [])

        # Build allowed_dirs from authorized workspaces + shared workspace
        allowed_dirs = []
        if self.shared_workspace:
            allowed_dirs.append(self.shared_workspace)
        # Add workspaces of authorized agents
        from . import DEFAULT_DATA_DIR as _DEFAULT_DD2
        data_dir = _os.environ.get("TUDOU_CLAW_DATA_DIR") or _DEFAULT_DD2
        for other_agent_id in self.authorized_workspaces:
            ws_path = _os.path.join(data_dir, "workspaces", other_agent_id)
            allowed_dirs.append(ws_path)
        # Allow access to agent's skills directory so granted skill scripts
        # can be executed without sandbox violations.
        agent_skills_dir = _os.path.join(str(self._get_agent_workspace()), "skills")
        if _os.path.isdir(agent_skills_dir):
            allowed_dirs.append(agent_skills_dir)

        policy = _sandbox.SandboxPolicy(
            root=root, mode=mode, allow_list=allow_list,
            agent_id=self.id, agent_name=self.name,
            allowed_dirs=allowed_dirs,
        )
        return _sandbox.sandbox_scope(policy)

    # ---- chat ----

    def chat(self, user_message, on_event: Any = None,
             abort_check: Any = None, source: str = "admin") -> str:
        """
        Run a chat turn. If abort_check is a callable returning True,
        the chat loop will stop early.

        user_message: str for text-only, or list[dict] for multimodal content
                      (OpenAI vision format: [{type:"text",text:...},{type:"image_url",...}])
        source: "admin" for messages from portal UI, "agent:{agent_name}" for inter-agent,
                "system" for system messages
        """
        # ── Token logging context: 让本次 chat 内所有 LLM 调用 ──
        # ── 都能归属到这个 agent，token 统计才能落到 agent.stats ──
        from . import llm
        try:
            llm.set_token_context(agent_id=self.id, project_id="")
        except Exception:
            pass

        with self._lock:
            from .agent_types import AgentStatus
            self.status = AgentStatus.BUSY

            # ── Multimodal content handling ──
            # user_message can be str (text-only) or list[dict] (multimodal)
            _is_multimodal = isinstance(user_message, list)
            # Extract text portion for intent resolution, memory, logging
            if _is_multimodal:
                _user_text = " ".join(
                    p.get("text", "") for p in user_message
                    if isinstance(p, dict) and p.get("type") == "text"
                ).strip() or "(multimodal input)"
                _msg_content = user_message  # list format for LLM
            else:
                _user_text = str(user_message or "")
                _msg_content = _user_text   # string format for LLM

            # ── Intent Resolution: classify user intent BEFORE everything ──
            resolved_intent = None
            try:
                from .core.intent_resolver import IntentResolver
                _resolver = getattr(self, "_intent_resolver", None)
                if _resolver is None:
                    _resolver = IntentResolver()
                    self._intent_resolver = _resolver
                resolved_intent = _resolver.resolve(
                    message=_user_text,
                    agent_role=getattr(self, "role", ""),
                    history=[
                        {"role": m.get("role", ""), "content": _ensure_str_content(m.get("content"))}
                        for m in self.messages[-6:]
                        if m.get("role") in ("user", "assistant")
                    ],
                    learning_provider=getattr(self, "learning_provider", ""),
                    learning_model=getattr(self, "learning_model", ""),
                )
                self._last_resolved_intent = resolved_intent
                if resolved_intent and resolved_intent.confidence > 0.3:
                    self._log("intent", {
                        "category": resolved_intent.category,
                        "confidence": round(resolved_intent.confidence, 2),
                        "method": resolved_intent.resolution_method,
                        "slots": {k: v.value for k, v in resolved_intent.slots.items() if v.extracted},
                        "missing": resolved_intent.missing_required,
                    })
            except Exception as _ir_err:
                logger.debug("IntentResolver skipped: %s", _ir_err)

            # ── Memory augmentation: inject relevant facts as LLM CONTEXT ──
            # Memory is background reference, NOT a substitute for LLM reasoning.
            # The LLM always generates the actual answer.
            memory_context: str | None = None
            try:
                memory_context = self._build_memory_context(_user_text)
            except Exception as _mem_err:
                logger.debug("Failed to build memory context: %s", _mem_err)
                memory_context = None

            self._ensure_system_message(current_query=_user_text)
            self._trim_context()
            msg = {"role": "user", "content": _msg_content, "source": source}
            self.messages.append(msg)
            self._log("message", {"role": "user", "content": _user_text[:500], "source": source})

            # --- agent_state shadow (phase-1 grey rollout) ---
            try:
                from .agent_state.shadow import install_into_agent
                _shadow = getattr(self, "_shadow", None) or install_into_agent(self)
                if _shadow is not None:
                    _shadow.record_user(_user_text, source=source)
            except Exception:
                pass

            # --- Memory augmentation: inject retrieved facts as system context ---
            if memory_context:
                self.messages.append({
                    "role": "system",
                    "content": memory_context,
                })

            # --- Enhancement module: pre-thinking injection ---
            if self.enhancer and self.enhancer.enabled:
                pre_think = self.enhancer.pre_think(_user_text)
                if pre_think:
                    self.messages.append({
                        "role": "system",
                        "content": pre_think,
                    })
                    self._log("enhancement", {"action": "pre_think",
                                               "pattern": pre_think[:100]})

            # --- Template Library: auto-match and inject templates ---
            try:
                from .template_library import get_template_library
                tpl_lib = get_template_library()
                matched_templates = tpl_lib.match_templates(
                    _user_text, role=self.role, limit=2)
                if matched_templates:
                    tpl_context = tpl_lib.render_for_agent(
                        matched_templates, max_chars=4000)
                    if tpl_context:
                        self.messages.append({
                            "role": "system",
                            "content": tpl_context,
                        })
                        tpl_names = [t.name for t in matched_templates]
                        self._log("template_match", {
                            "templates": tpl_names,
                            "chars": len(tpl_context),
                        })
            except Exception:
                pass  # template library is optional

            # --- Skill System: auto-match and inject skills ---
            self._active_skill_ids = []
            self._chat_start_time = time.time()
            try:
                from .core.prompt_enhancer import get_prompt_pack_registry
                registry = get_prompt_pack_registry()
                if registry.store.get_active():
                    matched_skills = registry.match_skills(
                        _user_text, top_k=3,
                        agent_skills=self.bound_prompt_packs or None)
                    if matched_skills:
                        skill_ids = [s.skill_id for s in matched_skills]
                        context_text = registry.build_context_injection(
                            skill_ids, max_chars=15000)
                        if context_text:
                            self.messages.append({
                                "role": "system",
                                "content": context_text,
                            })
                            self._active_skill_ids = skill_ids
                            self._log("skill_match", {
                                "skills": [s.name for s in matched_skills],
                                "chars": len(context_text),
                            })
            except Exception:
                pass  # skill system is optional

            # --- src memory engine: transcript + routing ---
            self.transcript.append(_user_text)
            self.turn_count += 1
            # Route prompt through PortRuntime for context enrichment
            try:
                routed = self.route_prompt(_user_text, limit=3)
                if routed:
                    route_info = ", ".join(f"{m.kind}:{m.name}({m.score})"
                                           for m in routed[:3])
                    self._log("routing", {"matches": route_info})
            except Exception:
                routed = []

            def _emit(evt):
                if on_event:
                    try:
                        on_event(evt)
                    except Exception:
                        pass

            def _is_aborted() -> bool:
                if abort_check and callable(abort_check):
                    return abort_check()
                return False

            tool_defs = self._get_effective_tools()
            final_content = ""

            # History: record chat start
            self.history_log.add("chat_start",
                                 f"user={_user_text[:80]}")

            try:
                from pathlib import Path
                old_cwd = os.getcwd()
                if self.working_dir and Path(self.working_dir).is_dir():
                    os.chdir(self.working_dir)

                # ── Real-time provider/model refresh (multimodal-aware) ──
                # Pass the original user_message (may be list for multimodal)
                # so _message_is_multimodal can detect image/audio parts
                _eff_provider, _eff_model = self._resolve_effective_provider_model(
                    user_message=user_message,
                )

                # ── Middleware: PRE_LLM (compaction + model routing) ──
                try:
                    from .middleware import ensure_pipeline, MiddlewareContext, Stage
                    _mw_pipe = ensure_pipeline()
                    _mw_ctx = MiddlewareContext(
                        agent_id=self.id, agent_name=self.name,
                        messages=self.messages,
                        provider=_eff_provider, model=_eff_model,
                        data={"context_limit": self._get_context_limit()},
                    )
                    _mw_result = _mw_pipe.run(Stage.PRE_LLM, _mw_ctx)

                    # Handle compaction signal
                    compaction = _mw_ctx.data.get("compaction_needed")
                    if compaction in ("hard", "critical"):
                        self._compress_context()
                    elif compaction == "soft":
                        self._trim_context()

                    # Handle model routing suggestion
                    model_route = _mw_ctx.data.get("model_route")
                    if model_route and self.auto_route.get("enabled") and self.extra_llms:
                        route_label = str(self.auto_route.get(model_route, "")).strip()
                        if route_label:
                            for _slot in self.extra_llms:
                                if not isinstance(_slot, dict):
                                    continue
                                if str(_slot.get("label", "")).strip() == route_label:
                                    _sp = str(_slot.get("provider", "")).strip()
                                    _sm = str(_slot.get("model", "")).strip()
                                    if _sp or _sm:
                                        logger.info(
                                            "Agent %s: middleware model_route[%s] → %s/%s",
                                            self.id[:8], model_route,
                                            _sp or _eff_provider, _sm or _eff_model,
                                        )
                                        _eff_provider = _sp or _eff_provider
                                        _eff_model = _sm or _eff_model
                                    break
                except Exception as _mw_err:
                    logger.debug("pre_llm middleware skipped: %s", _mw_err)

                logger.info("Agent %s (%s) using provider=%s model=%s",
                            self.name, self.id[:8], _eff_provider, _eff_model)

                max_iters = 20

                # ── Task Checkpoint Injection: 任务恢复上下文 ──
                # 当 agent 处于 EXECUTING/PLANNING 阶段时，注入断点信息
                from .agent_types import AgentPhase
                if self.agent_phase in (AgentPhase.EXECUTING, AgentPhase.PLANNING):
                    checkpoint_ctx = self._build_checkpoint_context()
                    if checkpoint_ctx:
                        self.messages.append({
                            "role": "system",
                            "content": checkpoint_ctx,
                        })
                        self._log("checkpoint_inject", {
                            "phase": self.agent_phase.value,
                            "chars": len(checkpoint_ctx),
                        })
                        self.history_log.add("checkpoint",
                                              f"[Checkpoint] 注入任务恢复上下文 phase={self.agent_phase.value}")

                # Build messages-to-send once per iteration: self.messages
                # (stable prefix) + dynamic context injected at the end.
                # This preserves LM Studio / Ollama KV cache across turns.
                _msgs_to_send = self._inject_dynamic_context(
                    self.messages, current_query=_user_text)

                # Debug: verify multimodal content survives the pipeline
                if _is_multimodal:
                    _has_mm = any(
                        isinstance(m.get("content"), list)
                        for m in _msgs_to_send if m.get("role") == "user"
                    )
                    logger.info(
                        "MULTIMODAL CHECK: input_multimodal=True, "
                        "msgs_to_send has list content=%s, "
                        "provider=%s model=%s",
                        _has_mm, _eff_provider, _eff_model,
                    )
                    # Push a visible event to the chat UI so the user can
                    # verify that image content was received and see which
                    # model will handle it.
                    if on_event and _has_mm:
                        _img_count = sum(
                            1 for m in _msgs_to_send
                            if isinstance(m.get("content"), list)
                            for p in m["content"]
                            if isinstance(p, dict) and p.get("type") in (
                                "image_url", "image", "input_image")
                        )
                        from .agent_types import AgentEvent
                        _emit(AgentEvent(time.time(), "message", {
                            "role": "system",
                            "content": (
                                f"📎 {_img_count} image(s) received — "
                                f"sending to {_eff_provider}/{_eff_model}"
                            ),
                        }))

                for iteration in range(max_iters):
                    if _is_aborted():
                        final_content = final_content or "[Aborted]"
                        break
                    # Rebuild messages-to-send each iteration (self.messages
                    # may have grown with tool results from previous iteration).
                    # Dynamic context is appended at the end — keeps prefix stable.
                    if iteration > 0:
                        _msgs_to_send = self._inject_dynamic_context(
                            self.messages, current_query=_user_text)
                    # Strategy: always try streaming first (with tools).
                    # If the provider doesn't support streaming+tools,
                    # it falls back to non-streaming internally.
                    # For the first attempt when we have on_event, try
                    # streaming WITHOUT tools to get fast text output.
                    # If the model wants to call a tool, we retry with tools.

                    if on_event and not tool_defs:
                        # Pure stream, no tools at all
                        try:
                            gen = llm.chat(
                                _msgs_to_send, tools=None, stream=True,
                                provider=_eff_provider, model=_eff_model,
                            )
                            content = ""
                            for chunk in gen:
                                if _is_aborted():
                                    break
                                content += chunk
                                from .agent_types import AgentEvent
                                evt = AgentEvent(time.time(), "text_delta",
                                                 {"content": chunk})
                                _emit(evt)
                            if _is_aborted():
                                final_content = content or "[Aborted]"
                                break
                            final_content = content
                            self.messages.append({"role": "assistant",
                                                  "content": content,
                                                  "_source": "llm"})
                            self._log("message",
                                      {"role": "assistant",
                                       "content": content,
                                       "source": "llm"})
                            break
                        except Exception:
                            pass  # Fall through

                    # Non-streaming path (with tools support)
                    if _is_aborted():
                        final_content = final_content or "[Aborted]"
                        break
                    try:
                        response = llm.chat_no_stream(
                            _msgs_to_send, tools=tool_defs,
                            provider=_eff_provider, model=_eff_model,
                        )
                    except (ConnectionError, OSError) as conn_err:
                        # Provider unreachable — stop retrying immediately
                        raise RuntimeError(
                            f"LLM provider '{_eff_provider}' connection failed "
                            f"(model={_eff_model}): {conn_err}"
                        ) from conn_err
                    except Exception as llm_err:
                        # Other LLM errors (timeout, auth, etc.)
                        if "timeout" in str(llm_err).lower() or "timed out" in str(llm_err).lower():
                            raise RuntimeError(
                                f"LLM provider '{_eff_provider}' timed out "
                                f"(model={_eff_model}): {llm_err}"
                            ) from llm_err
                        raise
                    msg = response.get("message", {})
                    content = _ensure_str_content(msg.get("content"))
                    tool_calls = msg.get("tool_calls", [])

                    if content:
                        final_content = content
                        from .agent_types import AgentEvent
                        evt = AgentEvent(time.time(), "message",
                                         {"role": "assistant",
                                          "content": content})
                        self._log(evt.kind, evt.data)
                        _emit(evt)

                    # NOTE: text-to-tool-call extraction (for models that
                    # output JSON as text instead of tool_calls) is handled
                    # in llm.py's _normalize_response_tool_calls(), so
                    # tool_calls here is already normalised.

                    if not tool_calls:
                        # Final response — ensure we always emit something
                        if not content and final_content:
                            # LLM returned empty final response but we had
                            # intermediate content — re-emit the last known content
                            from .agent_types import AgentEvent
                            evt = AgentEvent(time.time(), "message",
                                             {"role": "assistant",
                                              "content": final_content})
                            self._log(evt.kind, evt.data)
                            _emit(evt)
                        self.messages.append({"role": "assistant",
                                              "content": content or final_content,
                                              "_source": "llm"})
                        break

                    assistant_msg: dict = {"role": "assistant",
                                           "content": content,
                                           "_source": "llm"}
                    assistant_msg["tool_calls"] = tool_calls
                    self.messages.append(assistant_msg)

                    # Check if all tool calls are parallel-safe
                    from .tools import PARALLEL_SAFE_TOOLS
                    all_parallel_safe = all(
                        tc.get("function", {}).get("name", "unknown") in PARALLEL_SAFE_TOOLS
                        for tc in tool_calls
                    )

                    # Parse all tool calls first
                    parsed_calls = []  # list of (name, arguments, call_id)
                    _empty_args_detected = False
                    for tc in tool_calls:
                        func_info = tc.get("function", {})
                        name = func_info.get("name", "unknown")
                        call_id = tc.get("id", f"call_{uuid.uuid4().hex[:8]}")
                        arguments = func_info.get("arguments", {})
                        if isinstance(arguments, str):
                            try:
                                arguments = json.loads(arguments)
                            except (json.JSONDecodeError, TypeError):
                                logger.warning(
                                    "tool_call '%s': arguments JSON parse "
                                    "failed (len=%d) — likely truncated",
                                    name, len(func_info.get("arguments", "")),
                                )
                                arguments = {}
                        # 双重保护：解析后仍然不是 dict
                        if not isinstance(arguments, dict):
                            try:
                                arguments = json.loads(str(arguments))
                            except (json.JSONDecodeError, TypeError, ValueError):
                                arguments = {"raw": str(arguments)}
                        # Track empty arguments — sign of LLM output truncation
                        if not arguments or arguments == {}:
                            _empty_args_detected = True
                        parsed_calls.append((name, arguments, call_id))

                    # Detect repeated empty-argument tool calls (LLM stuck in
                    # truncation loop). After 2 consecutive failures, inject a
                    # hint and let the LLM produce a text response instead.
                    if _empty_args_detected:
                        if not hasattr(self, '_empty_tc_streak'):
                            self._empty_tc_streak = 0
                        self._empty_tc_streak += 1
                        if self._empty_tc_streak >= 2:
                            logger.warning(
                                "Agent %s: %d consecutive empty tool_call "
                                "arguments — breaking retry loop",
                                self.id[:8], self._empty_tc_streak,
                            )
                            self._empty_tc_streak = 0
                            # Tell LLM to stop calling tools and respond in text
                            self.messages.append({
                                "role": "system",
                                "content": (
                                    "IMPORTANT: Your last tool calls had empty "
                                    "arguments (likely due to output truncation). "
                                    "Please respond with text instead. If you need "
                                    "to write a file, break the content into smaller "
                                    "pieces or describe what you want to write."
                                ),
                            })
                            continue  # skip tool execution, go to next LLM call
                    else:
                        self._empty_tc_streak = 0

                    # Execute in parallel if all tools are safe, otherwise sequential
                    from .tools import MAX_PARALLEL_WORKERS
                    if all_parallel_safe and len(parsed_calls) > 1:
                        def _execute_single_tool(name_args_id):
                            name, arguments, call_id = name_args_id
                            # Inject caller agent ID
                            if name in ("team_create", "send_message", "task_update",
                                        "mcp_call", "bash", "write_file", "edit_file"):
                                arguments["_caller_agent_id"] = self.id
                            # Execute
                            if name == "plan_update":
                                return name, self._handle_plan_update(arguments), call_id
                            else:
                                return name, self._execute_tool_with_policy(
                                    name, arguments, on_event=on_event), call_id

                        with concurrent.futures.ThreadPoolExecutor(
                            max_workers=MAX_PARALLEL_WORKERS
                        ) as executor:
                            futures = [
                                executor.submit(_execute_single_tool, (name, arguments, call_id))
                                for name, arguments, call_id in parsed_calls
                            ]
                            results = []
                            for future in concurrent.futures.as_completed(futures):
                                try:
                                    name, result, call_id = future.result()
                                    result = self._handle_large_result(name, result)
                                    results.append((name, result, call_id))
                                except Exception as e:
                                    logger.error(f"Parallel tool execution error: {e}")
                                    results.append(("unknown", f"Error: {e}", f"call_{uuid.uuid4().hex[:8]}"))
                    else:
                        # Sequential execution
                        results = []
                        for name, arguments, call_id in parsed_calls:
                            if _is_aborted():
                                break

                            from .agent_types import AgentEvent
                            evt = AgentEvent(time.time(), "tool_call",
                                             {"name": name,
                                              "arguments": self._truncate_dict(arguments)})
                            self._log(evt.kind, evt.data)
                            _emit(evt)

                            # Inject caller agent ID for tools that need agent context
                            if name in ("team_create", "send_message", "task_update",
                                        "mcp_call", "bash", "write_file", "edit_file"):
                                arguments["_caller_agent_id"] = self.id

                            # Handle plan_update internally (needs agent context)
                            if name == "plan_update":
                                result = self._handle_plan_update(arguments)
                                from .agent_types import AgentEvent
                                _emit(AgentEvent(time.time(), "plan_update",
                                                 {"plan": self.get_current_plan()}))
                            else:
                                result = self._execute_tool_with_policy(
                                    name, arguments, on_event=on_event)

                            # Handle large results
                            result = self._handle_large_result(name, result)

                            results.append((name, result, call_id))

                    # Process and emit all results
                    for name, result, call_id in results:
                        # Ensure result is always a string for safe operations
                        result_str = result if isinstance(result, str) else json.dumps(result, ensure_ascii=False)
                        from .agent_types import AgentEvent
                        evt = AgentEvent(time.time(), "tool_result",
                                         {"name": name, "result": result_str[:1000]})
                        self._log(evt.kind, evt.data)
                        _emit(evt)

                        # === 记录 Agent 自身操作到记忆 ===
                        self._record_tool_action(name, result_str)

                        # Check and inject budget pressure note
                        budget_note = llm.get_budget_pressure_note(iteration, max_iters)
                        if budget_note:
                            result_content = result_str + "\n\n" + budget_note
                        else:
                            result_content = result_str

                        self.messages.append({
                            "role": "tool",
                            "content": result_content,
                            "tool_call_id": call_id,
                        })

                        # --- agent_state shadow (phase-1 grey rollout) ---
                        try:
                            _shadow = getattr(self, "_shadow", None)
                            if _shadow is not None:
                                _shadow.record_tool_result(name, result_str)
                        except Exception:
                            pass

                os.chdir(old_cwd)
                from .agent_types import AgentStatus
                self.status = AgentStatus.IDLE

                # --- src integration: track cost & history ---
                if final_content:
                    in_tokens = len(_user_text.split())
                    out_tokens = len(final_content.split())
                    self.total_input_tokens += in_tokens
                    self.total_output_tokens += out_tokens
                    from src.costHook import apply_cost_hook
                    apply_cost_hook(self.cost_tracker,
                                    f"chat:{self.id[:6]}", in_tokens + out_tokens)
                    self.history_log.add("chat_done",
                                         f"[LLM] in={in_tokens} out={out_tokens} total_cost={self.cost_tracker.total_units}")
                    if self._query_engine is not None:
                        from src.models import UsageSummary
                        self._query_engine.total_usage = UsageSummary(
                            input_tokens=self.total_input_tokens,
                            output_tokens=self.total_output_tokens,
                        )
                    if len(self.transcript.entries) > self.profile.max_context_messages:
                        self.compact_memory()

                    # --- Enhancement module: auto-learn from interaction ---
                    if self.enhancer and self.enhancer.enabled:
                        try:
                            learn_result = self.enhancer.learn_from_interaction(
                                user_message=_user_text,
                                agent_response=final_content[:500],
                                outcome="success",
                            )
                            # 将自我学习的成果也写入 L3 记忆 (向量化)
                            if learn_result:
                                self._sync_enhancement_to_memory(learn_result)
                        except Exception:
                            pass

                    # --- Execution Analyzer: auto-analysis after chat ---
                    try:
                        from .core.execution_analyzer import analyze_and_grow
                        analysis = analyze_and_grow(
                            self,
                            task_id=f"chat_{int(self._chat_start_time)}",
                            start_time=self._chat_start_time,
                        )
                        if analysis and self._active_skill_ids:
                            from .core.prompt_enhancer import get_prompt_pack_registry
                            registry = get_prompt_pack_registry()
                            tools_used = [e.data.get("tool", "") for e in self.events[-50:]
                                          if e.kind == "tool_call"]
                            for sid in self._active_skill_ids:
                                applied = len(tools_used) > 0
                                registry.mark_skill_applied(
                                    sid, applied=applied,
                                    task_completed=analysis.task_completed)
                    except Exception:
                        pass  # auto-analysis is optional

                    # --- Three-layer memory: post-response write-back ---
                    self._memory_write_back(_user_text, final_content)

                    # --- Update state machine phase ---
                    self._update_agent_phase()

            except Exception as e:
                # Per-agent error isolation: log the error but recover to IDLE
                # so this agent remains usable and doesn't block the system.
                from .agent_types import AgentEvent
                evt = AgentEvent(time.time(), "error", {"error": str(e)})
                self._log(evt.kind, evt.data)
                _emit(evt)
                logger.error("Agent %s (%s) chat error: %s", self.name, self.id, e)
                try:
                    os.chdir(old_cwd)
                except Exception:
                    pass
                final_content = f"Error: {e}"
                # Recover to IDLE — the error is recorded in events/history,
                # but the agent should not stay in ERROR permanently.
                from .agent_types import AgentStatus
                self.status = AgentStatus.IDLE
                # --- agent_state shadow (phase-1 grey rollout) ---
                try:
                    _shadow = getattr(self, "_shadow", None)
                    if _shadow is not None:
                        _shadow.record_error(e)
                except Exception:
                    pass

            # --- agent_state shadow (phase-1 grey rollout) ---
            # Final assistant turn — closes the current shadow task.
            try:
                _shadow = getattr(self, "_shadow", None)
                if _shadow is not None:
                    _shadow.record_assistant(final_content or "")
            except Exception:
                pass

            self._auto_save_check()  # Auto-save after each chat turn
            return final_content

    def chat_async(self, user_message, source: str = "admin") -> Any:  # ChatTask
        """Submit a chat as a background task. Returns immediately.

        user_message: str for text-only, or list[dict] for multimodal content
        source: "admin" for messages from portal UI, "agent:{agent_name}" for inter-agent,
                "system" for system messages

        If another chat task is already running for this agent, the new message
        is appended to a per-agent pending queue and will be executed
        sequentially after the current task (and any already-queued tasks)
        finish. We NEVER abort the running task just because a new message
        arrived — that would destroy in-flight work.
        """
        from .chat_task import get_chat_task_manager, ChatTaskStatus
        mgr = get_chat_task_manager()
        # Detect any in-flight task for this agent
        active_states = (ChatTaskStatus.THINKING,
                         ChatTaskStatus.STREAMING,
                         ChatTaskStatus.TOOL_EXEC,
                         ChatTaskStatus.QUEUED,
                         ChatTaskStatus.WAITING_APPROVAL)
        has_active = False
        for existing_task in mgr.get_agent_tasks(self.id):
            if existing_task.status in active_states:
                has_active = True
                break
        # Extract text for task display (create_task expects string)
        _task_display = (
            _ensure_str_content(user_message)
            if isinstance(user_message, (list, dict))
            else str(user_message or "")
        )
        task = mgr.create_task(self.id, _task_display[:500])
        task.set_status(ChatTaskStatus.QUEUED, "Queued", 0)

        # Ensure the per-agent pending-message queue exists
        if not hasattr(self, "_pending_chat_queue") or self._pending_chat_queue is None:
            self._pending_chat_queue = []
        if not hasattr(self, "_pending_chat_lock") or self._pending_chat_lock is None:
            self._pending_chat_lock = threading.Lock()

        if has_active:
            with self._pending_chat_lock:
                self._pending_chat_queue.append((task, user_message, source))
                queue_depth = len(self._pending_chat_queue)
            logger.info(
                "Agent %s busy — queued chat task %s (queue depth=%d)",
                self.id[:8], task.id, queue_depth)
            try:
                task.push_event({
                    "type": "queued",
                    "content": f"⏳ 排队中 ({queue_depth}) — 等上一轮对话结束",
                    "queue_position": queue_depth,
                })
            except Exception:
                pass
            return task

        def _run(task=task, user_message=user_message, source=source):
            try:
                from . import llm
                # Show which provider/model is being used
                _prov_name = self.provider or "default"
                _mdl_name = self.model or "default"
                try:
                    reg = llm.get_registry()
                    entry = reg.get(self.provider)
                    if entry:
                        _prov_name = f"{entry.name} ({entry.kind})"
                except Exception:
                    pass
                task.set_status(ChatTaskStatus.THINKING,
                                f"🧠 Thinking... ({_mdl_name})", 10)
                task.push_event({"type": "thinking",
                                 "content": f"🧠 Thinking... ({_mdl_name})"})

                _tool_count = [0]  # track tool iterations for progress

                def _on_event(evt):
                    """Bridge agent events into ChatTask events."""
                    ts = evt.timestamp  # unix epoch seconds
                    if evt.kind == "text_delta":
                        task.set_status(ChatTaskStatus.STREAMING,
                                        "Generating response...", 80)
                        task.push_event({"type": "text_delta",
                                         "content": evt.data.get("content", ""),
                                         "timestamp": ts})
                    elif evt.kind == "message" and evt.data.get("role") == "assistant":
                        task.set_status(ChatTaskStatus.STREAMING,
                                        "Generating response...", 85)
                        task.push_event({"type": "text",
                                         "content": evt.data.get("content", ""),
                                         "timestamp": ts})
                    elif evt.kind == "tool_call":
                        _tool_count[0] += 1
                        name = evt.data.get("name", "")
                        # Progress: 20% base + increments per tool (up to 70%)
                        prog = min(70, 20 + _tool_count[0] * 15)
                        task.set_status(ChatTaskStatus.TOOL_EXEC,
                                        f"{name}", prog)
                        task.push_event({
                            "type": "tool_call",
                            "name": name,
                            "args": json.dumps(
                                evt.data.get("arguments", {}),
                                ensure_ascii=False)[:200],
                        })
                    elif evt.kind == "tool_result":
                        prog = min(75, 25 + _tool_count[0] * 15)
                        task.set_status(ChatTaskStatus.THINKING,
                                        "Analyzing...", prog)
                        task.push_event({
                            "type": "tool_result",
                            "name": evt.data.get("name", ""),
                            "content": evt.data.get("result", "")[:500],
                        })
                        task.push_event({"type": "thinking",
                                         "content": "Thinking..."})
                    elif evt.kind == "approval":
                        status = evt.data.get("status", "")
                        if status == "pending":
                            task.set_status(ChatTaskStatus.WAITING_APPROVAL,
                                            "Waiting for approval...", -1)
                            task.push_event({
                                "type": "approval_request",
                                "tool": evt.data.get("tool", ""),
                                "reason": evt.data.get("reason", ""),
                                "arguments": evt.data.get("arguments", {}),
                                "agent_id": self.id,
                                "agent_name": self.name,
                                "approval_id": evt.data.get("approval_id", ""),
                            })
                        elif status in ("approved", "denied"):
                            task.push_event({
                                "type": "approval_" + status,
                                "tool": evt.data.get("tool", ""),
                            })
                    elif evt.kind == "plan_update":
                        task.push_event({
                            "type": "plan_update",
                            "plan": evt.data.get("plan"),
                        })
                    elif evt.kind == "error":
                        task.push_event({"type": "error",
                                         "content": evt.data.get("error", "")})

                result = self.chat(user_message, on_event=_on_event,
                                   abort_check=lambda: task.aborted, source=source)
                task.result = result
                if task.aborted:
                    # Already set to ABORTED by abort()
                    pass
                else:
                    # All answers now come from the LLM. Memory is only
                    # injected as background context — no more short-circuit.
                    # --- agent_state shadow (phase-2 envelope injection) ---
                    # Push any artifacts produced during this turn to the
                    # frontend BEFORE the "done" event so the FileCard
                    # widgets attach to the just-finished assistant bubble.
                    # Wrapped in try/except — never break the live path.
                    try:
                        _shadow = getattr(self, "_shadow", None)
                        if _shadow is not None:
                            refs = _shadow.build_envelope_refs()
                            if refs:
                                task.push_event({
                                    "type": "artifact_refs",
                                    "refs": refs,
                                })
                    except Exception:
                        pass
                    task.set_status(ChatTaskStatus.COMPLETED, "Done", 100)
                    task.push_event({"type": "done", "source": "llm"})
            except Exception as e:
                if task.aborted:
                    pass  # Abort may cause exceptions, ignore
                else:
                    task.error = str(e)
                    task.set_status(ChatTaskStatus.FAILED, f"Error: {e}", -1)
                    task.push_event({"type": "error", "content": str(e)})
                    task.push_event({"type": "done"})
            finally:
                # Persist chat history so messages survive a restart.
                # We append to self.messages during chat() but nothing upstream
                # of that call flushes to disk, so we do it here at the end of
                # every chat task (success, failure, or abort).
                try:
                    from .hub import get_hub as _get_hub
                    _hub = _get_hub()
                    if _hub is not None:
                        try:
                            _hub._save_agent_workspace(self)
                        except Exception:
                            pass
                        # Also bump the aggregate JSON/SQLite dump so the
                        # sidebar-state load path sees fresh messages.
                        try:
                            _hub._save_agents()
                        except Exception:
                            pass
                except Exception as _persist_err:
                    logger.debug("post-chat persist failed: %s", _persist_err)

                # Drain pending chat queue: if the user typed more messages
                # while we were busy, run the next one now (sequentially).
                try:
                    next_item = None
                    lock = getattr(self, "_pending_chat_lock", None)
                    if lock is not None:
                        with lock:
                            q = getattr(self, "_pending_chat_queue", None) or []
                            if q:
                                next_item = q.pop(0)
                                # Refresh queue-position events for remaining
                                for _i, (_t, _, _) in enumerate(q):
                                    try:
                                        _t.push_event({
                                            "type": "queued",
                                            "content": f"⏳ 排队中 ({_i+1})",
                                            "queue_position": _i + 1,
                                        })
                                    except Exception:
                                        pass
                    if next_item is not None:
                        nxt_task, nxt_msg, nxt_src = next_item
                        logger.info(
                            "Agent %s draining pending chat task %s",
                            self.id[:8], nxt_task.id)
                        # Re-enter the same _run closure (with rebind via
                        # default parameters) on a fresh worker thread so we
                        # don't grow the call stack.
                        _runner = _run  # local name capture
                        threading.Thread(
                            target=lambda: _runner(nxt_task, nxt_msg, nxt_src),
                            daemon=True,
                        ).start()
                except Exception as _drain_err:
                    logger.debug("pending chat drain failed: %s", _drain_err)

        t = threading.Thread(target=_run, daemon=True)
        t.start()
        return task

    def _handle_plan_update(self, arguments: dict) -> str:
        """Handle the plan_update tool call internally."""
        # 防御：arguments 可能是 str（LLM 返回未解析的 JSON）
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except (json.JSONDecodeError, TypeError):
                return json.dumps({"error": "Invalid arguments format"})
        action = arguments.get("action", "")
        if action == "create_plan":
            # steps 可能是 JSON 字符串而非 list
            # Some models (Qwen) use "plan" instead of "steps"
            steps_raw = arguments.get("steps") or arguments.get("plan") or []
            if isinstance(steps_raw, str):
                try:
                    steps_raw = json.loads(steps_raw)
                except (json.JSONDecodeError, TypeError):
                    steps_raw = []
            if not isinstance(steps_raw, list):
                steps_raw = []
            # 确保每个 step 是 dict
            steps_clean = []
            for s in steps_raw:
                if isinstance(s, str):
                    try:
                        s = json.loads(s)
                    except (json.JSONDecodeError, TypeError):
                        s = {"title": s}
                if isinstance(s, dict):
                    steps_clean.append(s)
            plan = self.create_execution_plan(
                task_summary=arguments.get("task_summary", ""),
                steps=steps_clean,
            )
            step_ids = [{"id": s.id, "title": s.title} for s in plan.steps]
            return json.dumps({"ok": True, "plan_id": plan.id,
                               "steps": step_ids}, ensure_ascii=False)
        elif action == "start_step":
            step = self.update_plan_step(
                arguments.get("step_id", ""), "in_progress")
            return json.dumps({"ok": step is not None,
                               "step": step.to_dict() if step else None},
                              ensure_ascii=False)
        elif action == "complete_step":
            step = self.update_plan_step(
                arguments.get("step_id", ""), "completed",
                arguments.get("result_summary", ""))
            return json.dumps({"ok": step is not None,
                               "step": step.to_dict() if step else None},
                              ensure_ascii=False)
        elif action == "fail_step":
            step = self.update_plan_step(
                arguments.get("step_id", ""), "failed",
                arguments.get("result_summary", ""))
            return json.dumps({"ok": step is not None,
                               "step": step.to_dict() if step else None},
                              ensure_ascii=False)
        elif action == "add_step":
            step = self.add_plan_step(
                title=arguments.get("title", ""),
                detail=arguments.get("detail", ""))
            return json.dumps({"ok": step is not None,
                               "step": step.to_dict() if step else None},
                              ensure_ascii=False)
        else:
            return json.dumps({"error": f"Unknown action: {action}"},
                              ensure_ascii=False)

    # ---- Execution Plan management ----

    def create_execution_plan(self, task_summary: str,
                               steps: list[dict] | None = None) -> ExecutionPlan:
        """Create a new execution plan for the current task."""
        from .agent_types import ExecutionPlan
        plan = ExecutionPlan(task_summary=task_summary)
        if steps:
            for s in steps:
                plan.add_step(
                    title=s.get("title", ""),
                    detail=s.get("detail", ""),
                )
        self._current_plan = plan
        self.execution_plans.append(plan)
        # Emit event so UI can update
        self._log("plan_created", {
            "plan_id": plan.id,
            "task": task_summary[:100],
            "steps": len(plan.steps),
        })
        # 写入 L3 记忆：里程碑/步骤持久化
        self._write_plan_to_memory(plan)
        # 更新状态机
        self._update_agent_phase()
        return plan

    def update_plan_step(self, step_id: str, status: str,
                          result_summary: str = "") -> ExecutionStep | None:
        """Update a step's status in the current plan."""
        plan = self._current_plan
        if not plan:
            return None
        if status == "in_progress":
            step = plan.start_step(step_id)
        elif status == "completed":
            step = plan.complete_step(step_id, result_summary)
        elif status == "failed":
            step = plan.fail_step(step_id, result_summary)
        else:
            return None
        if step:
            self._log("plan_step_updated", {
                "plan_id": plan.id,
                "step_id": step.id,
                "title": step.title,
                "status": status,
            })
            # 步骤完成时写入 L3 记忆
            if status == "completed" and plan:
                self._write_step_completion_to_memory(plan, step)
            # 更新状态机
            self._update_agent_phase()
        return step

    def add_plan_step(self, title: str, detail: str = "") -> ExecutionStep | None:
        """Add a new step to the current plan (during execution)."""
        if not self._current_plan:
            return None
        step = self._current_plan.add_step(title=title, detail=detail)
        self._log("plan_step_added", {
            "plan_id": self._current_plan.id,
            "step_id": step.id,
            "title": title,
        })
        return step

    def get_current_plan(self) -> dict | None:
        """Get the current execution plan for UI display."""
        if self._current_plan:
            return self._current_plan.to_dict()
        return None

    def get_execution_plans(self, limit: int = 10) -> list[dict]:
        """Get recent execution plans."""
        return [p.to_dict() for p in self.execution_plans[-limit:]]

    def delegate(self, task, from_agent: str = "hub", child_agent: Any = None) -> str:
        """
        Enhanced delegate() with depth tracking, isolation, and parent-child relationship.

        Args:
            task: Task description/prompt (str or list[dict] for multimodal)
            from_agent: Name of delegating agent
            child_agent: Optional pre-created Agent instance. If None, creates a new sub-agent.

        Returns:
            Result string from the delegated task

        Raises:
            RuntimeError: If delegation depth exceeds max_delegate_depth
        """
        # Check delegation depth limit
        if self._delegate_depth >= self._max_delegate_depth:
            error_msg = (
                f"Delegation depth limit reached (current: {self._delegate_depth}, "
                f"max: {self._max_delegate_depth}). Cannot spawn new sub-agent."
            )
            self._log("delegation_error", {
                "error": "depth_limit_exceeded",
                "current_depth": self._delegate_depth,
                "max_depth": self._max_delegate_depth,
            })
            logger.error(error_msg)
            return f"ERROR: {error_msg}"

        # ── Admin-configurable fork policy (auth.tool_policy.fork_policy) ──
        # Resolve prospective child_role for role-edge check.
        # If caller passed a pre-built child_agent, use its role; otherwise the
        # new sub-agent will inherit self.role (see child_agent creation below).
        _prospective_child_role = child_agent.role if child_agent is not None else self.role
        _policy = None
        try:
            from .auth import get_auth as _get_auth
            _policy = _get_auth().tool_policy
            cost_last_hour = 0.0
            try:
                cost_last_hour = float(getattr(self.cost_tracker, "cost_last_hour", lambda: 0.0)())
            except Exception:
                pass
            ok, reason = _policy.check_fork_allowed(
                parent_id=self.id, parent_role=self.role,
                parent_depth=self._delegate_depth,
                cost_last_hour_usd=cost_last_hour,
                child_role=_prospective_child_role,
            )
            if not ok:
                self._log("delegation_error", {"error": "fork_policy_blocked", "reason": reason})
                logger.warning("Fork policy blocked: %s", reason)
                return f"ERROR: fork policy denied: {reason}"
            _policy.register_fork_start(self.id)
        except Exception as _e:
            logger.debug("fork policy check skipped: %s", _e)
            _policy = None

        # Create or use provided child agent
        if child_agent is None:
            from .agent import Agent
            child_agent = Agent(
                name=f"{self.name}_child_{uuid.uuid4().hex[:6]}",
                role=self.role,
                model=self.model,
                provider=self.provider,
                # Inherit working directory and shared workspace
                working_dir=self.working_dir,
                shared_workspace=self.shared_workspace,
                system_prompt=self.system_prompt,
                profile=self.profile.__class__.from_dict(self.profile.to_dict()),
                node_id=self.node_id,
                parent_id=self.id,  # Track parent relationship
                authorized_workspaces=list(self.authorized_workspaces),
            )

        # Set child's depth to parent's depth + 1
        child_agent._delegate_depth = self._delegate_depth + 1
        child_agent._max_delegate_depth = self._max_delegate_depth

        # Inherit cancellation event from parent for interrupt signaling
        child_agent._cancellation_event = self._cancellation_event

        # Track active child
        with self._active_children_lock:
            self._active_children.append((child_agent.id, child_agent))

        try:
            # Build prompt with delegation metadata
            _meta = f"[Delegated task from {from_agent} | depth={child_agent._delegate_depth}/{self._max_delegate_depth}]"
            if isinstance(task, list):
                # Multimodal: prepend metadata as text part, keep image parts
                _task_text = " ".join(
                    p.get("text", "") for p in task
                    if isinstance(p, dict) and p.get("type") == "text"
                ).strip() or "(multimodal input)"
                prompt = [{"type": "text", "text": f"{_meta}\n{_task_text}"}] + [
                    p for p in task
                    if isinstance(p, dict) and p.get("type") != "text"
                ]
            else:
                _task_text = str(task or "")
                prompt = f"{_meta}\n{_task_text}"

            # Log delegation event
            self._log("inter_agent_message", {
                "from_agent": from_agent,
                "to_agent": child_agent.id,
                "content": _task_text[:500],
                "msg_type": "delegation",
                "depth": child_agent._delegate_depth,
            })

            logger.info(
                "DELEGATE: parent=%s child=%s task_len=%d depth=%d/%d",
                self.id, child_agent.id, len(_task_text),
                child_agent._delegate_depth, self._max_delegate_depth
            )

            # Execute delegated task with isolation (separate message history)
            result = child_agent.chat(prompt)

            return result

        except Exception as e:
            error_msg = f"Delegation to {child_agent.id} failed: {str(e)}"
            self._log("delegation_error", {
                "error": str(e),
                "child_agent": child_agent.id,
                "depth": child_agent._delegate_depth,
            })
            logger.error(error_msg)
            return f"ERROR: {error_msg}"

        finally:
            # Remove child from active list when done
            with self._active_children_lock:
                self._active_children = [
                    (aid, ag) for aid, ag in self._active_children
                    if aid != child_agent.id
                ]
            # Decrement fork policy counter
            try:
                if _policy is not None:
                    _policy.register_fork_end(self.id)
            except Exception:
                pass

    def delegate_parallel(self, tasks: list[dict], max_workers: int = 4) -> list[dict]:
        """
        Spawn multiple sub-agents in parallel to handle a list of tasks.

        This is a Hermes-style parallel delegation pattern that:
        - Creates isolated sub-agent instances (each with separate message history)
        - Executes tasks concurrently via ThreadPoolExecutor
        - Shares: working_dir, tool access, LLM config, parent context
        - Respects: delegation depth limits, cancellation signals

        Args:
            tasks: List of task dicts, each containing:
                - "task" (str, required): Task description
                - "agent_id" (str, optional): Custom sub-agent ID (for tracking)
                - "context" (str, optional): Extra context to inject into task
            max_workers: Max parallel sub-agents (capped at 4 for safety)

        Returns:
            List of result dicts:
                [{
                    "agent_id": str,
                    "task": str,
                    "status": "success" | "failed" | "cancelled",
                    "result": str,
                    "error": str (if failed),
                    "duration": float,
                }]

        Example:
            results = agent.delegate_parallel([
                {"task": "Review code in file A for security", "agent_id": "reviewer_a"},
                {"task": "Review code in file B for performance", "agent_id": "reviewer_b"},
                {"task": "Write unit tests", "context": "Use pytest framework"},
            ])
        """
        if self._delegate_depth >= self._max_delegate_depth:
            error_msg = (
                f"Cannot delegate_parallel: depth limit reached "
                f"(current: {self._delegate_depth}, max: {self._max_delegate_depth})"
            )
            self._log("parallel_delegation_error", {"error": "depth_limit_exceeded"})
            return [{
                "status": "failed",
                "error": error_msg,
                "task": t.get("task", ""),
                "agent_id": t.get("agent_id", "unknown"),
                "result": "",
                "duration": 0.0,
            } for t in tasks]

        # Cap max_workers at 4 for safety
        max_workers = min(max_workers, 4)

        self._log("parallel_delegation_start", {
            "task_count": len(tasks),
            "max_workers": max_workers,
            "depth": self._delegate_depth,
        })

        logger.info(
            "PARALLEL_DELEGATE: parent=%s tasks=%d workers=%d depth=%d/%d",
            self.id, len(tasks), max_workers,
            self._delegate_depth, self._max_delegate_depth
        )

        results = []
        start_time = time.time()

        # Pre-flight fork policy check (one allowance per parallel task)
        try:
            from .auth import get_auth as _get_auth_pp
            _pp_policy = _get_auth_pp().tool_policy
        except Exception:
            _pp_policy = None

        def _execute_task(task_spec: dict) -> dict:
            """Execute a single task in a sub-agent (runs in thread)."""
            task_text = task_spec.get("task", "")
            agent_id = task_spec.get("agent_id", f"sub_{uuid.uuid4().hex[:6]}")
            context = task_spec.get("context", "")
            task_start = time.time()

            # Per-task fork policy check
            # parallel sub-agents inherit self.role, so child_role = self.role
            if _pp_policy is not None:
                try:
                    ok, reason = _pp_policy.check_fork_allowed(
                        parent_id=self.id, parent_role=self.role,
                        parent_depth=self._delegate_depth,
                        child_role=task_spec.get("role") or self.role,
                    )
                    if not ok:
                        return {"agent_id": agent_id, "task": task_text,
                                "status": "blocked", "result": "",
                                "error": f"fork policy: {reason}",
                                "duration": time.time() - task_start}
                    _pp_policy.register_fork_start(self.id)
                except Exception:
                    pass

            try:
                # Check cancellation signal
                if self._cancellation_event.is_set():
                    return {
                        "agent_id": agent_id,
                        "task": task_text,
                        "status": "cancelled",
                        "result": "",
                        "error": "Cancelled by parent agent",
                        "duration": time.time() - task_start,
                    }

                # Create isolated sub-agent
                from .agent import Agent
                sub_agent = Agent(
                    name=f"{self.name}_parallel_{agent_id}",
                    role=self.role,
                    model=self.model,
                    provider=self.provider,
                    working_dir=self.working_dir,
                    shared_workspace=self.shared_workspace,
                    system_prompt=self.system_prompt,
                    profile=self.profile.__class__.from_dict(self.profile.to_dict()),
                    node_id=self.node_id,
                    parent_id=self.id,
                    authorized_workspaces=list(self.authorized_workspaces),
                )

                # Set depth and inherit cancellation event
                sub_agent._delegate_depth = self._delegate_depth + 1
                sub_agent._max_delegate_depth = self._max_delegate_depth
                sub_agent._cancellation_event = self._cancellation_event

                # Track as active child
                with self._active_children_lock:
                    self._active_children.append((sub_agent.id, sub_agent))

                try:
                    # Build task prompt with context
                    full_task = task_text
                    if context:
                        full_task = f"{task_text}\n\n[Additional Context]\n{context}"

                    prompt = f"[Parallel delegated task | agent={agent_id} | depth={sub_agent._delegate_depth}/{self._max_delegate_depth}]\n{full_task}"

                    # Execute in isolation (separate message history)
                    result = sub_agent.chat(prompt)

                    return {
                        "agent_id": agent_id,
                        "task": task_text,
                        "status": "success",
                        "result": result,
                        "error": "",
                        "duration": time.time() - task_start,
                    }

                finally:
                    # Clean up from active children list
                    with self._active_children_lock:
                        self._active_children = [
                            (aid, ag) for aid, ag in self._active_children
                            if aid != sub_agent.id
                        ]
                    if _pp_policy is not None:
                        try:
                            _pp_policy.register_fork_end(self.id)
                        except Exception:
                            pass

            except Exception as e:
                if _pp_policy is not None:
                    try:
                        _pp_policy.register_fork_end(self.id)
                    except Exception:
                        pass
                return {
                    "agent_id": agent_id,
                    "task": task_text,
                    "status": "failed",
                    "result": "",
                    "error": str(e),
                    "duration": time.time() - task_start,
                }

        # Execute tasks in parallel using ThreadPoolExecutor
        with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = {executor.submit(_execute_task, task): task for task in tasks}

            for future in concurrent.futures.as_completed(futures):
                try:
                    result = future.result(timeout=300)  # 5 min timeout per task
                    results.append(result)
                except Exception as e:
                    task = futures[future]
                    results.append({
                        "agent_id": task.get("agent_id", "unknown"),
                        "task": task.get("task", ""),
                        "status": "failed",
                        "result": "",
                        "error": str(e),
                        "duration": time.time() - start_time,
                    })

        total_duration = time.time() - start_time

        self._log("parallel_delegation_complete", {
            "task_count": len(tasks),
            "success": sum(1 for r in results if r["status"] == "success"),
            "failed": sum(1 for r in results if r["status"] == "failed"),
            "cancelled": sum(1 for r in results if r["status"] == "cancelled"),
            "duration": total_duration,
        })

        logger.info(
            "PARALLEL_DELEGATE COMPLETE: parent=%s success=%d failed=%d duration=%.2fs",
            self.id,
            sum(1 for r in results if r["status"] == "success"),
            sum(1 for r in results if r["status"] == "failed"),
            total_duration
        )

        return results

    def cancel_children(self) -> dict:
        """
        Signal all active child agents to stop execution.

        Sets a threading.Event that child agents check in their chat loops
        (if abort_check callback is used). Returns summary of cancellation.

        Returns:
            {"cancelled_count": int, "agent_ids": list[str]}
        """
        self._cancellation_event.set()

        with self._active_children_lock:
            agent_ids = [aid for aid, _ in self._active_children]
            child_count = len(self._active_children)

        self._log("children_cancelled", {
            "count": child_count,
            "agent_ids": agent_ids,
        })

        logger.info(
            "CANCEL_CHILDREN: parent=%s cancelled=%d agents=%s",
            self.id, child_count, agent_ids
        )

        return {
            "cancelled_count": child_count,
            "agent_ids": agent_ids,
        }
