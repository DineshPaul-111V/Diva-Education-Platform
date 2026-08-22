import json

def get_language_instruction(lang_override: str = None) -> str:
    from flask import request, has_request_context
    lang = lang_override
    if not lang and has_request_context():
        if request.is_json and request.json:
            lang = request.json.get('language') or request.json.get('lang')
        if not lang:
            lang = request.args.get('lang') or request.cookies.get('preferred_language', 'English')
    lang = lang or 'English'
    lang_lower = lang.strip().lower()
    if lang_lower != 'english':
            # Language specific nuances
            specific_guidelines = ""
            if lang_lower == 'tamil':
                specific_guidelines = """- TAMIL PEDAGOGICAL TONE: Use natural, conversational Tamil (தமிழ்) with intuitive terminology (e.g. மாறிகள் for variables, தரவுத்தளம் for database, செயற்கூறு for functions where helpful, with English terms in brackets if clarifying).
- Keep real-world analogies culturally vibrant and familiar (e.g. சமையல் குறிப்பு / recipe steps, ரயில் முன்பதிவு / railway booking, நூலக அட்டை / library catalog)."""
            elif lang_lower == 'telugu':
                specific_guidelines = """- TELUGU PEDAGOGICAL TONE: Use clear, engaging Telugu (తెలుగు) with accessible phrasing (e.g. వేరియబుల్స్, ఫంక్షన్లు, డేటా స్ట్రక్చర్స్ with English technical terms preserved or in brackets).
- Keep analogies vivid and relatable (e.g. వంట తయారీ క్రమం, కిరాణా సరుకుల జాబితా, బస్సు రిజర్వేషన్ సిస్టమ్)."""
            elif lang_lower == 'bengali':
                specific_guidelines = """- BENGALI PEDAGOGICAL TONE: Use lucid, natural Bengali (বাংলা) with clear conceptual explanations (e.g. চলক/ভেরিয়েবল, ফাংশন, মেমরি লেআউট).
- Keep analogies relatable and vivid (e.g. রান্নার প্রণালী, বইয়ের তাক ও ইনডেক্স, মেট্রো রেল টিকিট টিকিট বুকিং)."""
            elif lang_lower == 'marathi':
                specific_guidelines = """- MARATHI PEDAGOGICAL TONE: Use clear, structured Marathi (मराठी) with intuitive explanations (e.g. व्हेरिएबल्स, फंक्शन्स, डेटा स्ट्रक्चर्स).
- Keep analogies relatable (e.g. स्वयंपाकाची रेसिपी, किराणा मालाची यादी, रेल्वे आरक्षण प्रणाली)."""
            elif lang_lower == 'hindi':
                specific_guidelines = """- HINDI PEDAGOGICAL TONE: Use engaging, clear Hindi (हिंदी) with natural technical phrasing (Hinglish-friendly technical vocabulary like वेरिएबल्स, फंक्शन्स, लूप्स, एरे for crystal-clear comprehension).
- Keep analogies intuitive and memorable (e.g. चाय बनाने की रेसिपी, क्रिकेट स्कोरबोर्ड, बैंक खाता पासबुक)."""

            return f"""

CRITICAL MULTI-LINGUAL PEDAGOGY RULES ({lang.upper()} TRANSLATION):
1. NARRATIVE TUTORIALS & EXPLANATIONS: Write all narrative explanations, conceptual analogies, topic breakdowns, trap explanations, and multiple-choice questions in natural, clear {lang}.
{specific_guidelines}
2. ALL CODE BLOCKS & RUN PLACES MUST BE 100% PURE ENGLISH:
   - ALL programming code in ```python ... ```, ```javascript ... ```, ```sql ... ```, worked examples (`example` field), and syntax blocks MUST BE 100% PURE ENGLISH.
   - All string literals inside code (e.g. `print("--- Welcome to Python Calculator ---")`, `input("Enter your name: ")`, `print(f"Total Sum: {{total}}")`), all comments (e.g. `# Step 1: Calculate total sum`), all function names, all variable names, and all keywords MUST BE WRITTEN IN PURE ASCII ENGLISH.
   - STRICT PROHIBITION: NEVER use {lang} or any non-English script inside any code block, print statement, input prompt, comment, or worked example. All code run places must be 100% English.
3. ALL NUMBERS MUST USE NORMAL WESTERN ARABIC NUMERALS (0, 1, 2, 3, 4, 5, 6, 7, 8, 9):
   - ALWAYS use standard digits 0, 1, 2, 3, 4, 5, 6, 7, 8, 9 for all section titles (e.g. `Section 1`, `Section 2`), numbered list items (`1.`, `2.`, `3.`), math formulas ($O(1)$, $O(N)$), time estimates (`10 mins`), and numeric literals in code (`10`, `20`).
   - STRICT PROHIBITION: NEVER output non-Western numeral characters (e.g. DO NOT use Devanagari '१, २, ३', Telugu '౧, ౨, ౩', Tamil '௧, ௨, ௩', Bengali '১, ২, ৩', etc.).
4. JSON INTEGRITY: Keep all JSON object keys in English. All string values must be cleanly formatted without literal double-escaped quotes or raw '\\n' characters.
"""
    return ""



