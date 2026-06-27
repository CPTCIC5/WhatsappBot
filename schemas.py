"""Pydantic request/response schemas for the website REST APIs."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# --- Feedback ----------------------------------------------------------------

Experience = Literal["happy", "medium", "sad"]
FeedbackType = Literal["product_purchased", "staff_experience", "activities"]


class FeedbackBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)
    phone: str = Field(..., min_length=6, max_length=20)
    experience: Experience
    feedback_type: FeedbackType
    product_id: Optional[int] = None
    description: Optional[str] = None


class FeedbackCreate(FeedbackBase):
    pass


class FeedbackUpdate(BaseModel):
    """All fields optional for partial updates."""
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    phone: Optional[str] = Field(None, min_length=6, max_length=20)
    experience: Optional[Experience] = None
    feedback_type: Optional[FeedbackType] = None
    product_id: Optional[int] = None
    description: Optional[str] = None


class FeedbackOut(FeedbackBase):
    model_config = ConfigDict(from_attributes=True)

    id: int
    created_at: Optional[datetime] = None


# --- Website chatbot ---------------------------------------------------------

class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    # OpenAI conversation id used as the session token. Omit on the first
    # message; the response returns one to send back on subsequent messages.
    session_id: Optional[str] = None


class ChatResponse(BaseModel):
    session_id: str
    reply: str


# --- Categories --------------------------------------------------------------

class CategoryBase(BaseModel):
    name: str = Field(..., min_length=1, max_length=120)


class CategoryCreate(CategoryBase):
    pass


class CategoryUpdate(BaseModel):
    name: Optional[str] = Field(None, min_length=1, max_length=120)


class CategoryOut(CategoryBase):
    model_config = ConfigDict(from_attributes=True)
    id: int


# --- Reviews -----------------------------------------------------------------

class ReviewBase(BaseModel):
    product_id: int
    rating: float = Field(..., ge=0, le=5)
    name: str = Field(..., min_length=1, max_length=120)
    email: Optional[str] = None
    description: Optional[str] = None


class ReviewCreate(ReviewBase):
    pass


class ReviewUpdate(BaseModel):
    rating: Optional[float] = Field(None, ge=0, le=5)
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    email: Optional[str] = None
    description: Optional[str] = None


class ReviewOut(ReviewBase):
    model_config = ConfigDict(from_attributes=True)
    id: int
    created_at: Optional[datetime] = None


# --- Blogs -------------------------------------------------------------------

class BlogBase(BaseModel):
    heading: str = Field(..., min_length=1, max_length=200)
    description: Optional[str] = None


class BlogCreate(BlogBase):
    pass


class BlogUpdate(BaseModel):
    heading: Optional[str] = Field(None, min_length=1, max_length=200)
    description: Optional[str] = None


class BlogOut(BlogBase):
    id: int
    image_url: Optional[str] = None
    created_at: Optional[datetime] = None


# --- Items (products) --------------------------------------------------------

class ItemMetalOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)
    id: int
    metal: Optional[str] = None
    karat: Optional[str] = None
    rate_per_gram: Optional[float] = None


class ItemImageOut(BaseModel):
    # id is null for the legacy single image set via the admin panel; images
    # added through the API have an id you can use to delete them individually.
    id: Optional[int] = None
    url: str


class ItemOut(BaseModel):
    id: int
    name: Optional[str] = None
    style_no: Optional[str] = None
    jewel_code: Optional[str] = None
    description: Optional[str] = None
    gross_weight: Optional[float] = None
    availability: bool = True
    metal_id: Optional[int] = None
    metal: Optional[ItemMetalOut] = None
    calculated_amount: float = 0.0
    categories: list[CategoryOut] = []
    images: list[ItemImageOut] = []

