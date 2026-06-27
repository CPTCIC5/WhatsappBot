# Ridra Jewellers — Website API Reference

REST APIs for the catalogue website (feedback, chatbot, categories, reviews, blogs).

## Conventions

- **Base URL:** `https://<host>` (local dev tunnel: `https://monitor-happy-mole.ngrok-free.app`)
- All endpoints are prefixed with **`/api`**.
- Request and response bodies are **JSON** (`Content-Type: application/json`).
- Timestamps are ISO-8601 UTC strings (e.g. `2026-06-27T18:13:18.831614`).
- No authentication is required on these endpoints (the admin panel at `/admin` is separate).
- Trailing slash: endpoints are written **without** a trailing slash (e.g. `POST /api/feedback`). The chatbot accepts both `/api/chat` and `/api/chat/`.

### Status codes

| Code | Meaning |
|------|---------|
| `200` | OK (GET / PATCH) |
| `201` | Created (POST) |
| `204` | No Content (DELETE — empty body) |
| `400` | Bad request (e.g. referenced product doesn't exist) |
| `404` | Resource not found |
| `422` | Validation error (bad/missing fields) — see error shape below |
| `502` | Chatbot temporarily unavailable |

### Validation error shape (`422`)

FastAPI returns field-level detail:

```json
{
  "detail": [
    { "type": "string_too_short", "loc": ["body", "name"], "msg": "String should have at least 1 character" }
  ]
}
```

### Other error shape (`400` / `404` / `502`)

```json
{ "detail": "Feedback not found" }
```

---

## 1. Feedback — `/api/feedback`

Customer feedback from the feedback forum.

### Object

| Field | Type | Notes |
|-------|------|-------|
| `id` | int | read-only |
| `name` | string | required, 1–120 chars |
| `phone` | string | required, 6–20 chars |
| `experience` | enum | required — `happy` \| `medium` \| `sad` |
| `feedback_type` | enum | required — `product_purchased` \| `staff_experience` \| `activities` |
| `product_id` | int \| null | optional; must reference an existing item if provided |
| `description` | string \| null | optional |
| `created_at` | datetime | read-only |

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/feedback` | Create feedback → `201` |
| `GET` | `/api/feedback` | List feedback |
| `GET` | `/api/feedback/{id}` | Get one |
| `PATCH` | `/api/feedback/{id}` | Update (partial allowed) |
| `DELETE` | `/api/feedback/{id}` | Delete → `204` |

**List query params:** `skip` (default `0`), `limit` (default `50`, max `200`), `experience`, `feedback_type`. Sorted newest first.

**Create example**

```http
POST /api/feedback
Content-Type: application/json

{
  "name": "Asha",
  "phone": "9876543210",
  "experience": "happy",
  "feedback_type": "product_purchased",
  "product_id": 1,
  "description": "Loved the necklace!"
}
```

**Response `201`**

```json
{
  "name": "Asha",
  "phone": "9876543210",
  "experience": "happy",
  "feedback_type": "product_purchased",
  "product_id": 1,
  "description": "Loved the necklace!",
  "id": 12,
  "created_at": "2026-06-27T18:13:18.831614"
}
```

> `product_id` referencing a non-existent item → `400 {"detail": "Product 999 not found"}`.

---

## 2. Website Chatbot — `/api/chat/`

Session-based assistant for basic catalogue queries. **Sessions are stateless from the
backend's view: the `session_id` is the conversation token.**

- On the **first** message, omit `session_id`. The response returns a `session_id`.
- On **every following** message, send back that same `session_id` to keep context.
- Persist `session_id` client-side (e.g. in memory / sessionStorage) for the chat widget's lifetime.

### Endpoint

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/chat` (or `/api/chat/`) | Send a message, get a reply |

**Request**

| Field | Type | Notes |
|-------|------|-------|
| `message` | string | required, non-empty |
| `session_id` | string \| null | omit on first message; reuse afterwards |

**Response**

| Field | Type | Notes |
|-------|------|-------|
| `session_id` | string | store and resend on the next message |
| `reply` | string | assistant's answer |

**First message**

```http
POST /api/chat
Content-Type: application/json

{ "message": "Do you have gold rings under 50000?" }
```

```json
{
  "session_id": "conv_abc123",
  "reply": "Yes! We have a few lovely 22K gold rings in that range ✨ ..."
}
```

**Follow-up**

```http
POST /api/chat
Content-Type: application/json

{ "message": "What about in silver?", "session_id": "conv_abc123" }
```

> Empty `message` → `422`. Backend/AI failure → `502 {"detail": "Chatbot is temporarily unavailable"}`.

---

## 3. Categories — `/api/categories`

Item categories (an item can belong to many; categories can be added freely).

### Object

| Field | Type | Notes |
|-------|------|-------|
| `id` | int | read-only |
| `name` | string | required, 1–120 chars |

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/categories` | Create → `201` |
| `GET` | `/api/categories` | List (params: `skip`=0, `limit`=100/max 500; sorted by name) |
| `GET` | `/api/categories/{id}` | Get one |
| `PATCH` | `/api/categories/{id}` | Update |
| `DELETE` | `/api/categories/{id}` | Delete → `204` |

```http
POST /api/categories
{ "name": "Rings" }
```

```json
{ "name": "Rings", "id": 3 }
```

> Linking categories to items is currently managed in the admin panel (Product form). If you need a public endpoint to attach/detach categories on an item, ask and we'll add it.

---

## 4. Reviews — `/api/reviews`

Customer reviews tied to an item.

### Object

| Field | Type | Notes |
|-------|------|-------|
| `id` | int | read-only |
| `product_id` | int | required; must reference an existing item |
| `rating` | number | required; `0`–`5` (decimals allowed, e.g. `4.5`) |
| `name` | string | required, 1–120 chars |
| `email` | string \| null | optional |
| `description` | string \| null | optional |
| `created_at` | datetime | read-only |

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/reviews` | Create → `201` |
| `GET` | `/api/reviews` | List |
| `GET` | `/api/reviews/{id}` | Get one |
| `PATCH` | `/api/reviews/{id}` | Update (partial; `product_id` is not changeable here) |
| `DELETE` | `/api/reviews/{id}` | Delete → `204` |

**List query params:** `product_id` (filter to one item), `skip` (default `0`), `limit` (default `50`, max `200`). Sorted newest first.

```http
POST /api/reviews
{
  "product_id": 1,
  "rating": 4.5,
  "name": "Asha",
  "email": "asha@example.com",
  "description": "Beautiful craftsmanship"
}
```

```json
{
  "product_id": 1,
  "rating": 4.5,
  "name": "Asha",
  "email": "asha@example.com",
  "description": "Beautiful craftsmanship",
  "id": 7,
  "created_at": "2026-06-27T18:20:00.000000"
}
```

> `rating` outside 0–5 → `422`. Unknown `product_id` → `400`.
> To show reviews on a product page: `GET /api/reviews?product_id=1`.

---

## 5. Blogs — `/api/blogs`

### Object

| Field | Type | Notes |
|-------|------|-------|
| `id` | int | read-only |
| `heading` | string | required, 1–200 chars |
| `description` | string \| null | optional |
| `created_at` | datetime | read-only |

### Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `POST` | `/api/blogs` | Create → `201` |
| `GET` | `/api/blogs` | List (params: `skip`=0, `limit`=50/max 200; sorted newest first) |
| `GET` | `/api/blogs/{id}` | Get one |
| `PATCH` | `/api/blogs/{id}` | Update |
| `DELETE` | `/api/blogs/{id}` | Delete → `204` |

```http
POST /api/blogs
{ "heading": "Festive Collection 2026", "description": "Our new Diwali drop ..." }
```

---

## Interactive docs

FastAPI auto-generates live, try-it-out docs while the server is running:

- **Swagger UI:** `GET /docs`
- **ReDoc:** `GET /redoc`
- **OpenAPI JSON:** `GET /openapi.json` (import into Postman / codegen)

---

## Not yet available

These appear in the design but have no REST API yet — ping the backend if the frontend needs them:

- `GET/POST /api/items` — items/products CRUD (managed via admin panel for now).
- `/api/referral/{user_id}` + the `/referral/{username}` web forum (wa.me intent flow).