# ==========================================
# 1. SKILL-MAP PROMPT (Comprehensive Full-Spectrum Curriculum)
# ==========================================
def SKILL_MAP_PROMPT(domain: str) -> str:
    return f"""You are a principal curriculum architect and distinguished technical authority in "{domain}".
Produce an exhaustive, industry-grade canonical skill map a student needs to master from absolute zero beginner to principal/staff engineer level in this domain.

Organize skills into exactly 4 tiers in this strict order: "Beginner", "Intermediate", "Advanced", "Pro".
CRITICAL REQUIREMENT: You MUST include the "Pro" tier. Failure to include the "Pro" tier will break the system curriculum mapping.
Each tier MUST contain 5 to 8 concrete, modern, highly specific, and actionable skills/classes covering the complete modern ecosystem (foundations, language/framework mechanics, tooling, debugging, system design, and production engineering).
Ensure skills within each tier are sequenced in strict prerequisite order from ground-up foundations to complex topics.
CRITICAL COVERAGE RULE: A skill map is incomplete if it only covers "impressive" architecture and performance topics while skipping practical, job-critical skills. Across the Intermediate and Advanced tiers combined, you MUST include at least one skill from EACH of these categories if they are relevant to "{domain}": (a) accessibility/a11y and semantic/inclusive design, (b) build tooling, bundlers, and dev environment configuration, (c) error handling and resilience patterns (e.g. error boundaries, retries, fallback states), (d) automated testing strategy, (e) CI/CD and deployment workflow. Sequence testing-related skills as early as reasonably possible (do not push them to the very end of Advanced) since good testing habits should apply to everything taught afterward.

Return strictly valid JSON, no prose, matching this schema:
{{
  "domain": "{domain}",
  "skillMap": [
    {{
      "tier": "Beginner",
      "skills": [
        {{
          "skillId": "string, kebab-case, unique across all tiers",
          "name": "string",
          "description": "string, clear explanation of why this skill is vital and what it accomplishes",
          "prerequisiteSkillIds": ["string", "..."]
        }}
      ]
    }},
    {{ "tier": "Intermediate", "skills": [ ... ] }},
    {{ "tier": "Advanced", "skills": [ ... ] }},
    {{ "tier": "Pro", "skills": [ ... ] }}
  ]
}}
"""

