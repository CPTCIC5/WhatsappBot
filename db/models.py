from sqlalchemy import create_engine, Column, Integer, String, DateTime, Enum
from sqlalchemy.orm import relationship, declarative_base, sessionmaker
from dotenv import load_dotenv
import enum

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

class Product(Base):
    __tablename__ = "products"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    description = Column(String)

    def __repr__(self):
        return self.name
    




class Lead(Base):
    __tablename__ = "leads"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    tag= Column(Enum("new", "existing", name="lead_tags"))
    email = Column(String, unique=True, index=True)
    phone = Column(String, unique=True, index=True)
    created_at = Column(DateTime)

    def __repr__(self):
        return self.name
    
