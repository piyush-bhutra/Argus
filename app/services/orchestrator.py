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
            attacks_str = f", attacks {arg.attacks[0]}" if arg.attacks else ""
            lines.append(f"[{arg.id}] {arg.agent} (Round {arg.round}{attacks_str}): {arg.text}")
        transcript_text = "\n".join(lines)
    
    prompt = f"""Claim: {claim}

Transcript so far:
{transcript_text}

Respond with exactly one JSON object representing your next move.
Shape:
{{
  "argument_text": "your argument here",
  "attacks_argument_id": "id of the argument you are attacking or null",
  "confidence": 0.9,
  "concede": false
}}
"""
    if retrying:
        prompt += "\nIMPORTANT: Your previous response could not be parsed. Return ONLY valid JSON, with absolutely no other text, markdown formatting, or prose."
        
    return prompt

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
                        
                    argument_text = data.get("argument_text", "")
                    attacks_argument_id = data.get("attacks_argument_id")
                    confidence = data.get("confidence", 0.5)
                    
                    try:
                        confidence = float(confidence)
                    except (ValueError, TypeError):
                        confidence = 0.5
                    
                    # Validate confidence is a float in [0,1] — clamp it
                    confidence = max(0.0, min(1.0, confidence))
                    
                    attacks = []
                    if attacks_argument_id is not None and str(attacks_argument_id).strip() and str(attacks_argument_id).strip() != "null":
                        attacks = [str(attacks_argument_id)]
                        
                    arg = Argument(
                        id=f"arg_{arg_counter}",
                        agent=agent,
                        round=round_num,
                        text=str(argument_text),
                        attacks=attacks,
                        self_confidence=confidence
                    )
                    transcript.append(arg)
                    arg_counter += 1
                    if on_argument is not None:
                        try:
                            on_argument(transcript)
                        except Exception as cb_err:  # noqa: BLE001
                            logger.warning(f"on_argument callback failed: {cb_err}")
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
