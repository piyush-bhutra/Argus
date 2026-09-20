"""
PRD §5a - Debate Orchestrator
"""
import json
from typing import Callable, List, Optional
from app.core.logger import logger
from app.models.schemas import Argument
from app.services.grok_client import call_grok

# Called after each new argument is appended, with the transcript so far — lets
# the caller stream partial progress (e.g. into the debate store for live polling).
OnArgument = Callable[[List[Argument]], None]

# A turn may put forward several arguments, each free to attack ANY earlier
# argument from the other side. Under the previous protocol — one argument per
# turn, implicitly attacking the last one — every debate produced the same chain,
# so the grounded extension was determined by turn order rather than by argument
# quality and carried no information at all.
MAX_PER_TURN = 3
MAX_ARGUMENTS = 12


def valid_attacks(targets, agent: str, prior: List[Argument]) -> List[str]:
    """Filter asserted attack targets down to the coherent ones.

    Drops anything that is not an existing earlier argument (unknown ids and
    forward references) and anything on the attacker's own side — a side
    dismantling its own case would hand it a free win in the grounded extension.
    Order is preserved and duplicates removed.
    """
    if targets is None:
        return []
    if isinstance(targets, str):
        targets = [targets]
    if not isinstance(targets, (list, tuple)):
        return []

    opposing = {a.id for a in prior if a.agent != agent}
    out = []
    for t in targets:
        if not isinstance(t, str):
            continue
        t = t.strip()
        if t and t in opposing and t not in out:
            out.append(t)
    return out

def _build_system_prompt(agent: str) -> str:
    if agent == "advocate":
        return "You are the Advocate. You argue that the user's claim is TRUE. Respond ONLY with valid JSON in the exact shape requested, with no prose wrapper."
    else:
        return "You are the Skeptic. You argue that the user's claim is FALSE. Respond ONLY with valid JSON in the exact shape requested, with no prose wrapper."

def _build_user_prompt(claim: str, transcript: List[Argument], retrying: bool = False) -> str:
    transcript_text = "None yet."
    if transcript:
        lines = []
        for arg in transcript:
            attacks_str = f", attacks {', '.join(arg.attacks)}" if arg.attacks else ""
            lines.append(f"[{arg.id}] {arg.agent} (Round {arg.round}{attacks_str}): {arg.text}")
        transcript_text = "\n".join(lines)

    prompt = f"""Claim: {claim}

Transcript so far:
{transcript_text}

Respond with exactly one JSON object representing your next move. You may put
forward up to {MAX_PER_TURN} distinct arguments this turn.

Each argument may attack ANY number of the opposing side's earlier arguments —
not only the most recent one. List their ids in "attacks", or use an empty list
if the argument stands on its own rather than rebutting anything. Attacking an
older argument that still stands is usually worth more than restating a reply to
the last thing said.

Shape:
{{
  "concede": false,
  "arguments": [
    {{
      "argument_text": "your argument here",
      "attacks": ["arg_1"],
      "confidence": 0.9
    }}
  ]
}}
"""
    if retrying:
        prompt += "\nIMPORTANT: Your previous response could not be parsed. Return ONLY valid JSON, with absolutely no other text, markdown formatting, or prose."
        
    return prompt

def _confidence(raw) -> float:
    try:
        return max(0.0, min(1.0, float(raw)))
    except (ValueError, TypeError):
        return 0.5


def _turn_arguments(data: dict) -> List[dict]:
    """Turn response -> list of argument dicts, in either supported shape.

    The current shape is {"arguments": [...]}. The single-argument shape
    {"argument_text": ..., "attacks_argument_id": ...} is still accepted: models
    do sometimes ignore the requested shape, and salvaging the response is
    cheaper than burning one of the three retries on it.
    """
    raw = data.get("arguments")
    if isinstance(raw, list):
        moves = [m for m in raw if isinstance(m, dict) and str(m.get("argument_text", "")).strip()]
        return moves

    if str(data.get("argument_text", "")).strip():
        target = data.get("attacks_argument_id")
        return [{
            "argument_text": data["argument_text"],
            "attacks": [] if target in (None, "", "null") else [str(target)],
            "confidence": data.get("confidence", 0.5),
        }]

    return []


