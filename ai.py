import re
from openai import OpenAI
from sqlalchemy.orm import Session, joinedload
from dotenv import load_dotenv
import os
import json
from db.models import Product as ProductModel, Metal as MetalModel, Lead as LeadModel, SessionLocal
from pydantic import BaseModel
from send_msg import send_img

load_dotenv()
api = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api)
model = "gpt-5.4"

# Contact for queries the bot can't resolve (big/complex questions).
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "support@ridra.in")

class Product(BaseModel):
    name: str | None = None
    gross_weight: float | None = None
    image_url: str | None = None
    metal_info: str | None = None
    calculated_amount: float | None = None
    description: str | None = None

class Products(BaseModel):
    products: list[Product]

def _products_to_response(products: list[ProductModel]) -> dict:
    """Convert DB product rows to Products schema dict."""
    products_list = [
        Product(
            name=p.name,
            image_url=p.image_url,
            gross_weight=p.gross_weight,
            metal_info=str(p.metal_info) if p.metal_info else None,
            calculated_amount=p.calculated_amount,
            description=p.description,
        )
        for p in products
    ]
    return Products(products=products_list).model_dump()


def get_all_products(db: Session):
    """Get all products from the database"""
    products = db.query(ProductModel).options(joinedload(ProductModel.metal_info)).all()
    return _products_to_response(products)


def get_products_by_name(db: Session, name: str):
    """Get products whose name contains the given string (case-insensitive)."""
    q = (
        db.query(ProductModel)
        .options(joinedload(ProductModel.metal_info))
        .filter(ProductModel.name.ilike(f"%{name}%"))
    )
    return _products_to_response(q.all())


def get_products_by_metal(db: Session, metal: str):
    """Get products by metal type (e.g. Gold, Silver)."""
    q = (
        db.query(ProductModel)
        .options(joinedload(ProductModel.metal_info))
        .join(ProductModel.metal_info)
        .filter(MetalModel.metal.ilike(f"%{metal}%"))
    )
    return _products_to_response(q.all())


def get_products_by_metal_karat(db: Session, karat: str):
    """Get products by metal karat (e.g. 22K, 18K)."""
    q = (
        db.query(ProductModel)
        .options(joinedload(ProductModel.metal_info))
        .join(ProductModel.metal_info)
        .filter(MetalModel.karat.ilike(f"%{karat}%"))
    )
    return _products_to_response(q.all())


def get_products_by_price(
    db: Session,
    *,
    min_price: float | None = None,
    max_price: float | None = None,
    exact_price: float | None = None,
):
    """Get products by price (calculated amount). Pass exact_price, or min_price/max_price, or both."""
    q = (
        db.query(ProductModel)
        .options(joinedload(ProductModel.metal_info))
        .join(ProductModel.metal_info)
    )
    # Use SQL expression for calculated amount: gross_weight * rate_per_gram
    amount = ProductModel.gross_weight * MetalModel.rate_per_gram
    if exact_price is not None:
        q = q.filter(amount.between(exact_price - 0.01, exact_price + 0.01))
    else:
        if min_price is not None:
            q = q.filter(amount >= min_price)
        if max_price is not None:
            q = q.filter(amount <= max_price)
    return _products_to_response(q.all())


def get_products_by_availability(db: Session, available: bool):
    """Get products by availability (boolean column): True = available, False = not available."""
    q = (
        db.query(ProductModel)
        .options(joinedload(ProductModel.metal_info))
        .filter(ProductModel.availability == available)
    )
    return _products_to_response(q.all())


# --- Lead extraction from user message ---

def _normalize_phone(s: str) -> str:
    """Return digits only for consistent storage and lookup."""
    return re.sub(r"\D", "", s)


def _extract_phone_numbers(text: str) -> list[str]:
    """Extract phone-like numbers from text (10+ digits, optionally with + or spaces/dashes)."""
    if not text or not text.strip():
        return []
    # Match sequences of digits, possibly with + prefix or spaces/dashes between digit groups
    raw = re.findall(r"\+?[\d\s\-\.\(\)]{10,}", text)
    normalized = []
    for s in raw:
        n = _normalize_phone(s)
        if len(n) >= 10 and n not in normalized:
            normalized.append(n)
    return normalized


