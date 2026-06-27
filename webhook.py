from fastapi import FastAPI, APIRouter, Request, HTTPException, Depends, BackgroundTasks
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
from flows import handle_incoming_message
import logging

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

load_dotenv()

router = APIRouter()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
VERSION = os.getenv("VERSION")
PORT = int(os.getenv("PORT", 8000))


static_path = Path("static")
static_path.mkdir(exist_ok=True)

@router.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks):
    """
    Fast webhook endpoint. Parses the inbound message and hands all routing
    (onboarding, referrals, AI replies) to the background task in flows.py.
    """
    try:
        body = await request.json()

        # Extract contact info
        contact = (
            body.get("entry", [{}])[0]
            .get("changes", [{}])[0]
            .get("value", {})
            .get("contacts", [{}])[0]
        )
        wa_id = contact.get("wa_id")
        name = contact.get("profile", {}).get("name")

        logger.info(f"Webhook received from {wa_id} ({name})")

        # Extract the message (text, interactive, etc.)
        message = (
            body.get("entry", [{}])[0]
            .get("changes", [{}])[0]
            .get("value", {})
            .get("messages", [{}])[0]
        )

        # Only act on real inbound messages from a known sender (ignore status
        # callbacks and empty payloads).
        if wa_id and message.get("type"):
            background_tasks.add_task(handle_incoming_message, wa_id, name, message)
            logger.info(f"Background task queued for {wa_id} (type={message.get('type')})")

        # Return immediately
        return PlainTextResponse('', status_code=200)

    except Exception as e:
        logger.error(f"Webhook error: {str(e)}")
        return PlainTextResponse('', status_code=200)


@router.get("/webhook")
async def verify_webhook(request: Request):
    query_params = request.query_params
    mode = query_params.get("hub.mode")
    token = query_params.get("hub.verify_token")
    challenge = query_params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("Webhook verified successfully!")
        return PlainTextResponse(challenge)
    else:
        raise HTTPException(status_code=403, detail="Verification token mismatch.")


@router.get("/health")
async def health_check():
    """Simple health check endpoint"""
    return {"status": "healthy", "service": "whatsapp-webhook"}


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

# Website REST APIs (feedback CRUD + chatbot)
from api import api_router
app.include_router(api_router)

from sqladmin import Admin
admin = Admin(app, engine)

from db.admin import (
    ProductAdmin, MetalAdmin, LeadAdmin, GroupAdmin, TemplateStorageAdmin,
    ReferralAdmin, FeedbackAdmin, CategoryAdmin, ReviewAdmin, BlogAdmin,
)
admin.add_view(MetalAdmin)
admin.add_view(ProductAdmin)
admin.add_view(CategoryAdmin)
admin.add_view(LeadAdmin)
admin.add_view(GroupAdmin)
admin.add_view(TemplateStorageAdmin)
admin.add_view(ReferralAdmin)
admin.add_view(FeedbackAdmin)
admin.add_view(ReviewAdmin)
admin.add_view(BlogAdmin)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0",port=8000)