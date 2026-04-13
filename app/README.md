# Genorova SaaS MVP

## Folder Structure

```text
app/
  backend/   FastAPI chat API wrapping the existing Genorova backend
  frontend/  React + Tailwind chat interface
  shared/    Shared contracts and notes
```

## Key Endpoints

- `POST /chat`
- `GET /conversations`
- `GET /conversations/{conversation_id}`
- `POST /conversations/new`
- `POST /generate`
- `POST /score`
- `GET /best_molecules`
- `GET /report`

## Run Locally

### Backend

```bash
cd app/backend
python -m pip install -r requirements.txt
python -m uvicorn main:app --reload --port 8000
```

### Frontend

```bash
cd app/frontend
npm install
npm run dev
```

Frontend: `http://localhost:5173`  
Backend: `http://localhost:8000`

The frontend expects the backend to be running before you open the chat UI.

## Render Deployment

### Backend Web Service

- Root directory: `app/backend`
- Build command: `pip install -r requirements.txt`
- Start command: `uvicorn main:app --host 0.0.0.0 --port $PORT`

### Frontend Static Site

- Root directory: `app/frontend`
- Build command: `npm install && npm run build`
- Publish directory: `dist`
- Environment variable: `VITE_API_BASE_URL=https://<your-backend-service>.onrender.com`
