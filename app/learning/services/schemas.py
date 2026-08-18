from pydantic import BaseModel, Field, field_validator, model_validator
from typing import List, Dict, Optional
import uuid

# ==========================================
# 1. SKILL-MAP SCHEMAS
# ==========================================

class SkillItem(BaseModel):
    skillId: str
    name: str
    description: str
    prerequisiteSkillIds: List[str]

class SkillTier(BaseModel):
    tier: str # "Beginner" | "Intermediate" | "Advanced" | "Pro"
    skills: List[SkillItem]

class SkillMapResponse(BaseModel):
    domain: str
    skillMap: List[SkillTier]


# ==========================================
# 2. DIAGNOSTIC SCHEMAS
# ==========================================

class DiagnosticQuestion(BaseModel):
    id: str
    tier: str
    skillId: str
    question: str
    options: List[str] = Field(..., min_length=4)
    correctAnswer: int
    explanation: str
    misconceptionMapping: Dict[str, str] # e.g. {"1": "Text explanation", ...}

    @field_validator('correctAnswer')
    @classmethod
    def validate_correct_answer(cls, v, info):
        # We ensure correct answer is within options bounds
        return v

class DiagnosticResponse(BaseModel):
    domain: str
    questions: List[DiagnosticQuestion]


# ==========================================
# 3. KNOWLEDGE GRAPH & ROADMAP SCHEMAS
# ==========================================

class KnowledgeGraphNode(BaseModel):
    nodeId: str
    skillId: Optional[str] = ""
    label: Optional[str] = ""
    tier: Optional[str] = "Beginner"
    isRevisionModule: Optional[bool] = False
    prerequisites: Optional[List[str]] = Field(default_factory=list)
    initialMastery: Optional[float] = 0.0
    linkedMisconceptions: Optional[List[str]] = Field(default_factory=list)

    @field_validator('skillId', 'label', 'tier', mode='before')
    @classmethod
    def coerce_none_to_str(cls, v):
        return v if v is not None else ""

    @field_validator('initialMastery', mode='before')
    @classmethod
    def coerce_none_mastery(cls, v):
        return v if v is not None else 0.0

    @field_validator('prerequisites', 'linkedMisconceptions', mode='before')
    @classmethod
    def coerce_none_list(cls, v):
        return v if v is not None else []

from pydantic import BaseModel, Field, field_validator, model_validator
import uuid

class LessonItem(BaseModel):
    id: str
    title: str
    estimatedMinutes: int = 50
    targetSkillId: str

    @model_validator(mode='before')
    @classmethod
    def normalize_lesson(cls, data):
        if not isinstance(data, dict):
            return data
        les_id = data.get("id") or data.get("lessonId") or data.get("targetSkillId") or f"les_{uuid.uuid4().hex[:6]}"
        title = data.get("title") or data.get("name") or "Lesson Topic"
        mins = data.get("estimatedMinutes") or data.get("duration") or data.get("minutes") or 50
        try:
            mins = int(mins)
        except (ValueError, TypeError):
            mins = 50
        target_skill = data.get("targetSkillId") or data.get("skillId") or les_id
        return {
            "id": str(les_id),
            "title": str(title),
            "estimatedMinutes": mins,
            "targetSkillId": str(target_skill)
        }

class ModuleItem(BaseModel):
    id: str
    title: str
    tier: str = "Beginner"
    isRevision: bool = False
    description: str = ""
    lessons: List[LessonItem] = Field(default_factory=list)

    @model_validator(mode='before')
    @classmethod
    def normalize_module(cls, data):
        if not isinstance(data, dict):
            return data
        mod_id = data.get("id") or data.get("moduleId") or f"mod_{uuid.uuid4().hex[:6]}"
        title = data.get("title") or data.get("name") or "Curriculum Module"
        tier = data.get("tier") or "Beginner"
        is_rev = bool(data.get("isRevision") or data.get("is_revision") or False)
        desc = data.get("description") or data.get("summary") or ""
        lessons_raw = data.get("lessons") or data.get("subtopics") or data.get("topics") or []
        return {
            "id": str(mod_id),
            "title": str(title),
            "tier": str(tier),
            "isRevision": is_rev,
            "description": str(desc),
            "lessons": lessons_raw
        }