# ==========================================
# 2. DIAGNOSTIC PROMPT
# ==========================================
def DIAGNOSTIC_PROMPT(domain: str, skill_map_dict: dict) -> str:
    return f"""You are an expert assessor for "{domain}". Here is the canonical skill map for this domain:
{json.dumps(skill_map_dict)}

Generate an adaptive placement assessment of exactly 8 questions that samples across ALL FOUR
tiers (exactly 2 Beginner, 2 Intermediate, 2 Advanced, 2 Pro questions) so we can accurately
detect which tier the student is actually performing at. Tag each question with the skillId
and tier it tests. Increase conceptual depth within each tier.
CRITICAL REQUIREMENT: You MUST include questions with "tier": "Pro".

For each question:
- Provide 4 distinct, plausible options in the "options" array.
- "correctAnswer" MUST be the exact 0-based index (0, 1, 2, or 3) of the correct option.
- Distribute the correct answer index across different positions (0, 1, 2, 3) rather than always using 0.

Return strictly valid JSON, no prose:
{{
  "domain": "{domain}",
  "questions": [
    {{
      "id": "q1",
      "tier": "Beginner",
      "skillId": "string — must match a skillId from the provided skill map",
      "question": "string",
      "options": ["Option A","Option B","Option C","Option D"],
      "correctAnswer": 0,
      "explanation": "string",
      "misconceptionMapping": {{ "0": "misconception if select Option A", "1": "misconception if select Option B", "2": "misconception if select Option C", "3": "misconception if select Option D" }}
    }}
  ]
}}
"""

# ==========================================
# 3. ROADMAP PROMPT
# ==========================================
def ROADMAP_PROMPT(domain: str, skill_map_dict: dict, detected_level: str, diagnostic_misconceptions: list) -> str:
    return f"""Domain: "{domain}"
Full canonical skill map: {json.dumps(skill_map_dict)}
Student's detected starting level: "{detected_level}"
Misconceptions detected during placement: {json.dumps(diagnostic_misconceptions)}

Build a personalized learning roadmap following these MANDATORY rules:
1. If detectedLevel is "Beginner": include EVERY skill from the Beginner tier, taught from
   scratch, in prerequisite order. Do not skip any.
2. If detectedLevel is "Intermediate": include a compact "Beginner Revision" module covering
   Beginner tier skills (condensed, assumes some familiarity, faster pace) BEFORE starting
   Intermediate tier skills in full from scratch.
3. If detectedLevel is "Advanced": include condensed revision modules for BOTH Beginner and
   Intermediate tiers before starting Advanced tier skills in full from scratch.
4. If detectedLevel is "Pro": include condensed revision for Beginner, Intermediate, AND
   Advanced tiers before starting Pro tier skills in full from scratch.
5. Every module must map to specific skillId(s) from the provided skill map — the roadmap
   must eventually cover 100% of skillIds across ALL tiers, ending at Pro. Nothing in the
   skill map may be omitted from the full roadmap (revision modules can be condensed, but
   omission is not allowed).
6. Any skillId present in "diagnosticMisconceptions" gets an extra flagged "reinforcement"
   note on its corresponding roadmap node, regardless of tier.

Return strictly valid JSON, no prose:
{{
  "domain": "{domain}",
  "detectedLevel": "{detected_level}",
  "knowledgeGraph": [
    {{
      "nodeId": "string",
      "skillId": "string — matches skill map",
      "label": "string",
      "tier": "Beginner | Intermediate | Advanced | Pro",
      "isRevisionModule": false,
      "prerequisites": ["nodeId"],
      "initialMastery": 0.0,
      "linkedMisconceptions": ["string"]
    }}
  ],
  "modules": [
    {{
      "id": "string",
      "title": "string",
      "tier": "Beginner | Intermediate | Advanced | Pro",
      "isRevision": false,
      "description": "string",
      "lessons": [
        {{ "id": "string", "title": "string", "estimatedMinutes": 50, "targetSkillId": "string" }}
      ]
    }}
  ]
}}
"""

