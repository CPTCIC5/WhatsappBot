from fastapi import FastAPI, APIRouter, Request, HTTPException
from fastapi.responses import PlainTextResponse
import os
from dotenv import load_dotenv
import httpx
from ai import chat_with_assistant

load_dotenv()

router = APIRouter()

VERIFY_TOKEN = os.getenv("VERIFY_TOKEN")
ACCESS_TOKEN = os.getenv("ACCESS_TOKEN")
VERSION = os.getenv("VERSION")
PORT = int(os.getenv("PORT", 8000))

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
app.include_router(router)

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=PORT)