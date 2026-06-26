import asyncio
import sys
import logging
from typing import Dict, Any

from api.services.llm.factory import get_llm_provider
from api.services.llm.base import LLMResponse

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("eval_live_llm")

# A realistic representation of Marcus Webb
SYSTEM_PROMPT = """You are Marcus Webb, a character in an interrogation game.

PERSONALITY TRAITS: calculated, defensive, prideful
MOTIVATION: Protect his brother
FEAR: Going back to prison
BACKGROUND: Ex-con who got pulled back into the underworld.
SPEECH STYLE: clipped, guarded, occasionally sarcastic

CURRENT EMOTIONAL STATE:
  Stress:      0.20  (0=calm, 1=breaking)
  Trust:       0.20  (0=hostile, 1=open)
  Suspicion:   0.60  (0=unsuspicious, 1=paranoid)
  Cooperation: 0.10  (0=stonewalling, 1=fully cooperative)

CURRENT BEHAVIOUR MODE: DEFLECTING
PHYSICAL/VERBAL TELL: avoiding eye contact, answering with questions
Your response must be consistent with these observable signals.

PRIVATE CONTEXT (you know this — do NOT reveal unless forced):
  - I buried the money behind the old sawmill.
    (Reveal only if: confronted with concrete proof about the shovel receipt)

INTERACTION RULES:
- Never break character.
- Keep responses under 50 words.
"""

GOLDEN_SET = [
    {
        "name": "Friendly Greeting",
        "message": "Hey Marcus, just want to talk. No pressure.",
        "expected_deltas": {
            "trust": lambda d: d > 0,          # Trust should increase
            "stress": lambda d: d < 0 or d == 0 # Stress shouldn't spike
        }
    },
    {
        "name": "Hostile Accusation",
        "message": "I know you stole the money, you liar. Tell me where it is or I lock you up.",
        "expected_deltas": {
            "stress": lambda d: d > 0,         # Stress should increase
            "cooperation": lambda d: d < 0,    # Cooperation should decrease
        }
    },
    {
        "name": "Manipulative Probe (Brother)",
        "message": "I can make sure your brother stays safe. But you need to help me.",
        "expected_deltas": {
            "suspicion": lambda d: d > 0,      # Suspicion should increase (he's calculated/defensive)
        }
    }
]

async def run_evals():
    provider = get_llm_provider()
    logger.info(f"Running evals against LIVE provider: {provider.__class__.__name__}")
    
    passed = 0
    failed = 0

    for test in GOLDEN_SET:
        name = test["name"]
        message = test["message"]
        expected_deltas = test["expected_deltas"]

        logger.info(f"\\n--- Running Eval: {name} ---")
        logger.info(f"User: {message}")
        
        try:
            response: LLMResponse = await provider.complete(SYSTEM_PROMPT, message)
        except Exception as e:
            logger.error(f"❌ Exception calling provider: {e}")
            failed += 1
            continue

        if not response.is_valid:
            logger.error(f"❌ Failed to parse JSON or timed out. Raw content: {response.raw_content}")
            failed += 1
            continue
            
        logger.info(f"Response: {response.npc_response}")
        logger.info(f"Deltas: stress={response.state_delta.stress}, trust={response.state_delta.trust}, "
                    f"susp={response.state_delta.suspicion}, coop={response.state_delta.cooperation}")
        
        # Verify deltas
        test_passed = True
        delta_dict = {
            "stress": response.state_delta.stress,
            "trust": response.state_delta.trust,
            "suspicion": response.state_delta.suspicion,
            "cooperation": response.state_delta.cooperation,
        }
        
        for metric, validator in expected_deltas.items():
            val = delta_dict[metric]
            if not validator(val):
                logger.error(f"❌ Failed metric check: {metric} delta was {val}, which violates expectations.")
                test_passed = False
                
        if test_passed:
            logger.info("✅ PASS")
            passed += 1
        else:
            failed += 1
            
    logger.info(f"\\n=== EVALUATION COMPLETE ===")
    logger.info(f"Total: {len(GOLDEN_SET)} | Passed: {passed} | Failed: {failed}")
    
    if failed > 0:
        sys.exit(1)

if __name__ == "__main__":
    asyncio.run(run_evals())
