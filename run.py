import os
import sys

# Automatically detect and use the project's virtual environment packages if running via global Python
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
venv_site_packages = os.path.join(BASE_DIR, ".venv", "Lib", "site-packages")
if os.path.exists(venv_site_packages) and venv_site_packages not in sys.path:
    sys.path.insert(0, venv_site_packages)

# Load environment variables before app creation
try:
    from dotenv import load_dotenv
    load_dotenv(os.path.join(BASE_DIR, ".env"))
except ImportError:
    env_file = os.path.join(BASE_DIR, ".env")
    if os.path.exists(env_file):
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    os.environ.setdefault(k.strip(), v.strip().strip("\"'"))

from app import create_app

app = create_app()

if __name__ == "__main__":
    port_str = os.environ.get("PORT", "5001").strip("\"' \t\n\r")
    try:
        port = int(port_str)
    except ValueError:
        port = 5001

    print("\n" + "=" * 60)
    print("  [*] Diva AI Education Platform is starting!")
    print(f"  -> Localhost:  http://localhost:{port}/")
    print(f"  -> Loopback:   http://127.0.0.1:{port}/")
    print(f"  -> Compiler:   http://localhost:{port}/compiler/")
    print(f"  -> Dashboard:  http://localhost:{port}/learning/dashboard")
    print("=" * 60 + "\n")

    app.run(host="0.0.0.0", port=port, debug=True)
