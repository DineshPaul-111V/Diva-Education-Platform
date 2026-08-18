from app.learning.services.llm import call_llm
from app.learning.services.prompts import DIAGNOSTIC_PROMPT
from app.learning.services.schemas import DiagnosticResponse

def generate_diagnostic(domain: str, skill_map: dict) -> DiagnosticResponse:
    prompt = DIAGNOSTIC_PROMPT(domain, skill_map)
    return call_llm(prompt, DiagnosticResponse, model_type="fast")
