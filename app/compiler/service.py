import sys
import os
import time
import subprocess
import sqlite3
import requests
import logging
from typing import Dict, Any

logger = logging.getLogger(__name__)

# Execution limits
MAX_CODE_LENGTH = 50000
MAX_OUTPUT_LENGTH = 32000
MAX_TIMEOUT_SECONDS = 5.0

# Open multi-language compilation API (Wandbox)
WANDBOX_API_URL = "https://wandbox.org/api/compile.json"

# Language aliases mapping to canonical language names
LANGUAGE_ALIASES = {
    "python": "python",
    "python3": "python",
    "py": "python",
    "javascript": "javascript",
    "js": "javascript",
    "node": "javascript",
    "typescript": "typescript",
    "ts": "typescript",
    "c": "c",
    "cpp": "c++",
    "c++": "c++",
    "cplusplus": "c++",
    "java": "java",
    "rust": "rust",
    "rs": "rust",
    "go": "go",
    "golang": "go",
    "sql": "sql",
    "sqlite": "sql",
    "ruby": "ruby",
    "rb": "ruby",
    "php": "php",
    "bash": "bash",
    "sh": "bash"
}

# Wandbox compiler identifier mapping
WANDBOX_COMPILERS = {
    "c": "gcc-head-c",
    "c++": "gcc-head",
    "rust": "rust-head",
    "go": "go-head",
    "java": "openjdk-head",
    "typescript": "typescript-head",
    "javascript": "nodejs-head",
    "ruby": "ruby-head",
    "php": "php-head",
    "bash": "bash"
}

def execute_code(language: str, code: str, stdin: str = "") -> Dict[str, Any]:
    """
    Main code execution dispatcher.
    Executes Python, JavaScript, and SQL locally for sub-millisecond latency,
    and multi-language compilation (C, C++, Java, Rust, Go, TS) via the open Wandbox engine.
    """
    norm_lang = LANGUAGE_ALIASES.get(language.strip().lower(), "python")
    
    if len(code) > MAX_CODE_LENGTH:
        return {
            "stdout": "",
            "stderr": f"Error: Code size exceeds maximum limit of {MAX_CODE_LENGTH} characters.",
            "exitCode": 1,
            "executionTimeMs": 0,
            "language": norm_lang,
            "version": "1.0",
            "success": False
        }

    start_time = time.time()
    
    if norm_lang == "sql":
        result = _execute_sql_locally(code)
    elif norm_lang == "python":
        result = _execute_python_locally(code, stdin)
    elif norm_lang == "javascript":
        # Execute locally via node if available
        result = _execute_javascript_locally(code, stdin)
    else:
        # Multi-language compilation (C, C++, Java, Rust, Go, TypeScript)
        result = _execute_wandbox(norm_lang, code, stdin)
        
    duration_ms = int((time.time() - start_time) * 1000)
    result["executionTimeMs"] = duration_ms
    result["language"] = norm_lang
    return result

def _execute_python_locally(code: str, stdin: str = "") -> Dict[str, Any]:
    """
    Executes Python in an isolated subprocess with strict timeouts.
    """
    try:
        proc = subprocess.run(
            [sys.executable, "-I", "-c", code],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=MAX_TIMEOUT_SECONDS
        )
        stdout = proc.stdout[:MAX_OUTPUT_LENGTH]
        stderr = proc.stderr[:MAX_OUTPUT_LENGTH]
        exit_code = proc.returncode
        
        return {
            "stdout": stdout,
            "stderr": stderr,
            "exitCode": exit_code,
            "version": f"Python {sys.version.split()[0]}",
            "success": exit_code == 0
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Time Limit Exceeded: Execution exceeded {int(MAX_TIMEOUT_SECONDS)}s limit. Check for infinite loops or blocking inputs.",
            "exitCode": 124,
            "version": f"Python {sys.version.split()[0]}",
            "success": False
        }
    except Exception as e:
        logger.warning("Local python execution error: %s", e)
        return {
            "stdout": "",
            "stderr": f"Execution Error: {str(e)}",
            "exitCode": 1,
            "version": "Python",
            "success": False
        }

