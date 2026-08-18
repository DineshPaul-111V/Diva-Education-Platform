import re
import concurrent.futures
from app.learning.services.llm import call_llm
from app.learning.services.prompts import SUBTOPIC_BREAKDOWN_PROMPT, SUBTOPIC_CONTENT_PROMPT, LESSON_QUIZ_PROMPT
from app.learning.services.schemas import SubtopicBreakdown, SubtopicContent, LessonQuiz
from app.learning.services.rag import store_student_embedding

def auto_fence_ascii_art(markdown_text: str) -> str:
    """
    Finds consecutive lines of raw ASCII box drawing / flowcharts (lines with +, -, |, >, <)
    that are outside of existing code blocks, and wraps them in ```text ... ```.
    """
    if not markdown_text:
        return ""
    lines = markdown_text.split("\n")
    new_lines = []
    in_code_block = False
    ascii_buffer = []
    
    def is_ascii_diagram_line(line: str) -> bool:
        trimmed = line.strip()
        if not trimmed:
            return False
        # Table rows like | col | col | shouldn't be boxed if it's a markdown table
        if re.match(r"^\|[^|]+\|.*\|$", trimmed):
            return False
        # Box lines like +--------+ or +---+---+
        if re.match(r"^\+[-+=]+\+.*$", trimmed):
            return True
        # Flow lines with arrows like | ---> | or +----->+ or | ===> |
        if ("| ----" in trimmed or "| --->" in trimmed or "+ --->" in trimmed or "---->" in trimmed) and ("|" in trimmed or "+" in trimmed):
            return True
        if trimmed.startswith("+--") or trimmed.endswith("--+"):
            return True
        return False

    for line in lines:
        if line.strip().startswith("```"):
            if ascii_buffer:
                new_lines.append("```text")
                new_lines.extend(ascii_buffer)
                new_lines.append("```")
                ascii_buffer = []
            in_code_block = not in_code_block
            new_lines.append(line)
            continue
            
        if in_code_block:
            new_lines.append(line)
            continue
            
        if is_ascii_diagram_line(line):
            ascii_buffer.append(line)
        else:
            if ascii_buffer:
                new_lines.append("```text")
                new_lines.extend(ascii_buffer)
                new_lines.append("```")
                ascii_buffer = []
            new_lines.append(line)
            
    if ascii_buffer:
        new_lines.append("```text")
        new_lines.extend(ascii_buffer)
        new_lines.append("```")
        
    return "\n".join(new_lines)

def normalize_numerals(text: str) -> str:
    """
    Converts any non-standard regional numerals (Devanagari, Eastern Arabic, Persian, Tamil, Telugu, Bengali)
    into standard Western Arabic digits 0-9 across all courses and languages.
    """
    if not text:
        return ""
    devanagari_map = str.maketrans("०१२३४५६७८९", "0123456789")
    arabic_indic_map = str.maketrans("٠١٢٣٤٥٦٧٨٩", "0123456789")
    persian_map = str.maketrans("۰۱۲۳۴۵۶۷۸۹", "0123456789")
    tamil_map = str.maketrans("௦௧௨௩௪௫௬௭௮௯", "0123456789")
    telugu_map = str.maketrans("౦౧౨౩౪౫౬౭౮౯", "0123456789")
    bengali_map = str.maketrans("০১২৩৪৫৬৭৮৯", "0123456789")

    return text.translate(devanagari_map).translate(arabic_indic_map).translate(persian_map).translate(tamil_map).translate(telugu_map).translate(bengali_map)

