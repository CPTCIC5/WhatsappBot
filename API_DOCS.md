# Ridra Jewellers — Website API Reference

REST APIs for the catalogue website (feedback, chatbot, categories, reviews, blogs).

## Conventions

- **Base URL:** `https://<host>` (local dev tunnel: `https://monitor-happy-mole.ngrok-free.app`)
- All endpoints are prefixed with **`/api`**.
- Request bodies are **JSON** (`Content-Type: application/json`) **except endpoints that accept image uploads** (Items, Blogs create/update), which use **`multipart/form-data`**. Responses are always JSON.
- **Images:** uploads go to Azure Blob Storage. Responses return **time-limited signed (SAS) URLs** (valid ~1 year, regenerated on every read). Don't cache image URLs long-term — re-fetch the resource to get a fresh URL. Allowed types: `jpeg, png, webp, gif`.
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

## 3. Categories — `/api/categories`  *(create/update use form-data)*

Item categories (an item can belong to many). Each category can have an image.

### Object (response)

| Field | Type | Notes |
|-------|------|-------|
| `id` | int | read-only |
| `name` | string | required, 1–120 chars |
| `image_url` | string \| null | signed URL of the category image (or `null`) |

### Endpoints

| Method | Path | Body | Description |
|--------|------|------|-------------|
| `POST` | `/api/categories` | `multipart/form-data` | Create → `201` |
| `GET` | `/api/categories` | — | List (`skip`=0, `limit`=100/max 500; by name) |
| `GET` | `/api/categories/{id}` | — | Get one |
| `PATCH` | `/api/categories/{id}` | `multipart/form-data` | Update |
| `DELETE` | `/api/categories/{id}` | — | Delete → `204` (also deletes image) |

**Form fields:** `name` (text), `image` (file, optional).

```js
const fd = new FormData();
fd.append("name", "Rings");
fd.append("image", fileInput.files[0]);   // optional
await fetch("/api/categories", { method: "POST", body: fd });
```

```json
{ "id": 3, "name": "Rings", "image_url": "https://ridra.blob.core.windows.net/catalogue-images/categories/...jpg?<sas>" }
```

> Linking categories to items is done on the item (`category_ids` in the Items API) or in the admin Product form.

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

## 5. Blogs — `/api/blogs`  *(create/update use form-data)*

### Object (response)

| Field | Type | Notes |
|-------|------|-------|
| `id` | int | read-only |
| `heading` | string | required, 1–200 chars |
| `description` | string \| null | optional |
| `image_url` | string \| null | signed URL of the cover image (or `null`) |
| `created_at` | datetime | read-only |

### Endpoints

| Method | Path | Body | Description |
|--------|------|------|-------------|
| `POST` | `/api/blogs` | `multipart/form-data` | Create → `201` |
| `GET` | `/api/blogs` | — | List (`skip`=0, `limit`=50/max 200; newest first) |
| `GET` | `/api/blogs/{id}` | — | Get one |
| `PATCH` | `/api/blogs/{id}` | `multipart/form-data` | Update (send only fields you change) |
| `DELETE` | `/api/blogs/{id}` | — | Delete → `204` (also deletes the image) |

**Form fields (POST/PATCH):** `heading` (text), `description` (text, optional), `image` (file, optional).

```js
const fd = new FormData();
fd.append("heading", "Festive Collection 2026");
fd.append("description", "Our new Diwali drop ...");
fd.append("image", fileInput.files[0]);   // optional
await fetch("/api/blogs", { method: "POST", body: fd });
```

```json
{
  "heading": "Festive Collection 2026",
  "description": "Our new Diwali drop ...",
  "id": 4,
  "image_url": "https://ridra.blob.core.windows.net/catalogue-images/blogs/ab12...jpg?<sas>",
  "created_at": "2026-06-28T10:00:00.000000"
}
```

> Don't set `Content-Type` manually when sending `FormData` — the browser adds the multipart boundary.

---

## 6. Items (Products) — `/api/items`  *(create/update use form-data)*

