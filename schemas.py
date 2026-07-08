"""Pydantic request/response schemas for the website REST APIs."""

from datetime import datetime
from typing import Literal, Optional

from pydantic import BaseModel, ConfigDict, Field


# --- Feedback ----------------------------------------------------------------

RatingValue = Literal["Needs Improvement", "Good", "Loved It!"]


class ReferenceEntry(BaseModel):
    """One row of the References table (section 7)."""
    name: Optional[str] = None
    mobile: Optional[str] = None
    relation: Optional[str] = None
    area: Optional[str] = None


class FeedbackBase(BaseModel):
    # ── Section 1: Sparkle Member Details ──────────────────────────────
    name: str = Field(..., min_length=1, max_length=120)
    phone: str = Field(..., min_length=6, max_length=20)
    email: Optional[str] = None
    address: Optional[str] = None
    spouse_name: Optional[str] = None

    # ── Section 2: Celebration Moments ──────────────────────────────────
    anniversary_date: Optional[str] = None   # ISO date string e.g. "2024-03-15"
    spouse_birthday: Optional[str] = None
    child_birthday: Optional[str] = None

    # ── Section 3: Tell Me About You ─────────────────────────────────
    about_you: Optional[str] = None

    # ── Section 4: What Makes Your Heart Shine ───────────────────────
    jewellery_preferences: Optional[list[str]] = None  # e.g. ["purity", "daily"]

    # ── Section 5: Your Ridra Experience ────────────────────────────
    rating_designs: Optional[RatingValue] = None
    rating_quality: Optional[RatingValue] = None
    rating_value: Optional[RatingValue] = None
    rating_staff: Optional[RatingValue] = None
    rating_overall: Optional[RatingValue] = None

    # ── Section 6: Your Words, Our Motivation ──────────────────────
    words: Optional[str] = None

    # ── Section 7: References ───────────────────────────────────────
    references: Optional[list[ReferenceEntry]] = None

    # ── Section 8: Let's Stay Connected ────────────────────────────
    join_update_list: Optional[bool] = None
    visited_recently: Optional[bool] = None
    can_give_references: Optional[bool] = None
    next_visit_pref_1: Optional[str] = None
    next_visit_pref_2: Optional[str] = None


class FeedbackCreate(FeedbackBase):
    pass


class FeedbackUpdate(BaseModel):
    """All fields optional for partial updates."""
    # Section 1
    name: Optional[str] = Field(None, min_length=1, max_length=120)
    phone: Optional[str] = Field(None, min_length=6, max_length=20)
    email: Optional[str] = None
    address: Optional[str] = None
    spouse_name: Optional[str] = None
    # Section 2
    anniversary_date: Optional[str] = None
    spouse_birthday: Optional[str] = None
    child_birthday: Optional[str] = None
    # Section 3
    about_you: Optional[str] = None
    # Section 4
    jewellery_preferences: Optional[list[str]] = None
    # Section 5
    rating_designs: Optional[RatingValue] = None
    rating_quality: Optional[RatingValue] = None
    rating_value: Optional[RatingValue] = None
    rating_staff: Optional[RatingValue] = None
    rating_overall: Optional[RatingValue] = None
    # Section 6
    words: Optional[str] = None
    # Section 7
    references: Optional[list[ReferenceEntry]] = None
    # Section 8
    join_update_list: Optional[bool] = None
    visited_recently: Optional[bool] = None
    can_give_references: Optional[bool] = None
    next_visit_pref_1: Optional[str] = None
    next_visit_pref_2: Optional[str] = None


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
    id: int
    image_url: Optional[str] = None


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
    reviews: list[ReviewOut] = []

