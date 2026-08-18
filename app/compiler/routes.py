import logging
from flask import Blueprint, render_template, request, jsonify
from flask_login import current_user
from app.extensions import limiter
from app.compiler.service import execute_code, LANGUAGE_ALIASES
from app.learning.services.llm import call_llm_text, LLMGenerationError
from app.learning.services.prompts import get_language_instruction

logger = logging.getLogger(__name__)

compiler_bp = Blueprint("compiler", __name__, url_prefix="/compiler")

# Starter code snippets for popular languages
STARTER_TEMPLATES = {
    "python": '''# Python 3 Playground
def fibonacci(n):
    a, b = 0, 1
    for _ in range(n):
        yield a
        a, b = b, a + b

# Generate first 10 Fibonacci numbers
print("--- Fibonacci Sequence ---")
print(list(fibonacci(10)))

# Test data structures
data = {"language": "Python", "version": "3.11", "status": "Ready"}
print(f"\\nPlatform: {data}")
''',
    "javascript": '''// JavaScript (Node.js) Playground
function calculateStats(numbers) {
    const sum = numbers.reduce((a, b) => a + b, 0);
    const avg = sum / numbers.length;
    return { count: numbers.length, sum, avg };
}

const nums = [12, 45, 68, 23, 89, 90, 34];
console.log("Input:", nums);
console.log("Computed Stats:", calculateStats(nums));
''',
    "typescript": '''// TypeScript Playground
interface User {
    id: number;
    name: string;
    role: "student" | "instructor" | "admin";
}

const users: User[] = [
    { id: 1, name: "Alice", role: "student" },
    { id: 2, name: "Bob", role: "instructor" }
];

users.forEach(u => console.log(`User: ${u.name} (${u.role.toUpperCase()})`));
''',
    "c": '''#include <stdio.h>

int main() {
    printf("Hello from C!\\n");
    
    int arr[] = {10, 20, 30, 40, 50};
    int n = sizeof(arr) / sizeof(arr[0]);
    
    int sum = 0;
    for (int i = 0; i < n; i++) {
        sum += arr[i];
    }
    
    printf("Sum of array elements: %d\\n", sum);
    return 0;
}
''',
    "c++": '''#include <iostream>
#include <vector>
#include <numeric>
#include <algorithm>

int main() {
    std::vector<int> numbers = {5, 2, 8, 1, 9, 3};
    
    std::sort(numbers.begin(), numbers.end());
    
    std::cout << "Sorted Vector: ";
    for (int n : numbers) {
        std::cout << n << " ";
    }
    std::cout << "\\n";
    
    int total = std::accumulate(numbers.begin(), numbers.end(), 0);
    std::cout << "Total Sum: " << total << "\\n";
    return 0;
}
''',
    "java": '''public class Main {
    public static void main(String[] args) {
        System.out.println("=== Java Online Runner ===");
        
        String[] concepts = {"OOP", "Polymorphism", "Generics", "Streams"};
        for (String concept : concepts) {
            System.out.println("Concept: " + concept);
        }
    }
}
''',
    "rust": '''fn main() {
    println!("=== Rust Cargo Runner ===");
    
    let mut numbers = vec![1, 2, 3, 4, 5];
    let squares: Vec<i32> = numbers.iter().map(|&x| x * x).collect();
    
    println!("Original: {:?}", numbers);
    println!("Squared: {:?}", squares);
}
''',
    "go": '''package main

import (
	"fmt"
	"strings"
)

func main() {
	fmt.Println("=== Go Runtime Playground ===")
	
	message := "Concurrent, Fast, and Reliable"
	words := strings.Split(message, ", ")
	
	for i, w := range words {
		fmt.Printf("[%d] %s\\n", i+1, w)
	}
}
''',
    "sql": '''-- In-Memory SQLite SQL Playground
CREATE TABLE students (
    id INTEGER PRIMARY KEY,
    name TEXT NOT NULL,
    domain TEXT NOT NULL,
    mastery_score REAL DEFAULT 0.0
);

INSERT INTO students (name, domain, mastery_score) VALUES 
    ('Ada Lovelace', 'Algorithms', 98.5),
    ('Alan Turing', 'Cryptography', 99.0),
    ('Grace Hopper', 'Compilers', 95.0),
    ('Linus Torvalds', 'Operating Systems', 92.0);

SELECT * FROM students WHERE mastery_score >= 95.0 ORDER BY mastery_score DESC;
'''
}

@compiler_bp.route("", methods=["GET"], strict_slashes=False)
@compiler_bp.route("/", methods=["GET"], strict_slashes=False)
def playground():
    initial_lang = request.args.get("lang", "python").lower()
    initial_lang = LANGUAGE_ALIASES.get(initial_lang, "python")
    code_param = request.args.get("code")
    
    initial_code = code_param if code_param else STARTER_TEMPLATES.get(initial_lang, STARTER_TEMPLATES["python"])
    
    return render_template(
        "compiler/playground.html",
        initial_lang=initial_lang,
        initial_code=initial_code,
        templates=STARTER_TEMPLATES
    )

@compiler_bp.route("/execute", methods=["POST"])
@limiter.limit("30 per minute")
def execute():
    data = request.json or {}
    language = data.get("language", "python")
    code = data.get("code", "")
    stdin = data.get("stdin", "")
    
    if not code or not code.strip():
        return jsonify({
            "stdout": "",
            "stderr": "No code provided to execute.",
            "exitCode": 1,
            "executionTimeMs": 0,
            "success": False
        }), 400
        
    result = execute_code(language, code, stdin)
    return jsonify(result)

@compiler_bp.route("/explain", methods=["POST"])
@limiter.limit("10 per minute")
def explain_error():
    data = request.json or {}
    code = data.get("code", "")[:4000]
    error = data.get("error", "")[:2000]
    language = data.get("language", "python")
    
    if not error:
        return jsonify({"explanation": "No error provided to analyze."}), 400
        
    prompt = f"""You are an expert compiler engineer and computer science tutor.
A student ran this {language} code:
```
{code}
```

And received this compiler/runtime error:
```
{error}
```

Explain what caused this error in plain, encouraging language.
Provide:
1. The root cause in 1-2 intuitive sentences.
2. The exact line or construct causing the failure.
3. The fixed, working code snippet.
{get_language_instruction()}
"""
    try:
        explanation = call_llm_text(prompt, model_type="fast")
        return jsonify({"explanation": explanation})
    except Exception as e:
        logger.exception("AI Explain Error failed: %s", e)
        return jsonify({"explanation": "Could not analyze the error with AI at this time."}), 500
