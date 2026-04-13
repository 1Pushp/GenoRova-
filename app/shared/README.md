# Shared

This folder is reserved for shared contracts and helpers across the MVP.

Current shared contract:

- `POST /chat`
  - Request: `{ "message": "...", "conversation_id": "optional" }`
  - Response: `{ "conversation_id": "...", "reply": "...", "data": {...} }`
