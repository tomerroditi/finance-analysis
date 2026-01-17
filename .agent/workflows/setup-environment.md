---
description: Set up a new environment (install deps, config ports)
---

Use this workflow to initialize a new clone or worktree. It installs dependencies and configures unique ports if running in a parallel worktree.

1. **Install Backend Dependencies**
   Initialize the python environment and install dependencies.
   ```zsh
   python3.12 -m venv .venv
   source .venv/bin/activate
   poetry install
   ```

2. **Install Frontend Dependencies**
   Install node modules.
   ```zsh
   cd frontend && npm install
   ```

3. **Configure Worktree Ports**
   If this is a worktree (folder name not exactly 'finance-analysis'), generate unique ports and configure `.env` files.
   // turbo
   ```zsh
   # check if current directory is the main repo
   CURRENT_DIR=$(basename "$PWD")
   if [[ "$CURRENT_DIR" == "finance-analysis" ]]; then
       echo "Main repository detected. Using default ports (8000/5173)."
   else
       echo "Worktree detected: $CURRENT_DIR"
       
       # Generate a semi-unique offset (0-100) based on directory name checksum
       OFFSET=$(($(cksum <<< "$CURRENT_DIR" | cut -f1 -d ' ') % 100))
       
       BACKEND_PORT=$((8000 + OFFSET))
       FRONTEND_PORT=$((5173 + OFFSET))
       
       echo "Configuring ports:"
       echo "  Backend: $BACKEND_PORT"
       echo "  Frontend: $FRONTEND_PORT"
       
       # Write backend .env
       # Note: We append/overwrite CORS_ORIGINS
       echo "CORS_ORIGINS=http://localhost:$FRONTEND_PORT,http://127.0.0.1:$FRONTEND_PORT" > backend/.env
       
       # Write frontend .env
       echo "PORT=$FRONTEND_PORT" > frontend/.env
       echo "VITE_BACKEND_URL=http://127.0.0.1:$BACKEND_PORT" >> frontend/.env
       
       echo "Environment configuration complete."
       echo "To run backend: poetry run uvicorn backend.main:app --reload --port $BACKEND_PORT"
       echo "To run frontend: npm run dev"
   fi
   ```
