"""
api/services/emotion_service.py
────────────────────────────────
Pure-logic emotional state engine.

No database, no Redis, no LLM calls. Every function is deterministic and
fully unit-testable in isolation.

Responsibilities:
  1. apply_delta  — add a NPCStateDelta to a NPCEmotionalState, clamp to [0.0, 1.0]
  2. classify_behaviour — map an NPCEmotionalState to a NPCBehaviour via
                          a priority-ordered rule table

Behaviour classification rules (first match wins):
  ┌─────────────────────────────────────────────┬─────────────┐
  │ Condition                                   │ Behaviour   │
  ├─────────────────────────────────────────────┼─────────────┤
  │ stress ≥ 0.85                               │ confessing  │
  │ stress > 0.70  AND  trust < 0.20            │ hostile     │
  │ stress > 0.50  AND  trust < 0.40            │ nervous     │
  │ suspicion > 0.50  AND  stress < 0.70        │ deflecting  │
  │ (always)                                    │ cooperative │
  └─────────────────────────────────────────────┴─────────────┘

The `cooperative` catch-all guarantees `classify_behaviour` always
returns a valid enum value — it can never return None.
"""

from __future__ import annotations

from typing import Callable

from api.schemas.npc import NPCBehaviour, NPCEmotionalState, NPCStateDelta


class EmotionService:
    """
    Stateless service for NPC emotional state transitions.

    Instantiate once at module level (or per-request — it carries no state).
    All methods are synchronous; no awaiting required.
    """

    # ── Behaviour classification rule table ────────────────────────────────────
    # Each entry is (predicate, behaviour_string).
    # Evaluated top-to-bottom; the FIRST matching predicate wins.
    # The final entry is an unconditional catch-all — the list is exhaustive.
    #
    # Using a list of (Callable, str) rather than if/elif chains makes it
    # trivial to add, reorder, or A/B test rules without touching logic.

    BEHAVIOUR_RULES: list[tuple[Callable[[NPCEmotionalState], bool], str]] = [
        (lambda s: s.stress >= 0.85,                         "confessing"),
        (lambda s: s.stress > 0.70 and s.trust < 0.20,       "hostile"),
        (lambda s: s.stress > 0.50 and s.trust < 0.40,       "nervous"),
        (lambda s: s.suspicion > 0.50 and s.stress < 0.70,   "deflecting"),
        (lambda s: True,                                       "cooperative"),
    ]

    # ── Public API ─────────────────────────────────────────────────────────────

    def apply_delta(
        self,
        current: NPCEmotionalState,
        delta: NPCStateDelta,
    ) -> NPCEmotionalState:
        """
        Add `delta` to `current` and clamp every dimension to [0.0, 1.0].

        Returns a NEW NPCEmotionalState — both inputs are immutable (frozen=True).

        Examples:
            current = NPCEmotionalState(stress=0.7)
            delta   = NPCStateDelta(stress=0.2, trust=-0.1)
            result  → NPCEmotionalState(stress=0.9, trust=0.4, ...)

            current = NPCEmotionalState(stress=0.95)
            delta   = NPCStateDelta(stress=0.2)
            result  → NPCEmotionalState(stress=1.0, ...)  ← clamped
        """
        return NPCEmotionalState(
            stress=self._clamp(current.stress + delta.stress),
            trust=self._clamp(current.trust + delta.trust),
            suspicion=self._clamp(current.suspicion + delta.suspicion),
            cooperation=self._clamp(current.cooperation + delta.cooperation),
        )

    def classify_behaviour(self, state: NPCEmotionalState) -> NPCBehaviour:
        """
        Return the NPCBehaviour that matches the given emotional state.

        Evaluates BEHAVIOUR_RULES in order; returns on the first match.
        The final catch-all rule (lambda s: True) guarantees this function
        always returns a value — it never returns None.

        Args:
            state: Current NPCEmotionalState after apply_delta.

        Returns:
            The matching NPCBehaviour enum member.
        """
        for condition, behaviour_str in self.BEHAVIOUR_RULES:
            if condition(state):
                return NPCBehaviour(behaviour_str)

        # Unreachable: the catch-all rule always matches.
        # Included for static analysis / mypy completeness.
        return NPCBehaviour.cooperative  # pragma: no cover

    # ── Private helpers ────────────────────────────────────────────────────────

    @staticmethod
    def _clamp(value: float) -> float:
        """Clamp a float to the inclusive range [0.0, 1.0]."""
        return max(0.0, min(1.0, value))

    # ── Convenience method ─────────────────────────────────────────────────────

    def step(
        self,
        current: NPCEmotionalState,
        delta: NPCStateDelta,
    ) -> tuple[NPCEmotionalState, NPCBehaviour]:
        """
        Convenience: apply_delta + classify_behaviour in one call.

        Returns (new_state, new_behaviour).
        Used by npc_service.interact() to reduce boilerplate.
        """
        new_state = self.apply_delta(current, delta)
        new_behaviour = self.classify_behaviour(new_state)
        return new_state, new_behaviour


# ── Module-level singleton ─────────────────────────────────────────────────────
# Stateless — safe to share across all requests without locking.
emotion_service = EmotionService()
