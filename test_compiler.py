import os
import unittest
import json
from dotenv import load_dotenv

load_dotenv()
os.environ["DATABASE_URL"] = "sqlite:///:memory:"

from app import create_app
from app.compiler.service import execute_code

class TestCompilerAndPlayground(unittest.TestCase):
    def setUp(self):
        self.app = create_app()
        self.app.config["TESTING"] = True
        self.app.config["WTF_CSRF_ENABLED"] = False
        self.client = self.app.test_client()

    def test_python_local_execution(self):
        print("\n[TEST] Python Execution...")
        code = "print('Hello from Diva AI Compiler!')\nprint(2 + 2)"
        res = execute_code("python", code)
        self.assertTrue(res["success"])
        self.assertEqual(res["exitCode"], 0)
        self.assertIn("Hello from Diva AI Compiler!", res["stdout"])
        self.assertIn("4", res["stdout"])
        self.assertEqual(res["stderr"], "")
        print(f"OK: Python stdout: {res['stdout'].strip()} ({res['executionTimeMs']}ms)")

    def test_python_stdin_execution(self):
        print("\n[TEST] Python Stdin...")
        code = "name = input()\nprint(f'Welcome, {name}!')"
        res = execute_code("python", code, stdin="Ada Lovelace")
        self.assertTrue(res["success"])
        self.assertIn("Welcome, Ada Lovelace!", res["stdout"])
        print(f"OK: Python stdin test passed.")

    def test_python_error_traceback(self):
        print("\n[TEST] Python Runtime Error Handling...")
        code = "def divide(a, b):\n    return a / b\nprint(divide(10, 0))"
        res = execute_code("python", code)
        self.assertFalse(res["success"])
        self.assertNotEqual(res["exitCode"], 0)
        self.assertIn("ZeroDivisionError", res["stderr"])
        print(f"OK: Correctly captured stderr: {res['stderr'].strip()[:60]}...")

    def test_python_timeout_safety(self):
        print("\n[TEST] Execution Timeout Protection...")
        code = "import time\nwhile True:\n    time.sleep(0.1)"
        res = execute_code("python", code)
        self.assertFalse(res["success"])
        self.assertIn("Time Limit Exceeded", res["stderr"])
        print(f"OK: Successfully caught infinite loop with timeout message.")

    def test_sql_in_memory_execution(self):
        print("\n[TEST] SQL In-Memory SQLite Execution...")
        sql = """
        CREATE TABLE users (id INTEGER PRIMARY KEY, username TEXT, score INT);
        INSERT INTO users (username, score) VALUES ('Turing', 100), ('Lovelace', 99);
        SELECT * FROM users WHERE score >= 99 ORDER BY score DESC;
        """
        res = execute_code("sql", sql)
        self.assertTrue(res["success"])
        self.assertEqual(res["exitCode"], 0)
        self.assertIn("Turing", res["stdout"])
        self.assertIn("Lovelace", res["stdout"])
        print(f"OK: SQL execution output:\n{res['stdout'].strip()}")

    def test_javascript_execution(self):
        print("\n[TEST] JavaScript Execution...")
        js_code = "console.log('Hello from JS'); console.log([1,2,3].map(x => x * 10).join(', '));"
        res = execute_code("javascript", js_code)
        self.assertTrue(res["success"])
        self.assertIn("Hello from JS", res["stdout"])
        self.assertIn("10, 20, 30", res["stdout"])
        print(f"OK: JS Output: {res['stdout'].strip()} ({res['executionTimeMs']}ms)")

    def test_cpp_compilation_execution(self):
        print("\n[TEST] C++ Compilation & Execution...")
        cpp_code = """
        #include <iostream>
        int main() {
            std::cout << "C++ Compiler Active: " << (50 * 2) << std::endl;
            return 0;
        }
        """
        res = execute_code("c++", cpp_code)
        self.assertTrue(res["success"])
        self.assertIn("C++ Compiler Active: 100", res["stdout"])
        print(f"OK: C++ Output: {res['stdout'].strip()} ({res['executionTimeMs']}ms)")

    def test_compiler_route_api(self):
        print("\n[TEST] POST /compiler/execute API Endpoint...")
        payload = {
            "language": "python",
            "code": "print('API Endpoint Functional')",
            "stdin": ""
        }
        response = self.client.post(
            "/compiler/execute",
            data=json.dumps(payload),
            content_type="application/json"
        )
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.data)
        self.assertTrue(data["success"])
        self.assertIn("API Endpoint Functional", data["stdout"])
        print(f"OK: Endpoint returned: {data['stdout'].strip()}")

    def test_playground_view_render(self):
        print("\n[TEST] GET /compiler View Template...")
        response = self.client.get("/compiler")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Interactive Code Playground", response.data)
        self.assertIn(b"Python 3", response.data)
        print(f"OK: Playground HTML page rendered successfully.")

if __name__ == "__main__":
    unittest.main()
