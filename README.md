Admin Pharma - package ready to deploy to Render.

Structure:
- backend/: FastAPI app (serve static frontend if frontend/dist exists)
- frontend/: React + Vite source (run `npm run build` to create frontend/dist)

Render setup (one web service):
1) Build command:
   cd frontend && npm install && npm run build && cd ../backend && pip install -r requirements.txt

2) Start command:
   cd backend && bash start.sh

Optional: create a small background task on Render or an external cron to ping:
while true; do curl https://<your-service>.onrender.com/api/ping; sleep 180; done

Notes:
- After first run, create an admin user:
  curl -X POST -F "username=admin" -F "password=pass123" https://<your-service>/api/users/create
- The backend will create SQLite DB at backend/data/admin_pharma.db
