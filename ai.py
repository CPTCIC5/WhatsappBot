from openai import OpenAI
from sqlalchemy.orm import Session, joinedload
from dotenv import load_dotenv
import os
import json
from db.models import Product as ProductModel, Metal as MetalModel, SessionLocal
from pydantic import BaseModel

load_dotenv()
api = os.getenv("OPENAI_API_KEY")
client = OpenAI(api_key=api)
model = "gpt-5"

class Product(BaseModel):
    style_no: str | None = None
    jewel_code: str | None = None
    name: str | None = None
    gross_weight: float | None = None
    metal_info: str | None = None
    calculated_amount: float | None = None
    description: str | None = None

class Products(BaseModel):
    products: list[Product]

def _products_to_response(products: list[ProductModel]) -> dict:
    """Convert DB product rows to Products schema dict."""
    products_list = [
        Product(
            style_no=p.style_no,
            jewel_code=p.jewel_code,
            name=p.name,
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
]


def _handle_tool_call(db: Session, name: str, arguments: dict):
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
        else:
            out = {"error": f"Unknown tool: {name}"}
        return json.dumps(out, default=str)
    except Exception as e:
        return json.dumps({"error": str(e)})


def chat_with_assistant(content: str) -> str:
    """Chat with the assistant; product tools are called automatically when the user asks for product data."""
    db = SessionLocal()
    try:
        developer_instruction = (
            "You are a helpful store assistant. You have access to this store's product database. "
            "When the user asks to list, show, or get products (e.g. 'list me all the products'), use the get_all_products tool to fetch data from the database, then summarize the results for the user. "
            "You can also search by name, metal, karat, price, or availability using the other product tools. "
            "Reply in a friendly, concise way. Do not ask which brand or store—you are this store's assistant."
        )
        input_list = [
            {"role": "developer", "content": developer_instruction},
            {"role": "user", "content": content},
        ]
        tools = [{"type": "web_search", "filters": {"allowed_domains": ["ridra.in"]}}] + PRODUCT_TOOLS

        max_rounds = 5
        for _ in range(max_rounds):
            resp = client.responses.create(
                model=model,
                input=input_list,
                tools=tools,
            )
            # Append full response output (e.g. reasoning, function_call) so the model can continue
            input_list += list(resp.output)

            has_tool_call = False
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
                result = _handle_tool_call(db, name, arguments)
                input_list.append({
                    "type": "function_call_output",
                    "call_id": call_id,
                    "output": result,
                })

            if not has_tool_call:
                return resp.output_text or ""

        return resp.output_text or ""
    finally:
        db.close()



# x1= input("Enter the content: ")
# print(chat_with_assistant(x1))