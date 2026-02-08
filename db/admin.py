from db.models import Product, Metal, Lead, Group
from sqladmin import ModelView

class MetalAdmin(ModelView, model=Metal):
    name = "Metal"
    name_plural = "Metals"
    icon = "fa-solid fa-gem"
    
    column_list = [Metal.id, Metal.metal, Metal.karat, Metal.rate_per_gram]
    column_searchable_list = [Metal.metal, Metal.karat]
    column_sortable_list = [Metal.id, Metal.metal, Metal.karat, Metal.rate_per_gram]
    
    form_columns = [Metal.metal, Metal.karat, Metal.rate_per_gram]


class ProductAdmin(ModelView, model=Product):
    name = "Product"
    name_plural = "Products"
    icon = "fa-solid fa-box"
    
    column_list = [
        Product.id, 
        Product.style_no, 
        Product.jewel_code, 
        Product.name, 
        Product.gross_weight,
        Product.metal_info,
        "calculated_amount",  
        Product.description
    ]
    
    column_searchable_list = [Product.name, Product.style_no, Product.jewel_code]
    column_sortable_list = [Product.id, Product.name, Product.style_no, Product.gross_weight]
    
    
    column_details_exclude_list = []
    
    
    form_columns = [
        Product.style_no,
        Product.jewel_code,
        Product.name,
        Product.description,
        Product.gross_weight,
        Product.metal_info  
    ]
    
    column_labels = {
        "calculated_amount": "Amount (₹)",
        "gross_weight": "Gross Weight (g)",
        "metal_info": "Metal"
    }
    
    
    column_formatters = {
        "gross_weight": lambda m, a: f"{m.gross_weight:.3f}" if m.gross_weight else "0.000",
        "calculated_amount": lambda m, a: f"₹{m.calculated_amount:,.2f}" if m.calculated_amount else "₹0.00"
    }

class LeadAdmin(ModelView, model=Lead):
    name = "Lead"
    name_plural = "Leads"
    icon = "fa-solid fa-user"
    
    column_list = [Lead.id, Lead.name, Lead.tag, Lead.email, Lead.phone, Lead.created_at]
    column_searchable_list = [Lead.name, Lead.email, Lead.phone]
    column_sortable_list = [Lead.id, Lead.name, Lead.created_at]
    
    
    form_columns = [Lead.name, Lead.tag, Lead.email, Lead.phone]
    
    column_labels = {
        "created_at": "Created At"
    }
    
   
    column_formatters = {
        "created_at": lambda m, a: m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else ""
    }


class GroupAdmin(ModelView, model=Group):
    name = "Group"
    name_plural = "Groups"
    icon = "fa-solid fa-users"

    column_list = [Group.id, Group.name, Group.leads, Group.created_at]
    column_searchable_list = [Group.name]
    column_sortable_list = [Group.id, Group.name, Group.created_at]

    form_columns = [Group.name, Group.leads]

    column_labels = {
        "created_at": "Created At",
        "leads": "Leads",
    }

    column_formatters = {
        "created_at": lambda m, a: m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else "",
        "leads": lambda m, a: f"{len(m.leads)} lead(s)" if m.leads else "0 leads",
    }
