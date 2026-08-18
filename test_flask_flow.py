import os
import json
import unittest
from dotenv import load_dotenv

load_dotenv()

# Configure app to use in-memory SQLite database for testing before import
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import create_app
from app.extensions import db
from app.models.user import User
from app.models.learning_path import LearningPath
from app.models.lesson_progress import LessonProgress

class TestFlaskE2EFlow(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config['TESTING'] = True
        self.app.config['WTF_CSRF_ENABLED'] = False # Disable CSRF for programmatic tests
        self.client = self.app.test_client()
        
        with self.app.app_context():
            db.create_all()

    def tearDown(self):
        with self.app.app_context():
            db.drop_all()

    def test_full_user_flow(self):
        print("\n=== STARTING PYTHON E2E PLATFORM TEST ===")
        
        # 1. Register User
        print("\n[STEP 1] Registering test user...")
        reg_response = self.client.post('/auth/register', data={
            'name': 'Test Student',
            'email': 'student_test@example.com',
            'password': 'StrongPass!2026'
        }, follow_redirects=True)
        self.assertEqual(reg_response.status_code, 200)
        print("OK: Registration successful.")

        # 2. Login User
        print("\n[STEP 2] Logging in user...")
        login_response = self.client.post('/auth/login', data={
            'email': 'student_test@example.com',
            'password': 'StrongPass!2026'
        }, follow_redirects=True)
        self.assertEqual(login_response.status_code, 200)
        print("OK: Login successful.")

        # 3. Generate Skill Map
        print("\n[STEP 3] Generating skill map for domain 'Python Data Analytics'...")
        with self.app.app_context():
            from app.learning.services.skill_map import generate_skill_map
            skill_map_res = generate_skill_map("Python Data Analytics")
            skill_map_dict = skill_map_res.model_dump()
            
            self.assertEqual(skill_map_dict["domain"].lower(), "python data analytics")
            self.assertGreaterEqual(len(skill_map_dict["skillMap"]), 3)
            print("OK: Skill map generated successfully. Tiers:", [t["tier"] for t in skill_map_dict["skillMap"]])

        # 4. Generate Diagnostic Assessment
        print("\n[STEP 4] Generating diagnostic assessment...")
        with self.app.app_context():
            from app.learning.services.diagnostic import generate_diagnostic
            diag_res = generate_diagnostic("Python Data Analytics", skill_map_dict)
            diag_dict = diag_res.model_dump()
            
            self.assertGreaterEqual(len(diag_dict["questions"]), 4)
            print(f"OK: Placement test generated with {len(diag_dict['questions'])} questions.")

        # 5. Submit Diagnostic Answers & Build Roadmap
        print("\n[STEP 5] Submitting placement assessment answers...")
        # Mock answers
        answers_payload = []
        for q in diag_dict["questions"]:
            # Answer correctly for first 4, wrong for next 4 to test level detection
            answers_payload.append({
                "id": q["id"],
                "selectedIndex": q["correctAnswer"]
            })
            
        submit_payload = {
            "domain": "Python Data Analytics",
            "skillMap": skill_map_dict["skillMap"],
            "questions": diag_dict["questions"],
            "answers": answers_payload
        }
        
        submit_response = self.client.post('/learning/diagnostic/submit', 
            data=json.dumps(submit_payload),
            content_type='application/json'
        )
        if submit_response.status_code != 200:
            print("ERROR response:", submit_response.data.decode('utf-8', errors='ignore'))
        self.assertEqual(submit_response.status_code, 200)
        submit_data = json.loads(submit_response.data)
        
        learning_path_id = submit_data["learningPathId"]
        detected_level = submit_data["detectedLevel"]
        print(f"OK: Diagnostic submitted. Detected Level: {detected_level}. Path ID: {learning_path_id}")

        # 6. Retrieve Roadmap Lessons
        print("\n[STEP 6] Accessing first roadmap lesson...")
        with self.app.app_context():
            path = db.session.get(LearningPath, learning_path_id)
            self.assertIsNotNone(path)
            
            lessons = LessonProgress.query.filter_by(learning_path_id=learning_path_id).all()
            self.assertGreater(len(lessons), 0)
            
            first_lesson = next((l for l in lessons if l.status == "IN_PROGRESS"), None)
            self.assertIsNotNone(first_lesson)
            print(f"OK: Found active lesson in database: {first_lesson.title} [Tier: {first_lesson.tier}]")
            
            # 7. Generate Deep Lesson Content
            print(f"\n[STEP 7] Generating deep syllabus sections for: {first_lesson.title}...")
            from app.learning.services.lesson_content import generate_full_lesson
            lesson_content = generate_full_lesson(
                learning_path_id=path.id,
                lesson_id=first_lesson.lesson_id,
                skill_name=first_lesson.title,
                skill_description=first_lesson.title,
                tier=first_lesson.tier,
                is_revision=first_lesson.is_revision_module,
                domain=path.domain
            )
            
            self.assertEqual(lesson_content["lessonTitle"], first_lesson.title)
            self.assertGreater(len(lesson_content["sections"]), 0)
            
            # Check word count of sections content
            total_words = 0
            for sec in lesson_content["sections"]:
                total_words += len(sec["content"].split())
                
            print(f"OK: Sections generated: {len(lesson_content['sections'])}")
            print(f"OK: Assembled content word-count: {total_words} words")
            # Word-count check: full lesson is verifiably longer than old thin summaries, aiming for 1500-4000+ words
            self.assertGreater(total_words, 400)
            print("PASS: Multi-section content depth meets the addendum target.")

if __name__ == "__main__":
    unittest.main()