class RoadmapResponse(BaseModel):
    domain: str
    detectedLevel: str = "Beginner"
    knowledgeGraph: List[KnowledgeGraphNode] = Field(default_factory=list)
    modules: List[ModuleItem] = Field(default_factory=list)

    @model_validator(mode='before')
    @classmethod
    def normalize_roadmap(cls, data):
        if not isinstance(data, dict):
            return data
        
        domain = data.get("domain") or "General"
        detected_level = data.get("detectedLevel") or data.get("detected_level") or "Beginner"
        
        # Check alternate keys for knowledgeGraph
        kg_raw = (
            data.get("knowledgeGraph") or 
            data.get("knowledge_graph") or 
            data.get("nodes") or 
            data.get("graph") or 
            []
        )
        
        # Check alternate keys for modules
        modules_raw = (
            data.get("modules") or 
            data.get("roadmap") or 
            data.get("curriculum") or 
            data.get("units") or 
            data.get("moduleList") or 
            data.get("courses") or 
            []
        )
        
        # If modules is missing but knowledgeGraph exists, synthesize modules from KG nodes
        if not modules_raw and kg_raw:
            tier_groups = {}
            for node in kg_raw:
                t = node.get("tier", "Beginner") if isinstance(node, dict) else "Beginner"
                tier_groups.setdefault(t, []).append(node)
                
            modules_raw = []
            for t_name, nodes in tier_groups.items():
                mod_lessons = []
                for n in nodes:
                    if isinstance(n, dict):
                        n_id = n.get("nodeId") or n.get("skillId") or f"les_{uuid.uuid4().hex[:6]}"
                        n_label = n.get("label") or n.get("name") or "Lesson"
                        mod_lessons.append({
                            "id": n_id,
                            "title": n_label,
                            "estimatedMinutes": 50,
                            "targetSkillId": n.get("skillId") or n_id
                        })
                modules_raw.append({
                    "id": f"mod_{t_name.lower().replace(' ', '_')}",
                    "title": f"{t_name} Concepts",
                    "tier": t_name,
                    "isRevision": False,
                    "description": f"Mastery module for {t_name} tier competencies.",
                    "lessons": mod_lessons
                })
        
        # If knowledgeGraph is missing but modules exists, synthesize KG from modules
        if not kg_raw and modules_raw:
            kg_raw = []
            for m in modules_raw:
                if isinstance(m, dict):
                    m_tier = m.get("tier", "Beginner")
                    for les in (m.get("lessons") or []):
                        if isinstance(les, dict):
                            l_id = les.get("id") or les.get("targetSkillId") or f"node_{uuid.uuid4().hex[:6]}"
                            l_title = les.get("title") or "Concept"
                            kg_raw.append({
                                "nodeId": l_id,
                                "skillId": les.get("targetSkillId") or l_id,
                                "label": l_title,
                                "tier": m_tier,
                                "isRevisionModule": bool(m.get("isRevision", False)),
                                "prerequisites": [],
                                "initialMastery": 0.0,
                                "linkedMisconceptions": []
                            })
                            
        return {
            "domain": str(domain),
            "detectedLevel": str(detected_level),
            "knowledgeGraph": kg_raw,
            "modules": modules_raw
        }


# ==========================================
# 4. LESSON DEEP CONTENT SCHEMAS (Addendum v3)
# ==========================================

class SubtopicBreakdownItem(BaseModel):
    subtopicId: str
    title: str
    learningGoal: str
    orderIndex: int

    @model_validator(mode='before')
    @classmethod
    def normalize_subtopic_item(cls, data):
        if not isinstance(data, dict):
            return data
        s_id = data.get("subtopicId") or data.get("subtopic_id") or data.get("subtopic-id") or data.get("id") or f"sub_{uuid.uuid4().hex[:6]}"
        title = data.get("title") or data.get("name") or "Subtopic"
        goal = data.get("learningGoal") or data.get("learning_goal") or data.get("learning-goal") or data.get("goal") or "Master this subtopic."
        order = data.get("orderIndex") or data.get("order_index") or data.get("order") or 0
        return {
            "subtopicId": str(s_id),
            "title": str(title),
            "learningGoal": str(goal),
            "orderIndex": int(order)
        }