def _extract_name_from_message(text: str) -> str | None:
    """Try to extract a name from the message; return None if not found."""
    if not text or not text.strip():
        return None
    t = text.strip()
    # "name is X", "name: X", "i'm X", "i am X", "my name is X", "this is X"
    for pattern in [
        r"(?:name\s+is|name\s*:)\s*([a-zA-Z][a-zA-Z\s]{0,50}?)(?:\s+\d|\s*$|,)",
        r"(?:i\s*['']?m|i\s+am)\s+([a-zA-Z][a-zA-Z\s]{0,50}?)(?:\s+\d|\s*$|,)",
        r"(?:my\s+name\s+is)\s+([a-zA-Z][a-zA-Z\s]{0,50}?)(?:\s+\d|\s*$|,)",
        r"(?:this\s+is)\s+([a-zA-Z][a-zA-Z\s]{0,50}?)(?:\s+\d|\s*$|,)",
        r"(?:call me|contact)\s+([a-zA-Z][a-zA-Z\s]{0,50}?)(?:\s+\d|\s*$|,)",
    ]:
        m = re.search(pattern, t, re.IGNORECASE)
        if m:
            name = m.group(1).strip()
            if name and len(name) <= 100:
                return name
    return None


def ensure_leads_from_message(db: Session, content: str) -> None:
    """
    If the message contains any phone number that is not in the leads table,
    save it as a new lead. Use extracted name if present, otherwise 'unknown'.
    """
    phones = _extract_phone_numbers(content)
    if not phones:
        return
    name = _extract_name_from_message(content) or "unknown"
    for phone in phones:
        if db.query(LeadModel).filter(LeadModel.phone == phone).first() is not None:
            continue
        try:
            lead = LeadModel(phone=phone, name=name, email=None)
            db.add(lead)
            db.commit()
        except Exception:
            db.rollback()
            # e.g. duplicate from race, or DB constraint
            raise


