from sqlalchemy import create_engine, Column, Integer, String, DateTime, JSON, Enum, Float, ForeignKey, Text, Table, Boolean
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

DATABASE_URL = "sqlite:///./test.db"
engine= create_engine(DATABASE_URL)

SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()

class Metal(Base):
    __tablename__ = "metals"

    id = Column(Integer, primary_key=True, index=True)
    metal = Column(String, index=True)  
    karat = Column(String, index=True)  
    rate_per_gram = Column(Float)  

    
    products = relationship("Product", back_populates="metal_info")

    def __repr__(self):
        return f"{self.metal} - {self.karat}"


class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    style_no = Column(String, index=True)
    jewel_code = Column(String, index=True)
    image_url = Column(String, nullable=True)
    gross_weight = Column(Float)  
    name = Column(String, index=True)
    description = Column(Text)
    metal_id = Column(Integer, ForeignKey("metals.id"))
    availability = Column(Boolean, default=True, nullable=False)

    metal_info = relationship("Metal", back_populates="products")
    categories = relationship("Category", secondary="product_categories", back_populates="products")
    reviews = relationship("Review", back_populates="product", cascade="all, delete-orphan")
    images = relationship("ProductImage", back_populates="product", cascade="all, delete-orphan")

    @property
    def calculated_amount(self):
        """Calculate the amount based on gross weight and metal rate per gram"""
        if self.gross_weight and self.metal_info and self.metal_info.rate_per_gram:
            return round(self.gross_weight * self.metal_info.rate_per_gram, 2)
        return 0.0

    def __repr__(self):
        return self.name


# Association table for Product <-> Category (many-to-many)
product_categories = Table(
    "product_categories",
    Base.metadata,
    Column("product_id", Integer, ForeignKey("products.id"), primary_key=True),
    Column("category_id", Integer, ForeignKey("categories.id"), primary_key=True),
)


class Category(Base):
    __tablename__ = "categories"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    # Azure blob name for the category image (resolved to a SAS URL on read)
    image_blob = Column(String, nullable=True)

    products = relationship("Product", secondary="product_categories", back_populates="categories")

    def __repr__(self):
        return self.name


class ProductImage(Base):
    """One image for a product. Stores the Azure blob name (not a public URL)."""

    __tablename__ = "product_images"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    blob_name = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="images")

    def __repr__(self):
        return self.blob_name


class Review(Base):
    """A customer review for a catalogue item (product)."""

    __tablename__ = "reviews"

    id = Column(Integer, primary_key=True, index=True)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=False, index=True)
    rating = Column(Float, nullable=False)  # out of 5
    name = Column(String, nullable=False)
    email = Column(String, nullable=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product", back_populates="reviews")

    def __repr__(self):
        return f"Review #{self.id} ({self.rating}/5)"


class Blog(Base):
    __tablename__ = "blogs"

    id = Column(Integer, primary_key=True, index=True)
    heading = Column(String, nullable=False, index=True)
    description = Column(Text, nullable=True)
    # Azure blob name for the blog's cover image (resolved to a SAS URL on read)
    image_blob = Column(String, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    def __repr__(self):
        return self.heading
    




# Association table for Group <-> Lead (many-to-many)
group_leads = Table(
    "group_leads",
    Base.metadata,
    Column("group_id", Integer, ForeignKey("groups.id"), primary_key=True),
    Column("lead_id", Integer, ForeignKey("leads.id"), primary_key=True),
)

class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    tag= Column(Enum("new", "existing", name="lead_tags"), default="new")
    thread_id= Column(String, index=True, nullable=True)
    email = Column(String, unique=True, index=True)
    phone = Column(String, unique=True, index=True)
    created_at = Column(DateTime,  default=datetime.utcnow)

    # --- Milestone 3: onboarding + referrals ---
    # Onboarding journey state: new -> welcomed -> engaged
    onboarding_state = Column(
        Enum("new", "welcomed", "engaged", name="onboarding_states"),
        default="new",
        nullable=False,
    )
    # Unique code this customer shares to refer others
    referral_code = Column(String, unique=True, index=True, nullable=True)
    # Tracks a short multi-step intent (e.g. "awaiting_referral" while we wait
    # for the customer to send the friend's contact/number to refer)
    pending_intent = Column(String, nullable=True)

    groups = relationship("Group", secondary=group_leads, back_populates="leads")

    # Referrals this customer has made (they are the referrer)
    referrals_given = relationship(
        "Referral",
        foreign_keys="Referral.referrer_id",
        back_populates="referrer",
    )

    def __repr__(self):
        return self.name


class Referral(Base):
    """A referral made by an existing customer (referrer) toward a new person.

    Supports referral chains ("referrals from referrals") via parent_referral_id,
    so an admin can view the full tree of who referred whom.
    """

    __tablename__ = "referrals"

    id = Column(Integer, primary_key=True, index=True)
    # The existing customer who made the referral
    referrer_id = Column(Integer, ForeignKey("leads.id"), nullable=False, index=True)
    # The new lead once they join via this referral (filled on acceptance)
    referred_lead_id = Column(Integer, ForeignKey("leads.id"), nullable=True, index=True)
    # Details of the referred person, captured at referral time
    referred_phone = Column(String, nullable=True, index=True)
    referred_name = Column(String, nullable=True)
    # The referrer's code that was used for this referral
    referral_code = Column(String, index=True, nullable=True)
    status = Column(
        Enum("pending", "accepted", name="referral_status"),
        default="pending",
        nullable=False,
    )
    # If the referrer themselves joined via a referral, link that referral here
    parent_referral_id = Column(Integer, ForeignKey("referrals.id"), nullable=True, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)
    accepted_at = Column(DateTime, nullable=True)

    referrer = relationship("Lead", foreign_keys=[referrer_id], back_populates="referrals_given")
    referred_lead = relationship("Lead", foreign_keys=[referred_lead_id])
    parent_referral = relationship(
        "Referral",
        remote_side=[id],
        backref="child_referrals",
    )

    def __repr__(self):
        return f"Referral #{self.id} ({self.status})"


class Group(Base):
    __tablename__ = "groups"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    leads = relationship("Lead", secondary=group_leads, back_populates="groups")

    def __repr__(self):
        return self.name

"""
# Create a group and add leads
group = Group(name="VIP Customers")
db.add(group)
db.flush()
group.leads.extend([lead1, lead2])
db.commit()

# Or append one lead
group.leads.append(lead)
db.commit()
"""

class TemplateStorage(Base):
    __tablename__= "template_storage"

    id= Column(Integer, primary_key=True, index=True)
    template_name = Column(String, index=True)
    template_note=  Column(Text)


    def __str__(self):
        return self.template_name


class Feedback(Base):
    """Customer feedback collected via the website feedback forum."""

    __tablename__ = "feedback"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True, nullable=False)
    phone = Column(String, index=True, nullable=False)
    # How the customer felt about the experience
    experience = Column(
        Enum("happy", "medium", "sad", name="feedback_experience"),
        nullable=False,
    )
    # What the feedback is about
    feedback_type = Column(
        Enum("product_purchased", "staff_experience", "activities", name="feedback_type"),
        nullable=False,
    )
    # Optional product the feedback relates to (selectable)
    product_id = Column(Integer, ForeignKey("products.id"), nullable=True, index=True)
    description = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    product = relationship("Product")

    def __repr__(self):
        return f"Feedback #{self.id} ({self.experience})"