import os
import sys
import subprocess
from pathlib import Path

def print_step(msg):
    print(f"\n[SETUP] {msg}")
    print("-" * 40)

def setup_env():
    print_step("Checking environment variables...")
    env_path = Path(".env")
    if not env_path.exists():
        print("Creating .env from template...")
        with open(".env", "w") as f:
            f.write("# Finance Analysis Application Configuration\n")
            f.write("DATABASE_URL=sqlite:///./fad.db\n")
            f.write("FAD_USER_DIR=~/.finance-analysis\n")
            f.write("ENVIRONMENT=development\n")
        print("Created .env file. Please review it later for API keys.")
    else:
        print(".env already exists.")

def init_db():
    print_step("Initializing database...")
    # Add project root to sys.path for backend imports
    sys.path.append(os.getcwd())
    
    from backend.database import init_db as db_init
    try:
        db_init()
        print("Database initialized successfully.")
    except Exception as e:
        print(f"Error initializing database: {e}")

def install_deps():
    print_step("Checking dependencies...")
    # Check if poetry or pip should be used
    if Path("poetry.lock").exists():
        print("Poetry detected. Running poetry install...")
        subprocess.run(["poetry", "install"], check=True)
    else:
        print("Falling back to pip install...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-r", "requirements.txt"], check=False)

def setup_frontend():
    print_step("Setting up frontend...")
    frontend_dir = Path("frontend")
    if frontend_dir.exists():
        print("Installing frontend dependencies...")
        subprocess.run(["npm", "install"], cwd=frontend_dir, shell=True, check=True)
        print("Frontend setup complete.")
    else:
        print("Frontend directory not found. Skipping.")

def main():
    print("========================================")
    print("   Finance Analysis App Setup Utility   ")
    print("========================================")
    
    try:
        setup_env()
        # install_deps() # Skip heavy install in this script for now, assume user runs it
        init_db()
        # setup_frontend() # Skip for now, assume user handles it
        
        print("\n[SUCCESS] Setup complete!")
        print("To start the backend: python -m uvicorn backend.main:app --reload")
        print("To start the frontend: cd frontend && npm run dev")
    except Exception as e:
        print(f"\n[ERROR] Setup failed: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
