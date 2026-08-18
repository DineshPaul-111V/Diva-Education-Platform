from app.learning.services.llm import call_llm
from app.learning.services.prompts import REMEDIATION_PROMPT, RETRY_QUIZ_PROMPT
from app.learning.services.schemas import RemediationResponse, RetryQuizResponse

def generate_remediation(topic: str, wrong_answers: str) -> RemediationResponse:
    prompt = REMEDIATION_PROMPT(topic, wrong_answers)
    return call_llm(prompt, RemediationResponse)

def generate_retry_quiz(topic: str, user_level: str, lesson_content_markdown: str, remediation_summary: str) -> RetryQuizResponse:
    prompt = RETRY_QUIZ_PROMPT(topic, user_level, lesson_content_markdown, remediation_summary)
    return call_llm(prompt, RetryQuizResponse)
