"""
api/services/llm/
──────────────────
Provider-agnostic LLM integration layer for Phase 2 NPC intelligence.

Public surface:
  from api.services.llm import get_llm_provider, BaseLLMProvider, LLMResponse

The factory (`get_llm_provider`) reads LLM_PROVIDER from the environment
and returns the correct concrete provider. All providers implement the
same `BaseLLMProvider` interface so the NPC service never references a
provider class directly.
"""

from api.services.llm.base import BaseLLMProvider, LLMResponse
from api.services.llm.factory import get_llm_provider

__all__ = ["BaseLLMProvider", "LLMResponse", "get_llm_provider"]