class SubtopicBreakdown(BaseModel):
    skillName: str
    subtopics: List[SubtopicBreakdownItem]

    @model_validator(mode='before')
    @classmethod
    def normalize_breakdown(cls, data):
        if not isinstance(data, dict):
            return data
        s_name = data.get("skillName") or data.get("skill_name") or data.get("skill") or "Lesson"
        subtopics = data.get("subtopics") or data.get("topics") or data.get("modules") or []
        return {
            "skillName": str(s_name),
            "subtopics": subtopics
        }

class SectionMCQ(BaseModel):
    id: str = "mcq_1"
    question: str
    options: List[str] = Field(..., min_length=2)
    correctIndex: int = 0
    explanation: str = ""

    @model_validator(mode='before')
    @classmethod
    def normalize_section_mcq(cls, data):
        if not isinstance(data, dict):
            return data
        q_id = data.get("id") or data.get("mcqId") or f"mcq_{uuid.uuid4().hex[:6]}"
        question = data.get("question") or data.get("prompt") or "Practice Question"
        options = data.get("options") or data.get("choices") or ["A", "B", "C", "D"]
        correct = data.get("correctIndex") or data.get("correct_index") or data.get("answer") or 0
        try:
            correct = int(correct)
        except Exception:
            correct = 0
        explanation = data.get("explanation") or data.get("reason") or ""
        return {
            "id": str(q_id),
            "question": str(question),
            "options": [str(o) for o in options],
            "correctIndex": correct,
            "explanation": str(explanation)
        }

class SubtopicContent(BaseModel):
    subtopicId: str
    content: str
    example: str
    miniCheckQuestion: Optional[str] = ""
    mcqQuestions: List[SectionMCQ] = Field(default_factory=list)

    @model_validator(mode='before')
    @classmethod
    def normalize_subtopic_content(cls, data):
        if not isinstance(data, dict):
            return data
        s_id = data.get("subtopicId") or data.get("subtopic_id") or data.get("subtopic-id") or data.get("id") or "subtopic"
        content = data.get("content") or data.get("explanation") or data.get("body") or ""
        example = data.get("example") or data.get("code") or data.get("sample") or ""
        mini = data.get("miniCheckQuestion") or data.get("mini_check_question") or data.get("checkQuestion") or ""
        mcqs = data.get("mcqQuestions") or data.get("mcqs") or data.get("practiceQuestions") or data.get("questions") or []
        return {
            "subtopicId": str(s_id),
            "content": str(content),
            "example": str(example),
            "miniCheckQuestion": str(mini),
            "mcqQuestions": mcqs
        }

class QuizQuestion(BaseModel):
    id: str
    subtopicId: Optional[str] = None
    question: str
    options: List[str] = Field(..., min_length=2)
    correctIndex: int
    explanation: str

    @model_validator(mode='before')
    @classmethod
    def normalize_quiz_question(cls, data):
        if not isinstance(data, dict):
            return data
        q_id = data.get("id") or data.get("questionId") or f"qz_{uuid.uuid4().hex[:6]}"
        s_id = data.get("subtopicId") or data.get("subtopic_id") or data.get("subtopic-id")
        question = data.get("question") or data.get("prompt") or "Mastery Question"
        options = data.get("options") or data.get("choices") or ["A", "B", "C", "D"]
        correct = data.get("correctIndex") or data.get("correct_index") or data.get("answer") or 0
        try:
            correct = int(correct)
        except Exception:
            correct = 0
        explanation = data.get("explanation") or data.get("reason") or ""
        return {
            "id": str(q_id),
            "subtopicId": str(s_id) if s_id else None,
            "question": str(question),
            "options": [str(o) for o in options],
            "correctIndex": correct,
            "explanation": str(explanation)
        }

class LessonQuiz(BaseModel):
    questions: List[QuizQuestion]

    @model_validator(mode='before')
    @classmethod
    def normalize_lesson_quiz(cls, data):
        if not isinstance(data, dict):
            return data
        questions = data.get("questions") or data.get("quiz") or []
        return {
            "questions": questions
        }


# ==========================================
# 5. REMEDIATION & RETEACH SCHEMAS
# ==========================================

class ReteachResponse(BaseModel):
    reteachContent: str
    checkInQuestion: str

class RemediationResponse(BaseModel):
    remediationText: str
    recommendedFocus: List[str]

class RetryQuizResponse(BaseModel):
    quiz: List[QuizQuestion]


# ==========================================
# 6. TRENDING TOPICS SCHEMAS
# ==========================================

class TrendingTopicsResponse(BaseModel):
    topics: List[str]