# ==========================================
# 4. SUBTOPIC BREAKDOWN PROMPT (50-Minute Comprehensive Curriculum)
# ==========================================
# ==========================================
# 4. SUBTOPIC BREAKDOWN PROMPT (50-Minute Comprehensive Curriculum)
# ==========================================
# ==========================================
# 4. SUBTOPIC BREAKDOWN PROMPT (50-Minute Comprehensive Curriculum)
# ==========================================
def SUBTOPIC_BREAKDOWN_PROMPT(skill_name: str, skill_description: str, tier: str, is_revision: bool) -> str:
    revision_text = "This is an intensive revision masterclass (35 mins)." if is_revision else "This is a full 50-minute comprehensive masterclass."
    num_subtopics = "4" if is_revision else "4 to 5"
    
    tier_subtopic_guidance = ""
    if tier.lower() == "beginner":
        tier_subtopic_guidance = """
For BEGINNER modules:
1. Core Foundations & Intuitive Mental Model (What is this, everyday physical analogy, why we use it)
2. In-Depth Basics & Step-by-Step Code Walkthrough (First runnable scripts, variables, basic input/output)
3. Practical Everyday Examples & Useful Patterns (Simple real-world tasks, clean code)
4. Common Beginner Mistakes & How to Avoid Them (Syntax errors, indentation, debugging tips)
5. Summary, Best Practices & Quick Revision Card (Key rules, cheat sheet)
DO NOT create advanced topics like 'High-Performance Memory Layout' or 'Vector Spaces' for a basic beginner module.
"""
    else:
        tier_subtopic_guidance = """
1. Core Foundations & Intuitive Mental Model (Real-world analogies, problem origin, baseline definitions)
2. In-Depth Mechanics & Step-by-Step Code Walkthrough (Parameter mechanics, runtime execution flow)
3. Advanced Transformations & Production Patterns (Realistic scenarios, edge-case safety, typing)
4. Traps, Anti-Patterns & Silent Bugs (Common mistakes, root-cause diagnosis, fixes)
5. High-Performance Architecture, Memory Layout, Big-O Complexity & Scale
"""
    
    return f"""You are Diva AI, a world-class computer science curriculum architect and educator.
Design a structured 50-minute learning syllabus for the skill "{skill_name}" ({skill_description}), tier: {tier}.
{revision_text}

Break this single skill down into exactly {num_subtopics} logically sequenced, progressive sub-topic modules that together form a complete 50-minute masterclass.
Ensure smooth cognitive scaffolding: each sub-topic must build naturally on the previous one without sudden jumps in complexity.
Each sub-topic must represent approximately 10–12 minutes of structured study time, following these tier guidelines:
{tier_subtopic_guidance}
{get_language_instruction()}

Return strictly valid JSON, no prose:
{{
  "skillName": "{skill_name}",
  "subtopics": [
    {{
      "subtopicId": "string, kebab-case",
      "title": "string (e.g. '1. Core Foundations: Intuition & Basics (~10 mins)')",
      "learningGoal": "string — clear, actionable capability the student gains after completing this section",
      "orderIndex": 0
    }}
  ]
}}
"""

