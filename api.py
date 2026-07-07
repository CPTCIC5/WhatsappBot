"""Website REST APIs: feedback CRUD and the session-based chatbot."""

import logging

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, Form
from sqlalchemy.orm import Session

import azure_storage
from db.models import get_db, Feedback, Product, Category, Review, Blog, ProductImage, Metal
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
    ItemOut,
    ItemMetalOut,
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


def _serialize_category(cat: Category) -> CategoryOut:
    return CategoryOut(
        id=cat.id,
        name=cat.name,
        image_url=azure_storage.resolve_url(cat.image_blob),
    )


@category_router.post("", response_model=CategoryOut, status_code=201)
async def create_category(
    name: str = Form(..., min_length=1, max_length=120),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    category = Category(name=name)
    if image is not None and image.filename:
        category.image_blob = await _store_upload(image, prefix="categories/")
    db.add(category)
    db.commit()
    db.refresh(category)
    return _serialize_category(category)


@category_router.get("", response_model=list[CategoryOut])
def list_categories(skip: int = 0, limit: int = 100, db: Session = Depends(get_db)):
    cats = db.query(Category).order_by(Category.name).offset(skip).limit(min(limit, 500)).all()
    return [_serialize_category(c) for c in cats]


@category_router.get("/{category_id}", response_model=CategoryOut)
def get_category(category_id: int, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    return _serialize_category(category)


@category_router.patch("/{category_id}", response_model=CategoryOut)
async def update_category(
    category_id: int,
    name: str | None = Form(None, min_length=1, max_length=120),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    if name is not None:
        category.name = name
    if image is not None and image.filename:
        old = category.image_blob
        category.image_blob = await _store_upload(image, prefix="categories/")
        if old:
            azure_storage.delete_blob(old)
    db.commit()
    db.refresh(category)
    return _serialize_category(category)


@category_router.delete("/{category_id}", status_code=204)
def delete_category(category_id: int, db: Session = Depends(get_db)):
    category = db.query(Category).filter(Category.id == category_id).first()
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")
    if category.image_blob:
        azure_storage.delete_blob(category.image_blob)
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


# --- Image upload helper -----------------------------------------------------

async def _store_upload(file: UploadFile, prefix: str) -> str:
    """Validate, read and upload an image file. Returns the stored blob name."""
    data = await file.read()
    if not data:
        raise HTTPException(status_code=422, detail="Uploaded file is empty")
    try:
        return azure_storage.upload_image(data, file.content_type, prefix=prefix)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        logger.error(f"Image upload failed: {e}")
        raise HTTPException(status_code=502, detail="Image upload failed")


# --- Blogs CRUD (form-data: optional cover image) ---------------------------

blog_router = APIRouter(prefix="/blogs", tags=["blogs"])


def _serialize_blog(blog: Blog) -> BlogOut:
    return BlogOut(
        id=blog.id,
        heading=blog.heading,
        description=blog.description,
        image_url=azure_storage.resolve_url(blog.image_blob),
        created_at=blog.created_at,
    )


@blog_router.post("", response_model=BlogOut, status_code=201)
async def create_blog(
    heading: str = Form(..., min_length=1, max_length=200),
    description: str | None = Form(None),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    blog = Blog(heading=heading, description=description)
    if image is not None:
        blog.image_blob = await _store_upload(image, prefix="blogs/")
    db.add(blog)
    db.commit()
    db.refresh(blog)
    return _serialize_blog(blog)


@blog_router.get("", response_model=list[BlogOut])
def list_blogs(skip: int = 0, limit: int = 50, db: Session = Depends(get_db)):
    blogs = (
        db.query(Blog).order_by(Blog.created_at.desc()).offset(skip).limit(min(limit, 200)).all()
    )
    return [_serialize_blog(b) for b in blogs]


@blog_router.get("/{blog_id}", response_model=BlogOut)
def get_blog(blog_id: int, db: Session = Depends(get_db)):
    blog = db.query(Blog).filter(Blog.id == blog_id).first()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    return _serialize_blog(blog)


@blog_router.patch("/{blog_id}", response_model=BlogOut)
async def update_blog(
    blog_id: int,
    heading: str | None = Form(None, min_length=1, max_length=200),
    description: str | None = Form(None),
    image: UploadFile | None = File(None),
    db: Session = Depends(get_db),
):
    blog = db.query(Blog).filter(Blog.id == blog_id).first()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    if heading is not None:
        blog.heading = heading
    if description is not None:
        blog.description = description
    if image is not None:
        old = blog.image_blob
        blog.image_blob = await _store_upload(image, prefix="blogs/")
        if old:
            azure_storage.delete_blob(old)
    db.commit()
    db.refresh(blog)
    return _serialize_blog(blog)


@blog_router.delete("/{blog_id}", status_code=204)
def delete_blog(blog_id: int, db: Session = Depends(get_db)):
    blog = db.query(Blog).filter(Blog.id == blog_id).first()
    if not blog:
        raise HTTPException(status_code=404, detail="Blog not found")
    if blog.image_blob:
        azure_storage.delete_blob(blog.image_blob)
    db.delete(blog)
    db.commit()
    return None


# --- Items (products) CRUD (form-data: multiple images) ----------------------

item_router = APIRouter(prefix="/items", tags=["items"])


def _serialize_item(p: Product) -> ItemOut:
    images = []
    # Legacy single image_url (set via admin) has no ProductImage id.
    if p.image_url:
        u = azure_storage.resolve_url(p.image_url)
        if u:
            images.append({"id": None, "url": u})
    for img in p.images:
        u = azure_storage.resolve_url(img.blob_name)
        if u:
            images.append({"id": img.id, "url": u})

    return ItemOut(
        id=p.id,
        name=p.name,
        style_no=p.style_no,
        jewel_code=p.jewel_code,
        description=p.description,
        gross_weight=p.gross_weight,
        availability=p.availability,
        metal_id=p.metal_id,
        metal=p.metal_info,
        calculated_amount=p.calculated_amount,
        categories=[_serialize_category(cat) for cat in p.categories],
        images=images,
        reviews=p.reviews,
    )


def _apply_categories(db: Session, product: Product, category_ids: list[int]) -> None:
    cats = db.query(Category).filter(Category.id.in_(category_ids)).all()
    found = {c.id for c in cats}
    missing = set(category_ids) - found
    if missing:
        raise HTTPException(status_code=400, detail=f"Unknown category id(s): {sorted(missing)}")
    product.categories = cats


@item_router.post("", response_model=ItemOut, status_code=201)
async def create_item(
    name: str = Form(..., min_length=1),
    style_no: str | None = Form(None),
    jewel_code: str | None = Form(None),
    description: str | None = Form(None),
    gross_weight: float | None = Form(None),
    metal_id: int | None = Form(None),
    availability: bool = Form(True),
    category_ids: list[int] = Form([]),
    images: list[UploadFile] = File([]),
    db: Session = Depends(get_db),
):
    if metal_id is not None and not db.query(Metal).filter(Metal.id == metal_id).first():
        raise HTTPException(status_code=400, detail=f"Metal {metal_id} not found")

    product = Product(
        name=name,
        style_no=style_no,
        jewel_code=jewel_code,
        description=description,
        gross_weight=gross_weight,
        metal_id=metal_id,
        availability=availability,
    )
    if category_ids:
        _apply_categories(db, product, category_ids)
    db.add(product)
    db.flush()

    for f in images:
        if f and f.filename:
            blob = await _store_upload(f, prefix="products/")
            db.add(ProductImage(product_id=product.id, blob_name=blob))

    db.commit()
    db.refresh(product)
    return _serialize_item(product)


@item_router.get("", response_model=list[ItemOut])
def list_items(
    name: str | None = None,
    metal: str | None = None,
    metal_id: int | None = None,   # exact metal row id (preferred over 'metal' name)
    category_id: int | None = None,
    available: bool | None = None,
    min_price: float | None = None,
    max_price: float | None = None,
    skip: int = 0,
    limit: int = 50,
    db: Session = Depends(get_db),
):
    query = db.query(Product)
    if name:
        query = query.filter(Product.name.ilike(f"%{name}%"))

    # Exact metal_id filter (preferred — unique per metal+karat row)
    if metal_id is not None:
        query = query.filter(Product.metal_id == metal_id)

    joined_metal = False
    # Fuzzy metal name filter (legacy — matches all rows with the same metal name)
    if metal and metal_id is None:
        query = query.join(Product.metal_info).filter(Metal.metal.ilike(f"%{metal}%"))
        joined_metal = True

    if min_price is not None or max_price is not None:
        if not joined_metal:
            query = query.join(Product.metal_info)
            joined_metal = True
        if min_price is not None:
            query = query.filter(Product.gross_weight * Metal.rate_per_gram >= min_price)
        if max_price is not None:
            query = query.filter(Product.gross_weight * Metal.rate_per_gram <= max_price)

    if category_id is not None:
        query = query.filter(Product.categories.any(Category.id == category_id))
    if available is not None:
        query = query.filter(Product.availability == available)
    items = query.offset(skip).limit(min(limit, 200)).all()
    return [_serialize_item(p) for p in items]


@item_router.get("/{item_id}", response_model=ItemOut)
def get_item(item_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == item_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Item not found")
    return _serialize_item(product)


@item_router.patch("/{item_id}", response_model=ItemOut)
async def update_item(
    item_id: int,
    name: str | None = Form(None, min_length=1),
    style_no: str | None = Form(None),
    jewel_code: str | None = Form(None),
    description: str | None = Form(None),
    gross_weight: float | None = Form(None),
    metal_id: int | None = Form(None),
    availability: bool | None = Form(None),
    category_ids: list[int] | None = Form(None),
    images: list[UploadFile] = File([]),
    db: Session = Depends(get_db),
):
    product = db.query(Product).filter(Product.id == item_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Item not found")

    if name is not None:
        product.name = name
    if style_no is not None:
        product.style_no = style_no
    if jewel_code is not None:
        product.jewel_code = jewel_code
    if description is not None:
        product.description = description
    if gross_weight is not None:
        product.gross_weight = gross_weight
    if availability is not None:
        product.availability = availability
    if metal_id is not None:
        if not db.query(Metal).filter(Metal.id == metal_id).first():
            raise HTTPException(status_code=400, detail=f"Metal {metal_id} not found")
        product.metal_id = metal_id
    if category_ids is not None:
        _apply_categories(db, product, category_ids)

    # New images are appended (existing ones are kept; remove via the image endpoint).
    for f in images:
        if f and f.filename:
            blob = await _store_upload(f, prefix="products/")
            db.add(ProductImage(product_id=product.id, blob_name=blob))

    db.commit()
    db.refresh(product)
    return _serialize_item(product)


@item_router.delete("/{item_id}", status_code=204)
def delete_item(item_id: int, db: Session = Depends(get_db)):
    product = db.query(Product).filter(Product.id == item_id).first()
    if not product:
        raise HTTPException(status_code=404, detail="Item not found")
    for img in product.images:
        azure_storage.delete_blob(img.blob_name)
    db.delete(product)
    db.commit()
    return None


@item_router.delete("/{item_id}/images/{image_id}", status_code=204)
def delete_item_image(item_id: int, image_id: int, db: Session = Depends(get_db)):
    img = (
        db.query(ProductImage)
        .filter(ProductImage.id == image_id, ProductImage.product_id == item_id)
        .first()
    )
    if not img:
        raise HTTPException(status_code=404, detail="Image not found")
    azure_storage.delete_blob(img.blob_name)
    db.delete(img)
    db.commit()
    return None


# --- Metals (read-only) ------------------------------------------------------

metal_router = APIRouter(prefix="/metals", tags=["metals"])


@metal_router.get("", response_model=list[ItemMetalOut])
def list_metals(db: Session = Depends(get_db)):
    """Return all metals available in the database."""
    return db.query(Metal).order_by(Metal.id).all()


# --- Register all sub-routers on the main api_router -------------------------

api_router.include_router(feedback_router)
api_router.include_router(chat_router)
api_router.include_router(category_router)
api_router.include_router(review_router)
api_router.include_router(blog_router)
api_router.include_router(item_router)
api_router.include_router(metal_router)