def _execute_javascript_locally(code: str, stdin: str = "") -> Dict[str, Any]:
    """
    Executes JavaScript locally via node with timeout.
    """
    try:
        proc = subprocess.run(
            ["node", "-e", code],
            input=stdin,
            capture_output=True,
            text=True,
            timeout=MAX_TIMEOUT_SECONDS
        )
        stdout = proc.stdout[:MAX_OUTPUT_LENGTH]
        stderr = proc.stderr[:MAX_OUTPUT_LENGTH]
        exit_code = proc.returncode
        
        return {
            "stdout": stdout,
            "stderr": stderr,
            "exitCode": exit_code,
            "version": "Node.js",
            "success": exit_code == 0
        }
    except subprocess.TimeoutExpired:
        return {
            "stdout": "",
            "stderr": f"Time Limit Exceeded: Execution exceeded {int(MAX_TIMEOUT_SECONDS)}s limit.",
            "exitCode": 124,
            "version": "Node.js",
            "success": False
        }
    except Exception as e:
        logger.info("Local node execution not available, fallback to Wandbox: %s", e)
        return _execute_wandbox("javascript", code, stdin)

def _execute_sql_locally(sql_script: str) -> Dict[str, Any]:
    """
    Executes SQL statements in an in-memory SQLite database and formats results cleanly.
    """
    try:
        conn = sqlite3.connect(":memory:")
        cursor = conn.cursor()
        
        output_lines = []
        statements = [s.strip() for s in sql_script.split(";") if s.strip()]
        
        for stmt in statements:
            cursor.execute(stmt)
            if cursor.description:
                columns = [desc[0] for desc in cursor.description]
                rows = cursor.fetchall()
                
                output_lines.append(f"Query: {stmt}")
                if not rows:
                    output_lines.append("(0 rows returned)\n")
                    continue
                    
                col_widths = [len(c) for c in columns]
                for row in rows:
                    for i, val in enumerate(row):
                        col_widths[i] = max(col_widths[i], len(str(val)))
                        
                header = " | ".join(c.ljust(col_widths[i]) for i, c in enumerate(columns))
                divider = "-+-".join("-" * col_widths[i] for i in range(len(columns)))
                output_lines.append(header)
                output_lines.append(divider)
                
                for row in rows:
                    row_str = " | ".join(str(val).ljust(col_widths[i]) for i, val in enumerate(row))
                    output_lines.append(row_str)
                output_lines.append(f"({len(rows)} rows)\n")
            else:
                conn.commit()
                changes = conn.total_changes
                output_lines.append(f"Query: {stmt}\n-> Query OK, rows affected: {changes}\n")
                
        conn.close()
        return {
            "stdout": "\n".join(output_lines),
            "stderr": "",
            "exitCode": 0,
            "version": f"SQLite {sqlite3.sqlite_version}",
            "success": True
        }
    except Exception as e:
        return {
            "stdout": "",
            "stderr": f"SQL Error: {str(e)}",
            "exitCode": 1,
            "version": f"SQLite {sqlite3.sqlite_version}",
            "success": False
        }

def _execute_wandbox(language: str, code: str, stdin: str = "") -> Dict[str, Any]:
    """
    Executes multi-language code via Wandbox compilation API.
    """
    compiler = WANDBOX_COMPILERS.get(language, "gcc-head")
    
    payload = {
        "compiler": compiler,
        "code": code,
        "stdin": stdin,
        "save": False
    }
    
    try:
        response = requests.post(WANDBOX_API_URL, json=payload, timeout=12.0)
        if response.status_code == 200:
            data = response.json()
            
            raw_status = data.get("status", "0")
            try:
                exit_code = int(raw_status)
            except (ValueError, TypeError):
                exit_code = 0 if raw_status == "0" else 1
                
            stdout = (data.get("program_output") or "")[:MAX_OUTPUT_LENGTH]
            stderr_parts = []
            
            if data.get("compiler_error"):
                stderr_parts.append(data.get("compiler_error"))
            elif data.get("compiler_message") and exit_code != 0:
                stderr_parts.append(data.get("compiler_message"))
                
            if data.get("program_error"):
                stderr_parts.append(data.get("program_error"))
                
            stderr = "\n".join(stderr_parts)[:MAX_OUTPUT_LENGTH]
            
            # If no program_output but compiler produced message on success
            if not stdout and data.get("program_message") and not stderr:
                stdout = data.get("program_message")
                
            return {
                "stdout": stdout,
                "stderr": stderr,
                "exitCode": exit_code,
                "version": compiler,
                "success": exit_code == 0
            }
        else:
            return {
                "stdout": "",
                "stderr": f"Compilation Service Error ({response.status_code}): {response.text[:200]}",
                "exitCode": 1,
                "version": language,
                "success": False
            }
    except requests.Timeout:
        return {
            "stdout": "",
            "stderr": "Execution Timeout: The remote compiler service timed out.",
            "exitCode": 124,
            "version": language,
            "success": False
        }
    except Exception as e:
        logger.exception("Wandbox API request failed: %s", e)
        return {
            "stdout": "",
            "stderr": f"Compiler Error: {str(e)}",
            "exitCode": 1,
            "version": language,
            "success": False
        }