# ==========================================
# 5. PER-SUBTOPIC DEEP CONTENT PROMPT (Diva Ideas 8-Part Masterclass & Retention Standard)
# ==========================================
# ==========================================
# 5. PER-SUBTOPIC DEEP CONTENT PROMPT (Diva Ideas 8-Part Masterclass & Retention Standard)
# ==========================================
def SUBTOPIC_CONTENT_PROMPT(skill_name: str, subtopic_title: str, learning_goal: str, tier: str, is_revision: bool, domain_context: str, already_covered_summary: str = "") -> str:
    tier_guideline = ""
    if tier.lower() == "beginner":
        tier_guideline = """
CRITICAL BEGINNER TIER CONSTRAINTS:
- This is a BEGINNER lesson. Assume the student is starting from scratch.
- Keep all explanations, analogies, and code examples grounded in everyday programming fundamentals (printing, simple arithmetic, basic strings, variables, simple lists/loops).
- STRICT PROHIBITION: DO NOT reference advanced Machine Learning, tensors, deep learning, GPU kernels, neural networks, or complex distributed clustering in an introductory lesson. Keep it 100% focused on basic concepts.
"""
    elif tier.lower() == "intermediate":
        tier_guideline = """
INTERMEDIATE TIER CONSTRAINTS:
- Focus on practical software engineering, modular design, dictionaries, functions, data structures, and standard libraries.
"""
    else:
        tier_guideline = """
ADVANCED TIER CONSTRAINTS:
- Cover high-performance architecture, concurrency, memory layout, Big-O algorithmic scaling, and distributed enterprise scale.
"""

    # NEW: only added when there is prior subtopic history to avoid repeating
    redundancy_guard = ""
    if already_covered_summary.strip():
        redundancy_guard = f"""
CRITICAL ANTI-REDUNDANCY RULE:
The following concepts, examples, and code patterns were ALREADY taught in earlier subtopics of this same module:
\"\"\"
{already_covered_summary}
\"\"\"
Do NOT re-teach, re-explain, or re-demonstrate any of the above from scratch. If this subtopic's learning goal genuinely requires referencing one of these concepts, mention it in one short sentence ("as you saw earlier with let/const...") and move on immediately to NEW material. Every code example, analogy, and trap in this subtopic must introduce something the student has NOT already seen in this module. Overlap with prior subtopics is a critical failure of this task.
"""

    return f"""You are Diva AI, a master technical educator and principal software architect authoring an exhaustive, highly memorable masterclass chapter for "{skill_name}" within a {domain_context} course (Tier: {tier}).
Write a complete, deeply engaging, crystal-clear instructional chapter for: "{subtopic_title}".
Learning goal: {learning_goal}

{tier_guideline}
{redundancy_guard}

MANDATORY PEDAGOGICAL SPECIFICATIONS (Diva Ideas 8-Part Deep Mastery & High-Retention Standard):
1. CLARITY & ACCESSIBILITY FOR EVERY LEARNER: Explain concepts using simple, vivid, intuitive language. Break down complex mechanics into first principles. Explain what it is, why it was invented, and how it works under the hood before showing code.
2. MAXIMUM EDUCATIONAL DEPTH: Write 1,200–1,800 words of thorough, articulated educational content. Walk through every concept step-by-step. Do not summarize, truncate, or skip steps. CRITICAL: You MUST preserve exact indentation (using spaces) inside all code blocks.
3. LONG-TERM MEMORY RETENTION: Use mnemonic anchors, physical everyday analogies, and comparison tables so students can easily remember and distinguish concepts.
4. MANDATORY 8-PART CHAPTER STRUCTURE (You MUST include all 8 exact Markdown headings in your content):

   ### 1. 📖 Intuitive Mental Model & Real-World Anchor (Zero Jargon)
   - The "Why This Exists" First Principle: What everyday computational challenge led to this concept?
   - The Real-World Physical Analogy: A vivid everyday metaphor (e.g. kitchen recipes, postal sorting, grocery shopping list, library index) that makes the concept click instantly.
   - Core Definition in Plain English: Clear, jargon-free technical explanation.

   ### 2. ⚡ Syntax Blueprint & Parameter Mechanics (Diva Ideas Standard)
   - Clean, formal syntax structure with annotated types, arguments, and return values.
   - Minimalist Baseline ("Hello World"): The simplest possible valid execution.
   - Parameter & Option Table: Markdown table detailing `Parameter`, `Type`, `Purpose`, and `Default / Rules`.

   ### 3. 💻 Step-by-Step Code Walkthrough (Beginner ➔ Pro Evolution)
   - 3 progressive, runnable code examples:
     - Level 1: Minimal Core Usage
     - Level 2: Practical Transformation with Edge Case Handling (nulls, empty inputs, boundary bounds)
     - Level 3: Production Scenario (clean idioms, type annotations, error handling)
   - CRITICAL REQUIREMENT: Every single code example MUST be wrapped in triple backticks with the `python` language identifier (i.e. ```python ... ```). NEVER output raw code without backticks.
   - High-quality code with exhaustive inline comments explaining why each line exists.
   - Explicit **Expected Output** block below every code example showing what prints to console.
   - Execution Stepper: Step-by-step breakdown of how state changes in memory line-by-line during runtime.

   ### 4. 📊 Visual Architecture & State Flow (Mermaid.js Diagram)
   - A clean, beautiful vector diagram in dark-theme Mermaid syntax (`flowchart TD`, `graph LR`, or `sequenceDiagram`) visualizing data transformation, variables, or execution branching.
   - CRITICAL: NEVER output raw unfenced ASCII art. Use ONLY fenced ```mermaid ... ``` or ```text ... ``` blocks.

   ### 5. 🧠 Memory Hooks, Mnemonics & Disambiguation Matrix (Remember Forever)
   - The "Golden Rule of Thumb": A memorable 1-sentence mental anchor.
   - Mnemonic Acronym or Rhyme: An easy-to-remember phrase or acronym to recall syntax rules or steps under pressure.
   - Concept Comparison Table: A Markdown table comparing this concept against 2 common alternatives, eliminating confusion.

   ### 6. ⚠️ Common Beginner Traps & Anti-Pattern Matrix
   - Detail at least 2 common beginner traps, syntax mistakes, or silent bugs.
   - Format systematically with:
     - ❌ **Wrong Code / Anti-Pattern** (what causes errors or bugs)
     - 💥 **What Goes Wrong** (specific error or unintended behavior)
     - ✅ **Correct Production Solution** (idiomatic fix)
     - 💡 **Why this fix works** (underlying reason)

   ### 7. 🚀 Pro-Level Best Practices, Big-O Complexity & Industry Scale
   - Algorithmic Complexity: Time Complexity $O(...)$ and Space Complexity $O(...)$ with intuitive reasons why.
   - Production Best Practices: Clean code conventions, naming rules, and error handling.
   - Real-World Industry Case Study: How real engineering teams leverage this concept in production.

   ### 8. 📌 60-Second Memory Card & Cheat Sheet
   - 3–4 key takeaway bullet points summarizing the core rules.
   - Quick-reference syntax cheat snippet for instant recall before quizzes.

5. CRITICAL CODE FORMATTING RULES (STRICTLY ENFORCED FOR ALL CODE BLOCKS):
   - Every code block MUST use exactly 4 spaces per indentation level. NEVER flatten indented
     blocks (if/for/while/def/class/try bodies) to the left margin. A line inside an "if" or
     "for" block must visually start 4 spaces deeper than the block header that opens it.
   - Every line of narration, explanation, or step description that appears INSIDE a fenced
     code block (```python ... ```) MUST start with a Python comment marker "# ". NEVER write
     a bare English sentence like "Level 1: Displaying a simple greeting" on its own line
     inside a code fence without a leading "#". If it is not valid, executable Python syntax,
     it must be a "#" comment.
   - Example of what NOT to do:
```python
     Level 1: Spot the missing colon
     score = 85
     if score >= 80
     print("Great job!")
```
   - Example of the REQUIRED correct format:
```python
     # Level 1: Spot the missing colon
     score = 85
     if score >= 80:
         print("Great job!")
```
6. WORKED EXAMPLE: Provide a full, self-contained runnable code snippet demonstrating best practices.
7. MODULE PRACTICE: Generate EXACTLY 3 multiple-choice practice questions (MCQs) directly evaluating deep comprehension of this module (4 distinct plausible choices each, with a 0-indexed correctIndex and thorough explanatory rationale).
8. CHECK-IN REFLECTION: Provide one targeted diagnostic question to test comprehension.
{get_language_instruction()}

Return strictly valid JSON, no prose:
{{
  "subtopicId": "string — must match the subtopic this was generated for",
  "content": "string — full markdown containing all 8 required sections with headers, tables, Mermaid diagrams, memory hooks, code fences, and console outputs, 1200-1800 words",
  "example": "string — self-contained runnable code snippet or worked example",
  "miniCheckQuestion": "string — single diagnostic check question for this subtopic",
  "mcqQuestions": [
    {{
      "id": "mcq_1",
      "question": "string — Question 1 testing core mechanism of this module",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correctIndex": 0,
      "explanation": "string — detailed explanation of why this option is correct and others are flawed"
    }},
    {{
      "id": "mcq_2",
      "question": "string — Question 2 testing practical implementation or syntax pattern",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correctIndex": 1,
      "explanation": "string — detailed explanation of why this option is correct"
    }},
    {{
      "id": "mcq_3",
      "question": "string — Question 3 testing edge cases, performance, or debugging traps",
      "options": ["Option A", "Option B", "Option C", "Option D"],
      "correctIndex": 2,
      "explanation": "string — detailed explanation of the edge case and solution"
    }}
  ]
}}
"""

