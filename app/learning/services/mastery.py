def get_expected_index(q: dict) -> int:
    correct_idx = q.get("correctIndex")
    if isinstance(correct_idx, int):
        return correct_idx
    correct_ans = q.get("correctAnswer")
    if isinstance(correct_ans, int):
        return correct_ans
    
    # Check alternate keys
    for alt_key in ["correct_index", "correct_answer", "answerIndex"]:
        val = q.get(alt_key)
        if isinstance(val, int):
            return val
        if isinstance(val, str):
            try:
                return int(val)
            except ValueError:
                pass
    return 0

def evaluate_quiz_submission(quiz: list, answers: list) -> dict:
    """
    Evaluates a quiz submission on the server side against the authoritative quiz key.
    Never trust a client-submitted score.
    """
    total = len(quiz)
    if total == 0:
        return {
            "score": 0,
            "passed": False,
            "correctCount": 0,
            "totalQuestions": 0,
            "wrongAnswers": []
        }
        
    correct_count = 0
    wrong_answers = []
    
    for q in quiz:
        q_id = q.get("id")
        user_ans = next((a for a in answers if a.get("id") == q_id), None)
        expected = get_expected_index(q)
        
        is_correct = user_ans is not None and user_ans.get("selectedIndex") == expected
        
        if is_correct:
            correct_count += 1
        else:
            wrong_answers.append({
                "question": q,
                "given": user_ans.get("selectedIndex") if user_ans else None,
                "testedSkill": q.get("testedSkill") or q.get("subtopicId")
            })
            
    score = round((correct_count / total) * 100)
    passed = score >= 70.0 # MASTERY_THRESHOLD is 70%
    
    return {
        "score": score,
        "passed": passed,
        "correctCount": correct_count,
        "totalQuestions": total,
        "wrongAnswers": wrong_answers
    }
