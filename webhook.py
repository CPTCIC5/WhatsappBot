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
from send_msg import send_txt_msg_async
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

async def process_message_and_respond(wa_id: str, message_from: str, message_id: str, content: str):
    """
    Simple background task to process AI response and send WhatsApp message.
    """
    try:
        logger.info(f"Processing message from {wa_id}: {content[:50]}...")
        
        # Get database session
        db = next(get_db())
        
        try:
            # Get lead and generate AI response
            lead = db.query(Lead).filter(Lead.phone == wa_id).first()
            response_gpt = chat_with_assistant(lead.id, content) if lead else chat_with_assistant(None, content)
            
            logger.info(f"AI response generated for {wa_id}: {response_gpt[:50]}...")
            
            # Send response using async function
            response = await send_txt_msg_async(message_from, response_gpt)
            
            if response.status_code == 200:
                logger.info(f"Message sent successfully to {wa_id}")
            else:
                logger.error(f"Failed to send message to {wa_id}: {response.status_code}")
                
        finally:
            db.close()
        
    except Exception as e:
        logger.error(f"Error processing message for {wa_id}: {str(e)}")


@router.post("/webhook")
async def webhook(request: Request, background_tasks: BackgroundTasks, db: Session = Depends(get_db)):
    """
    Simple, fast webhook endpoint that handles concurrent requests.
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
        
        # Create new lead if doesn't exist or update thread_id if empty
        if wa_id:
            existing_lead = db.query(Lead).filter(Lead.phone == wa_id).first()
            if not existing_lead:
                try:
                    from openai import OpenAI
                    openai_client = OpenAI()
                    new_conv = openai_client.conversations.create()
                    new_lead = Lead(phone=wa_id, name=name, thread_id=new_conv.id)
                    db.add(new_lead)
                    db.commit()
                    logger.info(f"New lead created: {wa_id}")
                except Exception as e:
                    logger.error(f"Error creating lead for {wa_id}: {str(e)}")
            elif not existing_lead.thread_id:
                try:
                    from openai import OpenAI
                    openai_client = OpenAI()
                    new_conv = openai_client.conversations.create()
                    existing_lead.thread_id = new_conv.id
                    db.commit()
                    logger.info(f"Thread ID updated for existing lead: {wa_id}")
                except Exception as e:
                    logger.error(f"Error updating thread_id for {wa_id}: {str(e)}")
        # Extract message
        message = body.get("entry", [{}])[0].get("changes", [{}])[0].get("value", {}).get("messages", [{}])[0]

        if message.get("type") == "text":
            content = message["text"]["body"]
            message_from = message["from"]
            message_id = message["id"]
            
            # Add simple background task
            background_tasks.add_task(
                process_message_and_respond,
                wa_id,
                message_from,
                message_id,
                content
            )
            
            logger.info(f"Background task queued for {wa_id}")

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

from sqladmin import Admin
admin = Admin(app, engine)

from db.admin import ProductAdmin, MetalAdmin, LeadAdmin, GroupAdmin,TemplateStorageAdmin
admin.add_view(MetalAdmin)
admin.add_view(ProductAdmin)
admin.add_view(LeadAdmin)
admin.add_view(GroupAdmin)
admin.add_view(TemplateStorageAdmin)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app)