def LESSON_QUIZ_PROMPT(skill_name: str, subtopic_titles: list, tier: str) -> str:
    subtopics_str = ", ".join(subtopic_titles)
    return f"""Create a 5-question multiple-choice comprehensive mastery quiz for the 50-minute module "{skill_name}" (tier: {tier}).
Topics covered in this module: {subtopics_str}.

Requirements:
- Distribute questions across all subtopics to evaluate full-spectrum mastery.
- Include scenario-based questions, code snippet analysis, and architectural decision questions.
- Provide 4 distinct options per question with 0-indexed correctIndex and clear, instructive explanations.
{get_language_instruction()}

Return strictly valid JSON, no prose:
{{
  "questions": [
    {{
      "id": "qz_1",
      "subtopicId": "string — which subtopic this question tests",
      "question": "string",
      "options": ["string","string","string","string"],
      "correctIndex": 0,
      "explanation": "string"
    }}
  ]
}}
"""

# ==========================================
# 7. RETEACH PROMPT (Addendum v2 Section 3.8 / v3 scoping)
# ==========================================
def RETEACH_PROMPT(skill_name: str, subtopic_title: str, original_explanation: str, student_struggle: str) -> str:
    return f"""A student is learning subtopic "{subtopic_title}" under the skill "{skill_name}". Here was the original explanation:
\"\"\"
{original_explanation}
\"\"\"
They indicated they did not understand it. Signal from student: "{student_struggle}"

Re-teach this sub-topic concept COMPLETELY DIFFERENTLY from the original explanation — use a different
analogy, a different structural approach (e.g. if the original was text-heavy, use a
step-by-step numbered breakdown or a concrete worked example instead). Keep it short and
plain-language. End by asking a simple check-in question to confirm understanding this time.
{get_language_instruction()}

Return strictly valid JSON, no prose:
{{
  "reteachContent": "string — markdown",
  "checkInQuestion": "string"
}}
"""

