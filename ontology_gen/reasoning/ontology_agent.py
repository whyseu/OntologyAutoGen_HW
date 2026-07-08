"""Multi-agent framework where agents share one editable ontology.

This module implements :class:`OntologyAgent` — a lightweight agent that wraps
a shared :class:`OntologyEditor` + :class:`SymbolicReasoner`. Multiple agents
attached to the same editor see each other's edits immediately, enabling
collaborative ontology curation and reasoning scenarios.

Each agent has:
  - a *role* (e.g. "curator", "validator", "analyst") that biases its behaviour;
  - a *tool set* built from the editor + reasoner (query, add, update, delete,
    reason);
  - an optional LLM for natural-language turns (falls back to deterministic
    rules if no LLM is available).

Agents communicate via a shared message board (:class:`MessageBoard`) so that
one agent can request an action and another can fulfil it.

This is intentionally dependency-free (no external agent framework) to keep the
example runnable everywhere.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from .ontology_editor import OntologyEditor
from .ontology_loader import OntologyIndex
from .symbolic_reasoner import SymbolicReasoner, InferenceResult

logger = logging.getLogger("ontology_gen.reasoning.agent")


# ============================================================
# Message board
# ============================================================

@dataclass
class Message:
    sender: str
    recipient: Optional[str]   # None = broadcast
    content: str
    kind: str = "chat"         # "chat" | "request" | "result" | "system"
    timestamp: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def to_dict(self) -> dict:
        return {
            "sender": self.sender, "recipient": self.recipient,
            "content": self.content, "kind": self.kind,
            "timestamp": self.timestamp,
        }


class MessageBoard:
    """A simple append-only message bus shared by all agents."""

    def __init__(self) -> None:
        self._messages: list[Message] = []

    def post(self, msg: Message) -> None:
        self._messages.append(msg)
        tgt = msg.recipient or "ALL"
        logger.info("[board] %s -> %s: %s", msg.sender, tgt, msg.content)

    def history(self) -> list[Message]:
        return list(self._messages)

    def messages_for(self, agent_name: str) -> list[Message]:
        return [m for m in self._messages
                if m.recipient in (agent_name, None)]


# ============================================================
# Agent
# ============================================================

class OntologyAgent:
    """An agent that can query and mutate a shared ontology.

    Parameters
    ----------
    name : str
        Human-readable agent name.
    role : str
        One of "curator" (adds/edits concepts), "validator" (checks
        consistency, deletes invalid entries), "analyst" (read-only reasoning).
        Defaults to "analyst".
    editor : OntologyEditor
        The shared editor. All agents in a team must share the same instance.
    """

    def __init__(self, name: str, role: str, editor: OntologyEditor,
                 board: Optional[MessageBoard] = None):
        self.name = name
        self.role = role
        self.editor = editor
        self.reasoner = SymbolicReasoner(editor.idx)
        self.board = board or MessageBoard()
        self._tools: dict[str, Callable[..., Any]] = self._build_tools()

    # ------------------------------------------------------------------
    # tool registry
    # ------------------------------------------------------------------
    def _build_tools(self) -> dict[str, Callable[..., Any]]:
        tools: dict[str, Callable[..., Any]] = {
            "query_concept": self._tool_query_concept,
            "query_relations": self._tool_query_relations,
            "reason_is_a": self._tool_reason_is_a,
            "find_paths": self._tool_find_paths,
        }
        # curator & validator can mutate
        if self.role in ("curator", "validator"):
            tools.update({
                "add_concept": self._tool_add_concept,
                "add_relation": self._tool_add_relation,
                "add_subclass": self._tool_add_subclass,
                "update_concept": self._tool_update_concept,
                "delete_concept": self._tool_delete_concept,
            })
        return tools

    @property
    def tools(self) -> list[str]:
        return list(self._tools.keys())

    # ------------------------------------------------------------------
    # messaging
    # ------------------------------------------------------------------
    def say(self, content: str, *, recipient: Optional[str] = None,
            kind: str = "chat") -> None:
        self.board.post(Message(sender=self.name, recipient=recipient,
                                content=content, kind=kind))

    def listen(self) -> list[Message]:
        return self.board.messages_for(self.name)

    # ------------------------------------------------------------------
    # tool implementations
    # ------------------------------------------------------------------
    def _tool_query_concept(self, ref: str) -> dict:
        c = self.editor.get_concept(ref)
        if not c:
            return {"found": False, "ref": ref}
        # enrich with inherited relations
        cid = c["id"]
        rels = self.editor.idx.get_relations_of(cid, include_inherited=True)
        return {
            "found": True,
            "concept": c,
            "inherited_relation_count": len(rels),
            "relation_names": [r.get("name") for r in rels[:10]],
        }

    def _tool_query_relations(self, ref: str) -> list[dict]:
        cid = self.editor.idx.resolve_concept_id(ref)
        if not cid:
            return []
        rels = self.editor.idx.get_relations_of(cid, include_inherited=True)
        return [{"name": r.get("name"),
                 "domain": self.editor.idx.concept_name(r.get("domain_concept_id", "")),
                 "range": self.editor.idx.concept_name(r.get("range_concept_id", ""))}
                for r in rels]

    def _tool_reason_is_a(self, child: str, parent: str) -> dict:
        res: InferenceResult = self.reasoner.is_a(child, parent)
        return {"answer": res.answer, "found": res.found,
                "proof_steps": len(res.proof_chain)}

    def _tool_find_paths(self, src: str, dst: str, max_hops: int = 4) -> dict:
        res = self.reasoner.find_paths(src, dst, max_hops=max_hops)
        return {"answer": res.answer, "found": res.found,
                "path_count": len(res.proof_chain)}

    def _tool_add_concept(self, name: str, layer: str = "data",
                          **kw: Any) -> dict:
        cid = self.editor.add_concept(name=name, layer=layer, **kw)
        return {"created": True, "id": cid, "name": name}

    def _tool_add_relation(self, name: str, domain: str, range_: str,
                           **kw: Any) -> dict:
        rid = self.editor.add_relation(name, domain, range_, **kw)
        return {"created": True, "id": rid, "name": name}

    def _tool_add_subclass(self, child: str, parent: str) -> dict:
        ax_id = self.editor.add_subclass_axiom(child, parent)
        return {"created": True, "axiom_id": ax_id}

    def _tool_update_concept(self, ref: str, **fields: Any) -> dict:
        ok = self.editor.update_concept(ref, **fields)
        return {"updated": ok, "ref": ref}

    def _tool_delete_concept(self, ref: str) -> dict:
        ok = self.editor.delete_concept(ref)
        return {"deleted": ok, "ref": ref}

    # ------------------------------------------------------------------
    # dispatch
    # ------------------------------------------------------------------
    def call_tool(self, tool_name: str, **kwargs: Any) -> Any:
        """Invoke a registered tool by name."""
        fn = self._tools.get(tool_name)
        if not fn:
            raise ValueError(f"Agent '{self.name}' has no tool '{tool_name}'. "
                             f"Available: {self.tools}")
        logger.info("[%s] call %s(%s)", self.name, tool_name,
                    ", ".join(f"{k}={v!r}" for k, v in kwargs.items()))
        return fn(**kwargs)


# ============================================================
# Agent team (convenience)
# ============================================================

class AgentTeam:
    """A group of agents sharing one editor and one message board."""

    def __init__(self, editor: OntologyEditor):
        self.editor = editor
        self.board = MessageBoard()
        self.agents: dict[str, OntologyAgent] = {}

    def add_agent(self, name: str, role: str) -> OntologyAgent:
        if name in self.agents:
            raise ValueError(f"Agent '{name}' already exists")
        a = OntologyAgent(name, role, self.editor, self.board)
        self.agents[name] = a
        return a

    def agent(self, name: str) -> OntologyAgent:
        return self.agents[name]

    def transcript(self) -> list[str]:
        return [f"[{m.sender}->{m.recipient or 'ALL'}] {m.content}"
                for m in self.board.history()]
