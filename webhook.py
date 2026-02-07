from fastapi import FastAPI, APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse
import os
from dotenv import load_dotenv
import httpx
from ai import chat_with_assistant
from pathlib import Path
import sqladmin
from fastapi.staticfiles import StaticFiles
import shutil
from db.models import Base, engine

load_dotenv()

router = APIRouter()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
VERSION = os.getenv("VERSION")
PORT = int(os.getenv("PORT", 8000))


static_path = Path("static")
static_path.mkdir(exist_ok=True)

@router.post("/webhook")
async def webhook(request: Request):
    body = await request.json()
    print("Incoming webhook message:", body)

    message = body.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("messages", [{}])[0]

    if message.get("type") == "text":
        business_phone_number_id = body.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("metadata", {}).get("phone_number_id")
        content = message["text"]["body"]
        response_gpt = chat_with_assistant(content)
        print(response_gpt, 'xyz')

        reply_data = {
            "messaging_product": "whatsapp",
            "to": message["from"],
            "text": {"body": response_gpt},
            "context": {"message_id": message["id"]},
        }

        async with httpx.AsyncClient() as client:
            await client.post(
                f"https://graph.facebook.com/{VERSION}/{business_phone_number_id}/messages",
                headers={"Authorization": f"Bearer {ACCESS_TOKEN}"},
                json=reply_data
            )

    return PlainTextResponse('', status_code=200)


@router.get("/webhook")
async def verify_webhook(request: Request):
    query_params = request.query_params
    mode = query_params.get("hub.mode")
    token = query_params.get("hub.verify_token")
    challenge = query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        print("Webhook verified successfully!")
        return PlainTextResponse(challenge)
    else:
        raise HTTPException(status_code=403, detail="Verification token mismatch.")


# ✅ Proper app setup
app = FastAPI()

sqladmin_static_path = os.path.join(os.path.dirname(sqladmin.__file__), "statics")
for item in os.listdir(sqladmin_static_path):
    src = os.path.join(sqladmin_static_path, item)
    dest = os.path.join(static_path, item)
    if os.path.isdir(src):
        shutil.copytree(src, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dest)

# Mount your static directory
app.mount("/static", StaticFiles(directory="static"), name="static")

media_path = Path("media")
media_path.mkdir(exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")

Base.metadata.create_all(bind=engine)
app.include_router(router)

from sqladmin import Admin
admin = Admin(app, engine)

from db.admin import ProductAdmin
admin.add_view(ProductAdmin)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app)