def normalize_markdown_content(markdown_text: str) -> str:
    """
    Normalizes markdown text by:
    1. Unescaping literal '\\n' and '\\t' sequences and carriage returns.
    2. Converting any regional numeral characters into standard Western '1, 2, 3' digits.
    3. Cleaning up double-escaped quote artifacts in code blocks.
    4. Auto-fencing ASCII box diagrams into ```text ... ```.
    """
    if not markdown_text:
        return ""
    
    if "\\n" in markdown_text:
        markdown_text = markdown_text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
        
    markdown_text = markdown_text.replace("\r\n", "\n").replace("\r", "\n")
    
    # Normalize numerals across all languages to 0-9
    markdown_text = normalize_numerals(markdown_text)
    
    # Fix broken escaped quote patterns in code strings (e.g. print(f"\"\n... -> print(f"\n...)
    markdown_text = re.sub(r'print\(f\\"[\\n|\n]', 'print(f"\\n', markdown_text)
    markdown_text = re.sub(r'print\(f"[\\"]', 'print(f"', markdown_text)
    
    return auto_fence_ascii_art(markdown_text)

def clean_code_example(example_text: str) -> str:
    """
    Cleans worked examples to ensure valid ASCII newlines, formatting, and standard Western numerals.
    """
    if not example_text:
        return ""
    if "\\n" in example_text:
        example_text = example_text.replace("\\r\\n", "\n").replace("\\n", "\n").replace("\\t", "\t")
    example_text = example_text.replace("\r\n", "\n").replace("\r", "\n")
    # Clean up double-escaped quote artifacts in print statements
    example_text = re.sub(r'print\(f\\"[\\n|\n]', 'print(f"\\n', example_text)
    example_text = re.sub(r'print\(f"[\\"]', 'print(f"', example_text)
    return normalize_numerals(example_text.strip())

def generate_full_lesson(learning_path_id: str, lesson_id: str, skill_name: str, skill_description: str, tier: str, is_revision: bool, domain: str) -> dict:
    """
    High-speed parallel multi-section lesson generation pipeline.
    1. Generates 3-4 focused subtopics.
    2. Concurrently generates deep content + 3 MCQs for all subtopics + 5-question mastery quiz in parallel.
    3. Auto-fences ASCII diagrams and renders Mermaid flowcharts.
    4. Saves embeddings for each subtopic.
    """
    # Step 1: Breakdown (4 to 5 deep subtopics for full 50-min curriculum)
    breakdown_prompt = SUBTOPIC_BREAKDOWN_PROMPT(skill_name, skill_description, tier, is_revision)
    breakdown = call_llm(breakdown_prompt, SubtopicBreakdown, max_tokens=1500)
    
    selected_subtopics = breakdown.subtopics[:5] if len(breakdown.subtopics) >= 5 else breakdown.subtopics
    
    # Pre-render prompt strings in main thread
    subtopic_prompts = []
    for subtopic in selected_subtopics:
        prompt_str = SUBTOPIC_CONTENT_PROMPT(
            skill_name, 
            subtopic.title, 
            subtopic.learningGoal, 
            tier, 
            is_revision, 
            domain
        )
        subtopic_prompts.append((subtopic, prompt_str))
    
    subtopic_titles = [sub.title for sub in selected_subtopics]
    quiz_prompt = LESSON_QUIZ_PROMPT(skill_name, subtopic_titles, tier)
    
    def fetch_subtopic_content(item):
        sub, p_str = item
        data = call_llm(p_str, SubtopicContent, max_tokens=4800)
        return sub, data

    def fetch_quiz(p_str):
        return call_llm(p_str, LessonQuiz, max_tokens=2000)

    sections = []
    with concurrent.futures.ThreadPoolExecutor(max_workers=5) as executor:
        subtopic_futures = [executor.submit(fetch_subtopic_content, item) for item in subtopic_prompts]
        quiz_future = executor.submit(fetch_quiz, quiz_prompt)
        
        for future in subtopic_futures:
            subtopic, content_data = future.result()
            mcq_list = []
            if getattr(content_data, "mcqQuestions", None):
                for m in content_data.mcqQuestions:
                    mcq_list.append({
                        "id": m.id,
                        "question": m.question,
                        "options": m.options,
                        "correctIndex": m.correctIndex,
                        "explanation": m.explanation
                    })

            cleaned_content = normalize_markdown_content(content_data.content)
            cleaned_example = clean_code_example(content_data.example)

            section_item = {
                "subtopicId": subtopic.subtopicId,
                "title": subtopic.title,
                "orderIndex": subtopic.orderIndex,
                "learningGoal": subtopic.learningGoal,
                "content": cleaned_content,
                "example": cleaned_example,
                "miniCheckQuestion": content_data.miniCheckQuestion,
                "mcqQuestions": mcq_list
            }
            sections.append(section_item)
            
            # Store embedding chunk
            try:
                chunk_text = f"Skill: {skill_name} | Subtopic: {subtopic.title} | Content: {cleaned_content}"
                store_student_embedding(
                    learning_path_id=learning_path_id,
                    source_type="LESSON",
                    source_ref_id=f"{lesson_id}_{subtopic.subtopicId}",
                    chunk_text=chunk_text
                )
            except Exception:
                pass

        quiz = quiz_future.result()
    
    # Format questions to dict
    questions_list = []
    for q in quiz.questions:
        questions_list.append({
            "id": q.id,
            "subtopicId": q.subtopicId,
            "question": q.question,
            "options": q.options,
            "correctIndex": q.correctIndex,
            "explanation": q.explanation
        })
        
    final_sections = ensure_section_mcqs(sections, skill_name, domain)

    return {
        "lessonTitle": skill_name,
        "sections": final_sections,
        "keyTakeaways": subtopic_titles,
        "quiz": questions_list
    }

