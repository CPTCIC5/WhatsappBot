from fastapi import FastAPI, APIRouter, Request, HTTPException, Depends
from fastapi.responses import PlainTextResponse
from starlette.middleware.sessions import SessionMiddleware
import os
from dotenv import load_dotenv
import httpx
from ai import chat_with_assistant
from pathlib import Path
import sqladmin
from fastapi.staticfiles import StaticFiles
import shutil
from db.models import Base, engine, get_db, Lead
from sqlalchemy.orm import Session

load_dotenv()

router = APIRouter()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
VERSION = os.getenv("VERSION")
PORT = int(os.getenv("PORT", 8000))


static_path = Path("static")
static_path.mkdir(exist_ok=True)

@router.post("/webhook")
async def webhook(request: Request, db: Session = Depends(get_db)):
    body = await request.json()
    contact = (
    body.get("entry", [{}])[0]
        .get("changes", [{}])[0]
        .get("value", {})
        .get("contacts", [{}])[0]
)
    wa_id = contact.get("wa_id")
    name = contact.get("profile", {}).get("name")
    print("Incoming webhook message:", body)
    print("User Number", wa_id, "User Name", name)
    if db.query(Lead).filter(Lead.phone == wa_id).first() is None and wa_id is not None:
        from openai import OpenAI
        openai_client = OpenAI()
        # Responses API: one conversation per lead (stored in thread_id)
        new_conv = openai_client.conversations.create()
        new_lead = Lead(phone=wa_id, name=name, thread_id=new_conv.id)
        db.add(new_lead)
        db.commit()
        print(f"New lead created with wa_id: {wa_id}, conversation_id={new_conv.id}")

    message = body.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("messages", [{}])[0]

    if message.get("type") == "text":
        business_phone_number_id = body.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("metadata", {}).get("phone_number_id")
        content = message["text"]["body"]
        lead = db.query(Lead).filter(Lead.phone == wa_id).first()
        response_gpt = chat_with_assistant(lead.id, content) if lead else chat_with_assistant(None, content)
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


app = FastAPI()

# Add session middleware for flash messages in admin
app.add_middleware(SessionMiddleware, secret_key="your-secret-key-here-change-in-production")

sqladmin_static_path = os.path.join(os.path.dirname(sqladmin.__file__), "statics")
for item in os.listdir(sqladmin_static_path):
    src = os.path.join(sqladmin_static_path, item)
    dest = os.path.join(static_path, item)
    if os.path.isdir(src):
        shutil.copytree(src, dest, dirs_exist_ok=True)
    else:
        shutil.copy2(src, dest)

app.mount("/static", StaticFiles(directory="static"), name="static")

media_path = Path("media")
media_path.mkdir(exist_ok=True)
app.mount("/media", StaticFiles(directory="media"), name="media")

Base.metadata.create_all(bind=engine)
app.include_router(router)

from sqladmin import Admin
admin = Admin(app, engine)

from db.admin import ProductAdmin, MetalAdmin, LeadAdmin, GroupAdmin, WhatsAppTemplateAdmin
admin.add_view(MetalAdmin)
admin.add_view(ProductAdmin)
admin.add_view(LeadAdmin)
admin.add_view(GroupAdmin)
admin.add_view(WhatsAppTemplateAdmin)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app)