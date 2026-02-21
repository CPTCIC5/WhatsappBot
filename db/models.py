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

    @property
    def calculated_amount(self):
        """Calculate the amount based on gross weight and metal rate per gram"""
        if self.gross_weight and self.metal_info and self.metal_info.rate_per_gram:
            return round(self.gross_weight * self.metal_info.rate_per_gram, 2)
        return 0.0

    def __repr__(self):
        return self.name
    




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

    groups = relationship("Group", secondary=group_leads, back_populates="leads")
    def __repr__(self):
        return self.name


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
    template_note=  Column(Text, help_text="Note")


    def __str__(self):
        return self.template_name