import logging
import uuid
from app.learning.services.llm import call_llm
from app.learning.services.prompts import ROADMAP_PROMPT
from app.learning.services.schemas import RoadmapResponse, KnowledgeGraphNode, ModuleItem, LessonItem

logger = logging.getLogger(__name__)

def synthesize_fallback_roadmap(domain: str, skill_map_dict: dict, detected_level: str, misconceptions: list) -> RoadmapResponse:
    """
    Deterministic synthesis fallback for when LLM generation is unavailable or rate-limited.
    Constructs a fully conforming, tailored curriculum roadmap from the domain skill map.
    """
    level_order = ["Beginner", "Intermediate", "Advanced", "Pro"]
    start_level = detected_level if detected_level in level_order else "Beginner"
    start_idx = level_order.index(start_level)
    
    # Extract skill tiers
    tiers_map = {}
    for tier_data in skill_map_dict.get("skillMap", []):
        t_name = tier_data.get("tier", "Beginner")
        tiers_map[t_name] = tier_data.get("skills", [])
        
    kg_nodes = []
    modules = []
    
    # Map misconceptions by skillId
    misc_by_skill = {}
    for m in (misconceptions or []):
        s_id = m.get("skillId")
        if s_id:
            misc_by_skill.setdefault(s_id, []).append(m.get("misconceptionText", "Needs reinforcement"))
            
    # Build modules and KG nodes based on student level rules
    for idx, tier_name in enumerate(level_order):
        skills_in_tier = tiers_map.get(tier_name, [])
        if not skills_in_tier:
            continue
            
        is_revision = idx < start_idx
        
        # Build lessons
        lessons = []
        for s in skills_in_tier:
            s_id = s.get("skillId") or f"skill_{uuid.uuid4().hex[:6]}"
            s_name = s.get("name") or s.get("title") or "Core Topic"
            
            lessons.append(LessonItem(
                id=s_id,
                title=s_name,
                estimatedMinutes=35 if is_revision else 50,
                targetSkillId=s_id
            ))
            
            kg_nodes.append(KnowledgeGraphNode(
                nodeId=s_id,
                skillId=s_id,
                label=s_name,
                tier=tier_name,
                isRevisionModule=is_revision,
                prerequisites=s.get("prerequisiteSkillIds", []),
                initialMastery=0.7 if is_revision else 0.0,
                linkedMisconceptions=misc_by_skill.get(s_id, [])
            ))
            
        mod_title = f"{tier_name} Revision" if is_revision else f"{tier_name} Competencies"
        mod_desc = (
            f"Accelerated review of {tier_name} fundamentals tailored to your placement results."
            if is_revision
            else f"Comprehensive hands-on mastery of {tier_name} level {domain} topics."
        )
        
        modules.append(ModuleItem(
            id=f"mod_{tier_name.lower()}_{'rev' if is_revision else 'full'}",
            title=mod_title,
            tier=tier_name,
            isRevision=is_revision,
            description=mod_desc,
            lessons=lessons
        ))
        
    return RoadmapResponse(
        domain=domain,
        detectedLevel=detected_level,
        knowledgeGraph=kg_nodes,
        modules=modules
    )

def generate_roadmap(domain: str, skill_map_dict: dict, detected_level: str, misconceptions: list) -> RoadmapResponse:
    # Prune skill map to reduce prompt tokens and protect against Groq TPM rate limits
    pruned_skills = []
    for tier_data in skill_map_dict.get("skillMap", []):
        pruned_tier = {
            "tier": tier_data.get("tier"),
            "skills": [
                {
                    "skillId": s.get("skillId"),
                    "name": s.get("name")
                }
                for s in tier_data.get("skills", [])
            ]
        }
        pruned_skills.append(pruned_tier)
        
    pruned_map = {
        "domain": domain,
        "skillMap": pruned_skills
    }
    
    prompt = ROADMAP_PROMPT(domain, pruned_map, detected_level, misconceptions)
    try:
        response = call_llm(prompt, RoadmapResponse, max_tokens=3000)
        
        # Guard against LLM laziness where it outputs a sparse roadmap (e.g., 1 module, 1 lesson)
        total_lessons = sum(len(m.lessons) for m in response.modules)
        total_skills = sum(len(tier.get("skills", [])) for tier in skill_map_dict.get("skillMap", []))
        
        if total_lessons < (total_skills * 0.5) or len(response.modules) < 3:
            logger.warning(f"LLM generated a sparse roadmap ({len(response.modules)} modules, {total_lessons} lessons for {total_skills} skills). Forcing deterministic fallback.")
            raise ValueError("Sparse/lazy roadmap generation detected")
            
        return response
    except Exception as e:
        logger.warning("LLM roadmap generation encountered error (%s). Synthesizing tailored curriculum fallback...", e)
        return synthesize_fallback_roadmap(domain, skill_map_dict, detected_level, misconceptions)