# ==========================================
# 8. RETRY QUIZ PROMPT
# ==========================================
def RETRY_QUIZ_PROMPT(topic: str, user_level: str, lesson_content_markdown: str, remediation_summary: str) -> str:
    return f"""Generate a fresh 3-question multiple-choice evaluation quiz on "{topic}" for a student at level "{user_level}".

Here is a portion of the lesson content the student studied:
\"\"\"
{lesson_content_markdown[:1500]}
\"\"\"

Targeted remediation provided to the student:
\"\"\"
{remediation_summary[:800]}
\"\"\"

CRITICAL RULES:
1. Every quiz question must strictly evaluate ONLY what is taught in the lesson content and remediation above. Do NOT introduce outside topics.
2. Provide 4 distinct options per question. Exactly one option must be unequivocally correct.
3. For each question, "correctIndex" MUST be the exact 0-based index of the correct option (0, 1, 2, or 3). Vary the correct option index across questions (e.g. 1, 2, 0).
{get_language_instruction()}

Return strictly valid JSON, no prose:
{{
  "quiz": [
    {{
      "id": "qz_retry_1",
      "question": "string — directly testing the taught material",
      "options": ["Distractor A", "Correct Answer", "Distractor B", "Distractor C"],
      "correctIndex": 1,
      "explanation": "string"
    }}
  ]
}}
"""

