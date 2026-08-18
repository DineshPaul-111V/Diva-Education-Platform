from app.learning.services.llm import call_llm
from app.learning.services.prompts import SKILL_MAP_PROMPT
from app.learning.services.schemas import SkillMapResponse

def generate_skill_map(domain: str) -> SkillMapResponse:
    prompt = SKILL_MAP_PROMPT(domain)
    return call_llm(prompt, SkillMapResponse, model_type="fast")
