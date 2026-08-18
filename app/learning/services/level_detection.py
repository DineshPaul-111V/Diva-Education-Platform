from typing import List, Dict

TIER_ORDER = ["Beginner", "Intermediate", "Advanced", "Pro"]

def detect_student_level(graded_questions: List[Dict[str, any]]) -> str:
    """
    Deterministically computes the student's starting placement level from graded diagnostic questions.
    Enforces the core rule: student's level = highest tier where they score >= 70%
    AND all lower tiers also scored >= 70%.
    Failing Beginner questions guarantees "Beginner" level regardless of performance on harder questions.
    Each graded question dict should look like: {"tier": "Beginner", "correct": True/False}
    """
    tier_scores = {
        "Beginner": {"correct": 0, "total": 0},
        "Intermediate": {"correct": 0, "total": 0},
        "Advanced": {"correct": 0, "total": 0},
        "Pro": {"correct": 0, "total": 0}
    }
    
    for q in graded_questions:
        tier = q.get("tier")
        if tier in tier_scores:
            tier_scores[tier]["total"] += 1
            if q.get("correct"):
                tier_scores[tier]["correct"] += 1
                
    detected = "Beginner"
    for tier in TIER_ORDER:
        stats = tier_scores[tier]
        if stats["total"] == 0:
            continue
        pct = (stats["correct"] / stats["total"]) * 100
        if pct >= 70:
            detected = tier
        else:
            break # Stop climbing at the first tier they fail
            
    return detected