Catalogue items with multiple images.

### Object (response)

| Field | Type | Notes |
|-------|------|-------|
| `id` | int | read-only |
| `name` | string | |
| `style_no` | string \| null | |
| `jewel_code` | string \| null | SKU code |
| `description` | string \| null | |
| `gross_weight` | number \| null | grams |
| `availability` | bool | |
| `metal_id` | int \| null | |
| `metal` | object \| null | `{ id, metal, karat, rate_per_gram }` |
| `calculated_amount` | number | `gross_weight × metal.rate_per_gram` (₹) |
| `categories` | array | `[{ id, name, image_url }]` |
| `images` | array | `[{ id, url }]` — `url` is a signed URL; `id` is used to delete an image (`null` for the legacy admin image) |
| `reviews` | array | `[{ id, product_id, rating, name, email, description, created_at }]` |

### Endpoints

| Method | Path | Body | Description |
|--------|------|------|-------------|
| `POST` | `/api/items` | `multipart/form-data` | Create → `201` |
| `GET` | `/api/items` | — | List (filters below) |
| `GET` | `/api/items/{id}` | — | Get one |
| `PATCH` | `/api/items/{id}` | `multipart/form-data` | Update (partial; new images are **appended**) |
| `DELETE` | `/api/items/{id}` | — | Delete item + all its images → `204` |
| `DELETE` | `/api/items/{id}/images/{image_id}` | — | Remove a single image → `204` |

**List query params:** `name` (partial match), `metal` (e.g. `Gold`), `category_id`, `available` (`true`/`false`), `skip` (0), `limit` (50/max 200).

**Form fields (POST/PATCH):**

| Field | Type | Notes |
|-------|------|-------|
| `name` | text | required on create |
| `style_no`, `jewel_code`, `description` | text | optional |
| `gross_weight` | number | optional |
| `metal_id` | int | optional; must exist (else `400`) |
| `availability` | bool | `true`/`false` (default `true`) |
| `category_ids` | int (repeatable) | repeat the field per category; all must exist (else `400`) |
| `images` | file (repeatable) | repeat the field per image |

```js
const fd = new FormData();
fd.append("name", "Rose Gold Necklace");
fd.append("metal_id", "1");
fd.append("gross_weight", "8.5");
fd.append("category_ids", "1");
fd.append("category_ids", "3");          // multiple categories
fd.append("images", file1);
fd.append("images", file2);              // multiple images
await fetch("/api/items", { method: "POST", body: fd });
```

```json
{
  "id": 12,
  "name": "Rose Gold Necklace",
  "style_no": null,
  "jewel_code": null,
  "description": null,
  "gross_weight": 8.5,
  "availability": true,
  "metal_id": 1,
  "metal": { "id": 1, "metal": "Gold", "karat": "22K", "rate_per_gram": 6000 },
  "calculated_amount": 51000.0,
  "categories": [{ "id": 1, "name": "Necklaces" }],
  "images": [
    { "id": 7, "url": "https://ridra.blob.core.windows.net/catalogue-images/products/...jpg?<sas>" }
  ],
  "reviews": [
    { "id": 3, "product_id": 12, "rating": 4.5, "name": "Asha", "email": null, "description": "Lovely", "created_at": "2026-07-05T10:00:00" }
  ]
}
```

> **Adding images to an existing item:** `PATCH /api/items/{id}` with `images` files — they're appended.
> **Removing one image:** take the image's `id` from the `images` array, then `DELETE /api/items/{id}/images/{image_id}`.

---

## Interactive docs

FastAPI auto-generates live, try-it-out docs while the server is running:

- **Swagger UI:** `GET /docs`
- **ReDoc:** `GET /redoc`
- **OpenAPI JSON:** `GET /openapi.json` (import into Postman / codegen)

---

## Not yet available

These appear in the design but have no REST API yet — ping the backend if the frontend needs them:

- `/api/referral/{user_id}` + the `/referral/{username}` web forum (wa.me intent flow).
