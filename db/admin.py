from db.models import Product
from sqladmin import ModelView

class ProductAdmin(ModelView, model=Product):
    pass