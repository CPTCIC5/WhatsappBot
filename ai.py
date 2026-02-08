from openai import OpenAI
from sqlalchemy.orm import Session
from dotenv import load_dotenv
import os
from db.models import Product as ProductModel
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

def get_all_products(db: Session):
    """Get all products from the database"""
    products = db.query(ProductModel).all()
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





















def chat_with_assistant(content):
    resp = client.responses.create(
        model = model,
        input=[
            {
                "role":"developer", "content": "You are a human like assistant skilled in general task like alexa and google cloud. You dont have to reply in more than 20 words unless asks for. Act more like human, talk casually as you can."
            },
            {
                "role":"user",
                "content": content
            }
        ],
        tools=[
            {
            "type": "web_search",
            "filters": {
              "allowed_domains": [
                  "ridra.in"
              ]}
            }
        ]
    )
    return resp.output_text