# Tool definitions for the Responses API (function calling)
PRODUCT_TOOLS = [
    {
        "type": "function",
        "name": "get_all_products",
        "description": "List all products in the store's database. Use this when the user asks to list, show, or get all products.",
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_products_by_name",
        "description": "Search products by name (partial match). Use when the user asks for products with a specific name or keyword.",
        "parameters": {
            "type": "object",
            "properties": {
                "name": {"type": "string", "description": "Product name or keyword to search for."},
            },
            "required": ["name"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_products_by_metal",
        "description": "Get products by metal type (e.g. Gold, Silver).",
        "parameters": {
            "type": "object",
            "properties": {
                "metal": {"type": "string", "description": "Metal type, e.g. Gold or Silver."},
            },
            "required": ["metal"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_products_by_metal_karat",
        "description": "Get products by metal karat (e.g. 22K, 18K).",
        "parameters": {
            "type": "object",
            "properties": {
                "karat": {"type": "string", "description": "Karat e.g. 22K or 18K."},
            },
            "required": ["karat"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_products_by_price",
        "description": "Get products within a price range (min and/or max) or at an exact price.",
        "parameters": {
            "type": "object",
            "properties": {
                "min_price": {"type": ["number", "null"], "description": "Minimum price (optional)."},
                "max_price": {"type": ["number", "null"], "description": "Maximum price (optional)."},
                "exact_price": {"type": ["number", "null"], "description": "Exact price (optional)."},
            },
            "required": ["min_price", "max_price", "exact_price"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "get_products_by_availability",
        "description": "Get products by availability: available=True for in-stock/sellable, available=False for not sellable.",
        "parameters": {
            "type": "object",
            "properties": {
                "available": {"type": "boolean", "description": "True for available/sellable products, False otherwise."},
            },
            "required": ["available"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "send_product_image",
        "description": "Send a product image to the user via WhatsApp. Use when user asks to see an image, photo, or picture of a product.",
        "parameters": {
            "type": "object",
            "properties": {
                "image_url": {"type": "string", "description": "URL of the product image to send."},
                "caption": {"type": "string", "description": "Caption text describing the product (name, price, details)."},
            },
            "required": ["image_url", "caption"],
            "additionalProperties": False,
        },
        "strict": True,
    },
    {
        "type": "function",
        "name": "escalate_to_human",
        "description": (
            "Escalate to a human team member. Use ONLY when the query is large/complex, "
            "needs custom-order or pricing negotiation, a complaint, or anything you cannot "
            "confidently resolve with the product tools. Returns a message that shares the "
            "store's contact email so the customer can reach the team."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "reason": {"type": "string", "description": "Short reason for escalating (internal note)."},
            },
            "required": ["reason"],
            "additionalProperties": False,
        },
        "strict": True,
    },
]


def _handle_tool_call(db: Session, name: str, arguments: dict, user_phone: str | None = None):
    """Execute a product tool and return JSON string result."""
    try:
        if name == "get_all_products":
            out = get_all_products(db)
        elif name == "get_products_by_name":
            out = get_products_by_name(db, arguments["name"])
        elif name == "get_products_by_metal":
            out = get_products_by_metal(db, arguments["metal"])
        elif name == "get_products_by_metal_karat":
            out = get_products_by_metal_karat(db, arguments["karat"])
        elif name == "get_products_by_price":
            out = get_products_by_price(
                db,
                min_price=arguments.get("min_price"),
                max_price=arguments.get("max_price"),
                exact_price=arguments.get("exact_price"),
            )
        elif name == "get_products_by_availability":
            out = get_products_by_availability(db, arguments["available"])
        elif name == "send_product_image":
            if not user_phone:
                out = {"success": False, "error": "User phone number not available"}
            else:
                response = send_img(
                    user_contact_number=user_phone,
                    link=arguments["image_url"],
                    caption=arguments["caption"]
                )
                if response.status_code == 200:
                    out = {"success": True, "message": "Image sent successfully", "response": response.json()}
                else:
                    out = {"success": False, "error": f"Failed to send image: {response.status_code}", "response": response.json()}
        elif name == "escalate_to_human":
            out = {
                "escalated": True,
                "message": (
                    f"This one is best handled by our team 💎 Please email us at {CONTACT_EMAIL} "
                    "with your question and we'll get right back to you. You can keep chatting "
                    "here for anything else!"
                ),
            }
        else:
            out = {"error": f"Unknown tool: {name}"}
        return json.dumps(out, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def chat_with_assistant(lead_id: int | None, content: str) -> str:
    """Chat with the assistant; product tools are called automatically. Uses conversation in lead.thread_id when lead_id is set."""
    db = SessionLocal()
    try:
        ensure_leads_from_message(db, content)

        # Get user phone from lead
        user_phone: str | None = None
        if lead_id is not None:
            lead = db.query(LeadModel).filter(LeadModel.id == lead_id).first()
            if lead:
                user_phone = lead.phone

        developer_instruction = (
            "You're a friendly jewelry shop representative helping customers discover beautiful pieces. Your goal is marketing and awareness, not aggressive selling.\n\n"
            "CONVERSATION STYLE:\n"
            "- Keep messages short and WhatsApp-friendly (2-3 sentences max)\n"
            "- Use emojis naturally ✨💎\n"
            "- Sound human, never robotic or AI-like\n"
            "- Match their energy and communication style\n"
            "- Ask engaging questions to keep conversation flowing\n\n"
            "APPROACH:\n"
            "1. Build rapport first - be genuinely interested in their needs\n"
            "2. If someone asks about pricing too early, redirect to understanding their needs first\n"
            "3. Ask about their jewelry preferences, occasions, style\n"
            "4. Share relevant products based on their interests\n"
            "5. Focus on helping them explore and learn about jewelry\n"
            "6. If they seem interested, gently guide toward visiting the store\n\n"
            "EMOTIONAL SELLING PHILOSOPHY:\n"
            "Jewelry is NOT a need product - it's an EMOTION product. Nobody 'needs' a diamond ring, they need what it represents.\n\n"
            "SELL THE STORY, NOT THE SPECS:\n"
            "- Engagement Ring → 'Your forever story begins here' (not '22kt gold, 5.6 grams')\n"
            "- Bridal Jewelry → 'A mother's dream, father's pride, daughter's new beginning'\n"
            "- Self-Purchase → 'You deserve this celebration of your success'\n"
            "- Anniversary → 'Every year of love deserves to shine'\n\n"
            "FORMULA: Honest Pricing + Emotional Story = Trust + Desire\n"
            "- Emotion creates higher budget tolerance and less price sensitivity\n"
            "- Transparent pricing builds trust\n"
            "- Together they create conversion and loyalty\n\n"
            "PRODUCT TOOLS:\n"
            "- Use tools to find products matching their emotional needs\n"
            "- When showing products, focus on the life moment it represents\n"
            "- Send images when they want to see something specific\n"
            "- Keep descriptions about feelings and occasions, not just specifications\n\n"
            "RESOLVING QUERIES (Milestone 3):\n"
            "- Prefer short, predefined-style answers. Resolve small/common questions yourself "
            "(rates, availability, store info, product details) using the tools.\n"
            "- If a query is big, complex, or open-ended (custom orders, pricing negotiation, "
            "complaints, anything you can't confidently resolve), call escalate_to_human and "
            "relay its message so they can email the team. Do NOT invent answers.\n\n"
            "Remember: You're here to help them discover jewelry that tells their story. Connect pieces to their emotions and life moments."
        )
        tools = [{"type": "web_search", "filters": {"allowed_domains": ["ridra.in"]}}] + PRODUCT_TOOLS

        # Resolve conversation id from lead (Responses API conversation stored in thread_id)
        conversation_id: str | None = None
        if lead_id is not None:
            lead = db.query(LeadModel).filter(LeadModel.id == lead_id).first()
            if lead and lead.thread_id:
                conversation_id = lead.thread_id
            elif lead:
                # Old lead without thread_id: create conversation and persist
                new_conv = client.conversations.create()
                conversation_id = new_conv.id
                lead.thread_id = new_conv.id
                db.commit()

        # With conversation: pass only new user message; API prepends conversation history.
        # Without: build full input list so tool-call rounds keep context.
        if conversation_id:
            input_list = [{"role": "user", "content": content}]
        else:
            input_list = [
                {"role": "developer", "content": developer_instruction},
                {"role": "user", "content": content},
            ]
        create_kw: dict = {
            "model": model,
            "instructions": developer_instruction if conversation_id else None,
            "input": input_list,
            "tools": tools,
        }
        if conversation_id:
            create_kw["conversation"] = conversation_id
        if create_kw["instructions"] is None:
            del create_kw["instructions"]

        max_rounds = 5
        resp = None
        for _ in range(max_rounds):
            resp = client.responses.create(**create_kw)
            has_tool_call = False
            tool_outputs = []
            for item in resp.output:
                if getattr(item, "type", None) != "function_call":
                    continue
                has_tool_call = True
                name = getattr(item, "name", None)
                call_id = getattr(item, "call_id", None)
                arguments_raw = getattr(item, "arguments", None) or "{}"
                try:
                    arguments = json.loads(arguments_raw) if isinstance(arguments_raw, str) else arguments_raw
                except json.JSONDecodeError:
                    arguments = {}
                result = _handle_tool_call(db, name, arguments, user_phone)
                tool_outputs.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": result,
                })
            if not has_tool_call:
                return resp.output_text or ""
            if conversation_id:
                create_kw["input"] = tool_outputs
            else:
                create_kw["input"] = input_list + list(resp.output) + tool_outputs
                input_list = create_kw["input"]
        return (resp.output_text or "") if resp else ""
    finally:
        db.close()


# --- Website chatbot (session-based, no WhatsApp) ---------------------------

WEB_INSTRUCTION = (
    "You are the website assistant for *Ridra Jewellers*. Answer visitors' basic "
    "queries clearly and concisely (2-4 sentences).\n\n"
    "- Use the product tools to look up items by name, metal, karat, price, or "
    "availability, and share accurate details.\n"
    "- Be warm and helpful; focus on the occasion and story behind the jewelry.\n"
    "- For big/complex requests (custom orders, negotiations, complaints) or "
    f"anything you can't resolve, call escalate_to_human (shares {CONTACT_EMAIL}).\n"
    "- Never invent product or price details."
)

# Web chat reuses the product query tools but not WhatsApp image sending.
WEB_TOOLS = [t for t in PRODUCT_TOOLS if t.get("name") != "send_product_image"]


def chat_web(message: str, session_id: str | None = None) -> tuple[str, str]:
    """Website chatbot. Session is stateless: `session_id` is the OpenAI
    conversation id. Returns (reply_text, session_id).

    Pass session_id=None on the first message; the returned session_id should be
    sent back on subsequent messages to keep conversation context.
    """
    # Resolve or create the conversation that backs this session.
    conversation_id = session_id
    if not conversation_id:
        conversation_id = client.conversations.create().id

    tools = [{"type": "web_search", "filters": {"allowed_domains": ["ridra.in"]}}] + WEB_TOOLS

    db = SessionLocal()
    try:
        create_kw: dict = {
            "model": model,
            "instructions": WEB_INSTRUCTION,
            "input": [{"role": "user", "content": message}],
            "tools": tools,
            "conversation": conversation_id,
        }

        max_rounds = 5
        resp = None
        for _ in range(max_rounds):
            resp = client.responses.create(**create_kw)
            tool_outputs = []
            for item in resp.output:
                if getattr(item, "type", None) != "function_call":
                    continue
                name = getattr(item, "name", None)
                call_id = getattr(item, "call_id", None)
                arguments_raw = getattr(item, "arguments", None) or "{}"
                try:
                    arguments = json.loads(arguments_raw) if isinstance(arguments_raw, str) else arguments_raw
                except json.JSONDecodeError:
                    arguments = {}
                # No user_phone on the web → product image sending is disabled.
                result = _handle_tool_call(db, name, arguments, user_phone=None)
                tool_outputs.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": result,
                })
            if not tool_outputs:
                return (resp.output_text or ""), conversation_id
            create_kw["input"] = tool_outputs
        return ((resp.output_text or "") if resp else ""), conversation_id
    finally:
        db.close()
