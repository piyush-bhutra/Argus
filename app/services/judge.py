import math
from app.models.schemas import Argument, FactCheckResult
from sklearn.isotonic import IsotonicRegression

# All three signals are normalised to [-1, 1], so equal weights mean equal
# influence. Chosen on principle rather than fitted: picking the argmax over the
# evaluation set would be fitting on it. The weight sweep in the eval harness is
# reported as a sensitivity analysis, not used to select these.
STRUCTURAL_WEIGHT = 1.0
FACTCHECK_WEIGHT = 1.0
CONFIDENCE_WEIGHT = 0.5

_EPSILON = 1e-9

def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))


def structural_signal(
    grounded_extension: dict[str, list[str]],
    fact_check_results: list[FactCheckResult],
    mode: str = "weighted",
) -> float:
    """Surviving arguments weighted by their evidence support, in [-1, 1].

    Previously this was ``len(advocate) - len(skeptic)``, a raw count. Two
    defects followed. It was unbounded while the other signals sat in [-1, 1], so
    one extra survivor swung the logit by a full e-fold. And in a strictly
    alternating debate the last speaker is never attacked and therefore always
    survives, handing that side a permanent bonus for reasons of schedule.

    Weighting by evidence fixes both. The term is now bounded like the others,
    and an argument that survived on turn order with nothing behind it scores
    zero rather than a full point. Note the sign handling: a survivor whose
    evidence CONTRADICTS it counts against its own side, so the numerator uses
    signed support.

    The denominator is the SURVIVOR COUNT, not the total support magnitude.
    Normalising by magnitude would make the term purely relative: a single
    survivor backed by support 0.01 would score a full -1.0, which is the same
    "maximal signal from nothing" failure this function exists to remove. Divided
    by count, the term tracks absolute evidence strength and still cannot leave
    [-1, 1], since every support already lies there.

    ``mode="count"`` restores the original unweighted survivor difference. It
    exists only so the ablation can reproduce the bug deliberately and show that
    it was the bug; nothing in the live pipeline uses it.
    """
    adv_ids = grounded_extension.get("advocate", [])
    skp_ids = grounded_extension.get("skeptic", [])

    if mode == "count":
        return float(len(adv_ids) - len(skp_ids))

    support = {r.argument_id: r.support_score for r in fact_check_results}
    advocate = [support.get(i, 0.0) for i in adv_ids]
    skeptic = [support.get(i, 0.0) for i in skp_ids]

    n_survivors = len(advocate) + len(skeptic)
    if not n_survivors:
        return 0.0
    return (sum(advocate) - sum(skeptic)) / n_survivors

def compute_raw_probability(
    grounded_extension: dict[str, list[str]],
    fact_check_results: list[FactCheckResult],
    arguments: list[Argument],
) -> float:
    structural = structural_signal(grounded_extension, fact_check_results)

    fact_check_dict = {fc.argument_id: fc.support_score for fc in fact_check_results}
    
    adv_fc_scores = []
    skp_fc_scores = []
    
    arg_side_map = {arg.id: arg.agent for arg in arguments}
    
    for arg_id, score in fact_check_dict.items():
        agent = arg_side_map.get(arg_id)
        if agent == "advocate":
            adv_fc_scores.append(score)
        elif agent == "skeptic":
            skp_fc_scores.append(score)
            
    adv_fc_avg = sum(adv_fc_scores) / len(adv_fc_scores) if adv_fc_scores else 0.0
    skp_fc_avg = sum(skp_fc_scores) / len(skp_fc_scores) if skp_fc_scores else 0.0
    
    factcheck_signal = adv_fc_avg - skp_fc_avg

    adv_conf_scores = [arg.self_confidence for arg in arguments if arg.agent == "advocate"]
    skp_conf_scores = [arg.self_confidence for arg in arguments if arg.agent == "skeptic"]
    
    adv_conf_avg = sum(adv_conf_scores) / len(adv_conf_scores) if adv_conf_scores else 0.0
    skp_conf_avg = sum(skp_conf_scores) / len(skp_conf_scores) if skp_conf_scores else 0.0
    
    confidence_signal = adv_conf_avg - skp_conf_avg
    
    raw_probability = sigmoid(
        STRUCTURAL_WEIGHT * structural +
        FACTCHECK_WEIGHT * factcheck_signal +
        CONFIDENCE_WEIGHT * confidence_signal
    )
    
    return raw_probability

def fit_calibrator(raw_probabilities: list[float], true_labels: list[bool]):
    iso_reg = IsotonicRegression(out_of_bounds="clip")
    iso_reg.fit(raw_probabilities, [1 if label else 0 for label in true_labels])
    return iso_reg

def apply_calibration(calibrator, raw_probability: float) -> float:
    pred = calibrator.predict([raw_probability])
    return float(pred[0])
