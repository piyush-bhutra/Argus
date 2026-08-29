import math
from app.models.schemas import Argument, FactCheckResult
from sklearn.isotonic import IsotonicRegression

STRUCTURAL_WEIGHT = 1.0
FACTCHECK_WEIGHT = 1.0
CONFIDENCE_WEIGHT = 0.5

def sigmoid(x: float) -> float:
    return 1.0 / (1.0 + math.exp(-x))

def compute_raw_probability(
    grounded_extension: dict[str, list[str]],
    fact_check_results: list[FactCheckResult],
    arguments: list[Argument],
) -> float:
    survivors_advocate = grounded_extension.get("advocate", [])
    survivors_skeptic = grounded_extension.get("skeptic", [])
    structural_signal = len(survivors_advocate) - len(survivors_skeptic)

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
        STRUCTURAL_WEIGHT * structural_signal +
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