def ensure_section_mcqs(sections: list, skill_name: str, domain: str) -> list:
    """
    Guarantees every section in the module has exactly 3 MCQ practice questions with 4 choices.
    """
    if not sections:
        return []
    
    updated_sections = []
    for idx, sec in enumerate(sections):
        s = dict(sec)
        mcqs = list(s.get("mcqQuestions") or [])
        if len(mcqs) < 3:
            title = s.get("title", f"Module {idx + 1}")
            sub_id = s.get("subtopicId", f"sub_{idx + 1}")
            
            fallback_mcqs = [
                {
                    "id": f"{sub_id}_mcq_1",
                    "question": f"What is the core concept and purpose of '{title}' in {domain}?",
                    "options": [
                        f"Establishes essential syntax, patterns, and principles for {title}.",
                        f"Bypasses standard compilation rules and removes runtime safety.",
                        f"A deprecated pattern with no functional application in modern development.",
                        f"Restricts application execution to single-thread static modes only."
                    ],
                    "correctIndex": 0,
                    "explanation": f"{title} provides the foundational structural mechanisms and best practice patterns for {domain}."
                },
                {
                    "id": f"{sub_id}_mcq_2",
                    "question": f"Which approach is recommended when writing code for '{title}'?",
                    "options": [
                        f"Use clear, modular, well-tested functions following best practices.",
                        f"Place all application logic in a single monolithic global script.",
                        f"Disable exception handling to maximize CPU clock speed.",
                        f"Hardcode dynamic database configuration parameters directly in business logic."
                    ],
                    "correctIndex": 0,
                    "explanation": f"Modular code structure and clean architecture represent the industry standard for {domain}."
                },
                {
                    "id": f"{sub_id}_mcq_3",
                    "question": f"How do production engineers prevent common traps in '{title}'?",
                    "options": [
                        f"Implement strict input validation, error handling, and unit test suites.",
                        f"Ignore edge cases because they rarely occur in production environments.",
                        f"Run code without debugging or type checking to save memory overhead.",
                        f"Suppress all system warnings and logging outputs."
                    ],
                    "correctIndex": 0,
                    "explanation": f"Defensive programming and comprehensive test coverage are essential in production {domain} systems."
                }
            ]
            
            while len(mcqs) < 3:
                mcqs.append(fallback_mcqs[len(mcqs)])
            s["mcqQuestions"] = mcqs
            
        updated_sections.append(s)
        
    return updated_sections
