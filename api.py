"""Website REST APIs: feedback CRUD and the session-based chatbot."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from db.models import get_db, Feedback, Product, Category, Review, Blog
from schemas import (
    FeedbackCreate,
    FeedbackUpdate,
    FeedbackOut,
    ChatRequest,
    ChatResponse,
    CategoryCreate,
    CategoryUpdate,
    CategoryOut,
    ReviewCreate,
    ReviewUpdate,
    ReviewOut,
    BlogCreate,
    BlogUpdate,
    BlogOut,
)

logger = logging.getLogger(__name__)

api_router = APIRouter(prefix="/api")


# --- Feedback CRUD -----------------------------------------------------------

feedback_router = APIRouter(prefix="/feedback", tags=["feedback"])


def _validate_product(db: Session, product_id: int | None) -> None:
    if product_id is not None and not db.query(Product).filter(Product.id == product_id).first():
        raise HTTPException(status_code=400, detail=f"Product {product_id} not found")


@feedback_router.post("", response_model=FeedbackOut, status_code=201)
def create_feedback(payload: FeedbackCreate, db: Session = Depends(get_db)):
    _validate_product(db, payload.product_id)
    feedback = Feedback(**payload.model_dump())
    db.add(feedback)
    db.commit()
    db.refresh(feedback)
    return feedback


@feedback_router.get("", response_model=list[FeedbackOut])
def list_feedback(
    skip: int = 0,
    limit: int = 50,
    experience: str | None = None,
    feedback_type: str | None = None,
    db: Session = Depends(get_db),
):
    query = db.query(Feedback)
    if experience:
        query = query.filter(Feedback.experience == experience)
    if feedback_type:
        query = query.filter(Feedback.feedback_type == feedback_type)
    return (
        query.order_by(Feedback.created_at.desc())
        .offset(skip)
        .limit(min(limit, 200))
        .all()
    )


@feedback_router.get("/{feedback_id}", response_model=FeedbackOut)
def get_feedback(feedback_id: int, db: Session = Depends(get_db)):
    feedback = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    return feedback


@feedback_router.patch("/{feedback_id}", response_model=FeedbackOut)
def update_feedback(feedback_id: int, payload: FeedbackUpdate, db: Session = Depends(get_db)):
    feedback = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")

    data = payload.model_dump(exclude_unset=True)
    if "product_id" in data:
        _validate_product(db, data["product_id"])
    for key, value in data.items():
        setattr(feedback, key, value)
    db.commit()
    db.refresh(feedback)
    return feedback


@feedback_router.delete("/{feedback_id}", status_code=204)
def delete_feedback(feedback_id: int, db: Session = Depends(get_db)):
    feedback = db.query(Feedback).filter(Feedback.id == feedback_id).first()
    if not feedback:
        raise HTTPException(status_code=404, detail="Feedback not found")
    db.delete(feedback)
    db.commit()
    return None


# --- Website chatbot (session-based) ----------------------------------------

chat_router = APIRouter(prefix="/chat", tags=["chat"])


@chat_router.post("", response_model=ChatResponse)
@chat_router.post("/", response_model=ChatResponse)
def chat(payload: ChatRequest):
    """Send a message to the website chatbot. Omit session_id on the first
    message; reuse the returned session_id to keep conversation context."""
    from ai import chat_web

    try:
        reply, session_id = chat_web(payload.message, payload.session_id)
    except Exception as e:
        logger.error(f"Chat error: {e}")
        raise HTTPException(status_code=502, detail="Chatbot is temporarily unavailable")
    return ChatResponse(session_id=session_id, reply=reply)


# --- Categories CRUD ---------------------------------------------------------

category_router = APIRouter(prefix="/categories", tags=["categories"])


@category_router.post("", response_model=CategoryOut, status_code=201)
def create_category(payload: CategoryCreate, db: Session = Depends(get_db)):
    category = Category(**payload.model_dump())
    db.add(category)
    db.commit()
    db.refresh(category)
    return category


@category_router.get("", response_model=list[CategoryOut])
def list_categories(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    return db.query(Category).order_by(Category.name).offset(skip).limit(min(limit, 500)).all()


@category_router.get("/{category_id}", response_model=CategoryOut)
def get_category(category_id: int, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return category


@category_router.patch("/{category_id}", response_model=CategoryOut)
def update_category(category_id: int, payload: CategoryUpdate, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(category, key, value)
    db.commit()
    db.refresh(category)
    return category


@category_router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    db.delete(category)
    db.commit()
    return None


# --- Reviews CRUD ------------------------------------------------------------

review_router = APIRouter(prefix="/reviews", tags=["reviews"])


@review_router.post("", response_model=ReviewOut, status_code=201)
def create_review(payload: ReviewCreate, db: Session = Depends(get_db)):
    if not db.query(Product).filter(Product.id == payload.product_id).first():
        raise HTTPException(status_code=400, detail=f"Product {payload.product_id} not found")
    review = Review(**payload.model_dump())
    db.add(review)
    db.commit()
    db.refresh(review)
    return review


@review_router.get("", response_model=list[ReviewOut])
def list_reviews(
    product_id: int | None = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(Review)
    if product_id is not None:
        query = query.filter(Review.product_id == product_id)
    return (
        query.order_by(Review.created_at.desc())
        .offset(skip)
        .limit(min(limit, 200))
        .all()
    )


@review_router.get("/{review_id}", response_model=ReviewOut)
def get_review(review_id: int, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    return review


@review_router.patch("/{review_id}", response_model=ReviewOut)
def update_review(review_id: int, payload: ReviewUpdate, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(review, key, value)
    db.commit()
    db.refresh(review)
    return review


@review_router.delete("/{review_id}", status_code=204)
def delete_review(review_id: int, db: Session = Depends(get_db)):
    review = db.query(Review).filter(Review.id == review_id).first()
    if not review:
        raise HTTPException(status_code=404, detail="Review not found")
    db.delete(review)
    db.commit()
    return None


# --- Blogs CRUD --------------------------------------------------------------

blog_router = APIRouter(prefix="/blogs", tags=["blogs"])


@blog_router.post("", response_model=BlogOut, status_code=201)
def create_blog(payload: BlogCreate, db: Session = Depends(get_db)):
    blog = Blog(**payload.model_dump())
    db.add(blog)
    db.commit()
    db.refresh(blog)
    return blog


@blog_router.get("", response_model=list[BlogOut])
def list_blogs(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    return (
        db.query(Blog).order_by(Blog.created_at.desc()).offset(skip).limit(min(limit, 200)).all()
    )


@blog_router.get("/{blog_id}", response_model=BlogOut)
def get_blog(blog_id: int, db: Session = Depends(get_db)):
    blog = db.query(Blog).filter(Blog.id == blog_id).first()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    return blog


@blog_router.patch("/{blog_id}", response_model=BlogOut)
def update_blog(blog_id: int, payload: BlogUpdate, db: Session = Depends(get_db)):
    blog = db.query(Blog).filter(Blog.id == blog_id).first()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    for key, value in payload.model_dump(exclude_unset=True).items():
        setattr(blog, key, value)
    db.commit()
    db.refresh(blog)
    return blog


@blog_router.delete("/{blog_id}", status_code=204)
def delete_blog(blog_id: int, db: Session = Depends(get_db)):
    blog = db.query(Blog).filter(Blog.id == blog_id).first()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    db.delete(blog)
    db.commit()
    return None


api_router.include_router(feedback_router)
api_router.include_router(chat_router)
api_router.include_router(category_router)
api_router.include_router(review_router)
api_router.include_router(blog_router)