def run_debate(
    claim: str,
    rounds: int = 3,
    on_argument: Optional[OnArgument] = None,
) -> List[Argument]:
    """
    Run a debate between Advocate and Skeptic for N rounds.

    If ``on_argument`` is given, it is called after every new argument with the
    transcript so far, so callers can stream progress instead of waiting for the
    whole debate to finish.
    """
    transcript: List[Argument] = []
    arg_counter = 1
    
    for round_num in range(1, rounds + 1):
        round_concedes = {"advocate": False, "skeptic": False}
        
        for agent in ["advocate", "skeptic"]:
            system_prompt = _build_system_prompt(agent)
            conceded_this_turn = False
            
            for attempt in range(3):
                retrying = (attempt > 0)
                user_prompt = _build_user_prompt(claim, transcript, retrying)
                
                response_text = call_grok(user_prompt, system_prompt)
                
                try:
                    cleaned_response = response_text.strip()
                    if cleaned_response.startswith("```json"):
                        cleaned_response = cleaned_response[7:]
                    elif cleaned_response.startswith("```"):
                        cleaned_response = cleaned_response[3:]
                    if cleaned_response.endswith("```"):
                        cleaned_response = cleaned_response[:-3]
                    cleaned_response = cleaned_response.strip()
                    
                    data = json.loads(cleaned_response)
                    
                    if not isinstance(data, dict):
                        raise ValueError("Response is not a JSON object")
                    
                    concede = data.get("concede", False)
                    if concede:
                        conceded_this_turn = True
                        break

                    moves = _turn_arguments(data)[:MAX_PER_TURN]
                    if not moves:
                        # Nothing usable this turn is a concession in substance.
                        conceded_this_turn = True
                        break

                    added = 0
                    for move in moves:
                        if len(transcript) >= MAX_ARGUMENTS:
                            logger.warning(
                                f"argument cap ({MAX_ARGUMENTS}) reached; dropping "
                                f"the rest of {agent}'s round-{round_num} turn"
                            )
                            break

                        arg = Argument(
                            id=f"arg_{arg_counter}",
                            agent=agent,
                            round=round_num,
                            text=str(move.get("argument_text", "")),
                            # Validated against the transcript as it stands, so an
                            # argument in this same turn cannot attack its sibling.
                            attacks=valid_attacks(move.get("attacks"), agent, transcript),
                            self_confidence=_confidence(move.get("confidence")),
                        )
                        transcript.append(arg)
                        arg_counter += 1
                        added += 1
                        if on_argument is not None:
                            try:
                                on_argument(transcript)
                            except Exception as cb_err:  # noqa: BLE001
                                logger.warning(f"on_argument callback failed: {cb_err}")

                    if not added:
                        conceded_this_turn = True
                    break
                    
                except Exception as e:
                    logger.warning(f"Failed to parse LLM response on attempt {attempt + 1}: {e}")
                    if attempt == 2:
                        conceded_this_turn = True
                        logger.warning(f"{agent} exhausted retries. Treating as concede.")

            if conceded_this_turn:
                round_concedes[agent] = True
                opponent = "skeptic" if agent == "advocate" else "advocate"
                opponent_spoke = any(a.agent == opponent for a in transcript)

                # Guarantee at least one full round: never terminate in round 1
                # before the opponent has even had its opening turn. "Opponent has
                # zero arguments so far" in round 1 means "hasn't gone yet", not
                # "has nothing left to say".
                if round_num == 1 and not opponent_spoke:
                    continue

                # From here on, end early only on mutual concession in the same
                # round — neither side has anything new to add.
                if round_concedes[opponent]:
                    return transcript

    return transcript