# ==========================================
# 9. TARGETED REMEDIATION PROMPT
# ==========================================
def REMEDIATION_PROMPT(topic: str, wrong_answers: str) -> str:
    return f"""The student failed the mastery check for "{topic}" (needs ≥70% to pass) with these specific mistakes:
{wrong_answers}

Write a targeted, empathetic remedial explanation that addresses these exact misconceptions using
intuitive analogies and, if relevant, a short code step-through. Do NOT reveal answers to a future
retake quiz. End with one encouraging sentence.
{get_language_instruction()}

Return strictly valid JSON, no prose, matching this schema:
{{
  "remediationText": "string — markdown formatted",
  "recommendedFocus": ["string — concept names to revisit"]
}}
"""

# ==========================================
# 10. TRENDING TOPICS PROMPT
# ==========================================
def TRENDING_TOPICS_PROMPT() -> str:
    return """Suggest 6 currently in-demand IT/programming/CS learning topics suitable for an adaptive
learning platform. Mix languages, frameworks, and conceptual domains. Keep each under 5 words.

Return strictly valid JSON, no prose:
{ "topics": ["string", "string", "string", "string", "string", "string"] }
"""

# ==========================================
# 11. AI TUTOR RAG PROMPT (Diva AI Master Copilot)
# ==========================================
def TUTOR_RAG_PROMPT(student_message: str, retrieved_context: list, quick_action: str = None, language: str = None) -> str:
    context_str = "\n".join(f"[{i + 1}] {c}" for i, c in enumerate(retrieved_context))
    
    action_prompt = ""
    if quick_action == "simplify":
        action_prompt = "SPECIAL MODE: ELI5 / Simplify. Explain using simple plain-English language and a relatable everyday real-world analogy."
    elif quick_action == "enterprise_example":
        action_prompt = "SPECIAL MODE: Enterprise Production. Walk through how top companies (Google, Netflix, Meta, Stripe) implement this at scale with high availability and efficiency."
    elif quick_action == "debug_thought":
        action_prompt = "SPECIAL MODE: Debugging Mindset. Walk through a common silent bug or error, dissect the root cause, and demonstrate the step-by-step fix."
    elif quick_action == "quiz_me":
        action_prompt = "SPECIAL MODE: Socratic Practice. Ask the student one targeted, thought-provoking question to test their comprehension of the topic, and invite them to answer."
    elif quick_action == "code_breakdown":
        action_prompt = "SPECIAL MODE: Code Breakdown. Provide a clean, minimal runnable code snippet with inline comments and explicit Expected Output."
        
    return f"""You are Diva AI, an ultra-intelligent, friendly, and expert computer science tutor on the Diva AI learning platform.
Answer the student authoritatively using the lesson context below and your broad engineering expertise.

PEDAGOGICAL GUIDELINES:
1. Be concise, crystal-clear, and encouraging.
2. If explaining code, provide clean, runnable snippets with inline comments and expected outputs.
3. If explaining architecture, data flow, or memory layout, use fenced ```mermaid ... ``` diagrams (e.g. `graph LR` or `flowchart TD`). Never use raw unfenced ASCII art.
4. Conclude with a brief Socratic check-in question or key insight when appropriate.

Lesson Context:
{context_str}

{action_prompt}

Student query: "{student_message}"
{get_language_instruction(language)}

Respond conversationally in rich markdown. No JSON wrapper — output clean Markdown text only.
"""

