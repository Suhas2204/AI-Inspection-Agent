"""Compatibility shim: the LLM front end moved to inspection.orchestrator.

Re-exports the implementation, which is now in inspection/, private names
included: test_orchestrator_llm.py imports _wire_tools, _wire_messages and
_arguments_for, and test_agent_loop.py imports _is_reading.

No __main__ here: this module never had one. `python -m redlining.session
--agent` is how the orchestrator is driven.
"""

from __future__ import annotations

from .inspection.orchestrator import (  # noqa: F401
    ABSORBS_EXTRA_ARGS,
    ANSWER_KEYS,
    CLARIFY,
    LLM,
    LLM_API_KEY,
    LLM_MODEL,
    LLM_TEMPERATURE,
    LLM_TIMEOUT_S,
    LLM_URL,
    LlamaCppLLM,
    MockLLM,
    Orchestrator,
    PROMPT_VERSION,
    REDACTED,
    Reply,
    SECRET_KEYS,
    SYSTEM_PROMPT,
    TOOLS,
    TOOL_NAMES,
    ToolCall,
    VERDICT_KEYS,
    _COUNT_LABELS,
    _INTENTS,
    _OneReading,
    _SIGN_WORDS,
    _WORDS,
    _arguments_for,
    _is_reading,
    _scrub,
    _wire_messages,
    _wire_tools,
    redact,
    secrets_of,
)

__all__ = [
    "ABSORBS_EXTRA_ARGS", "ANSWER_KEYS", "CLARIFY", "LLM", "LLM_API_KEY",
    "LLM_MODEL", "LLM_TEMPERATURE", "LLM_TIMEOUT_S", "LLM_URL",
    "LlamaCppLLM", "MockLLM", "Orchestrator", "PROMPT_VERSION", "REDACTED",
    "Reply", "SECRET_KEYS", "SYSTEM_PROMPT", "TOOLS", "TOOL_NAMES",
    "ToolCall", "VERDICT_KEYS", "redact", "secrets_of",
]
