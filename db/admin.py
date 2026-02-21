from db.models import Product, Metal, Lead, Group, TemplateStorage
from sqladmin import ModelView, action
from starlette.requests import Request
from starlette.responses import RedirectResponse
from wtforms import Form, TextAreaField, validators
import os
import requests
from dotenv import load_dotenv

load_dotenv()

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
        Product.availability,
        Product.description,
        Product.image_url
    ]
    
    column_searchable_list = [Product.name, Product.style_no, Product.jewel_code]
    column_sortable_list = [Product.id, Product.name, Product.style_no, Product.gross_weight, Product.image_url]
    
    
    column_details_exclude_list = []
    
    
    form_columns = [
        Product.style_no,
        Product.jewel_code,
        Product.name,
        Product.description,
        Product.gross_weight,
        Product.metal_info,
        Product.availability,
        Product.image_url
    ]
    
    column_labels = {
        "calculated_amount": "Amount (₹)",
        "gross_weight": "Gross Weight (g)",
        "metal_info": "Metal",
        "availability": "Available",
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

    @action(
        name="send_message",
        label="Send WhatsApp Message",
        confirmation_message="Send message to all leads in selected group(s)?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def send_whatsapp_message(self, request: Request):
        """Send WhatsApp message to all leads in the selected group(s)"""
        from sqlalchemy.orm import Session
        from db.models import get_db
        from starlette.responses import HTMLResponse
        
        # Get selected group IDs from the request
        pks = request.query_params.get("pks", "").split(",")
        
        if not pks or pks == [""]:
            request.session["_messages"] = [("error", "No groups selected")]
            return RedirectResponse(url=request.url_for("admin:list", identity=self.identity), status_code=302)
        
        # Get message from query params (if submitted)
        message_text = request.query_params.get("message_text", "").strip()
        
        if message_text:
            # Message was submitted, send it
            # Get WhatsApp API credentials
            token = os.getenv("ACCESS_TOKEN")
            version = os.getenv("VERSION")
            number_id = os.getenv("PHONE_NUMBER_ID")
            
            if not all([token, version, number_id]):
                request.session["_messages"] = [("error", "WhatsApp API credentials not configured")]
                return RedirectResponse(url=request.url_for("admin:list", identity=self.identity), status_code=302)
            
            total_sent = 0
            total_failed = 0
            
            # Get database session
            db = next(get_db())
            
            try:
                # Send messages to each group
                for pk in pks:
                    group = db.query(Group).filter(Group.id == int(pk)).first()
                    if not group or not group.leads:
                        continue
                    
                    url = f"https://graph.facebook.com/{version}/{number_id}/messages"
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-type": "application/json"
                    }
                    
                    # Send to each lead in the group
                    for lead in group.leads:
                        data = {
                            "messaging_product": "whatsapp",
                            "recipient_type": "individual",
                            "to": lead.phone,
                            "type": "text",
                            "text": {
                                "body": message_text
                            }
                        }
                        
                        try:
                            response = requests.post(url=url, headers=headers, json=data)
                            if response.status_code == 200:
                                total_sent += 1
                            else:
                                total_failed += 1
                        except Exception:
                            total_failed += 1
            finally:
                db.close()
            
            request.session["_messages"] = [(
                "success" if total_failed == 0 else "warning",
                f"Message sent to {total_sent} lead(s). {total_failed} failed."
            )]
            return RedirectResponse(url=request.url_for("admin:list", identity=self.identity), status_code=302)
        
        # Show message input form - Get group info from database
        db = next(get_db())
        group_names = []
        total_leads = 0
        
        try:
            for pk in pks:
                group = db.query(Group).filter(Group.id == int(pk)).first()
                if group:
                    group_names.append(group.name)
                    total_leads += len(group.leads) if group.leads else 0
        finally:
            db.close()
        
        # Build the action URL with pks
        action_url = str(request.url)
        
        html_form = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Send WhatsApp Message</title>
            <link rel="stylesheet" href="/static/css/tabler.min.css">
        </head>
        <body>
            <div class="container mt-5">
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">Send WhatsApp Message to Group(s)</h3>
                    </div>
                    <div class="card-body">
                        <p><strong>Selected Groups:</strong> {', '.join(group_names)}</p>
                        <p><strong>Total Recipients:</strong> {total_leads} lead(s)</p>
                        <form method="GET" action="{action_url}">
                            <input type="hidden" name="pks" value="{','.join(pks)}">
                            <div class="mb-3">
                                <label class="form-label">Message Text</label>
                                <textarea name="message_text" class="form-control" rows="5" required 
                                    placeholder="Enter your message here..."></textarea>
                            </div>
                            <div class="d-flex gap-2">
                                <button type="submit" class="btn btn-primary">Send Message</button>
                                <a href="{request.url_for('admin:list', identity=self.identity)}" 
                                   class="btn btn-secondary">Cancel</a>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_form)

    @action(
        name="send_template",
        label="Send WhatsApp Template",
        confirmation_message="Send template to all leads in selected group(s)?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def send_whatsapp_template(self, request: Request):
        """Send WhatsApp template message to all leads in the selected group(s)"""
        from sqlalchemy.orm import Session
        from db.models import get_db
        from starlette.responses import HTMLResponse
        
        # Get selected group IDs from the request
        pks = request.query_params.get("pks", "").split(",")
        
        if not pks or pks == [""]:
            request.session["_messages"] = [("error", "No groups selected")]
            return RedirectResponse(url=request.url_for("admin:list", identity=self.identity), status_code=302)
        
        # Get template details from query params (if submitted)
        template_name = request.query_params.get("template_name", "").strip()
        language_code = request.query_params.get("language_code", "en_US").strip()
        
        if template_name:
            # Template was submitted, send it
            # Get WhatsApp API credentials
            token = os.getenv("ACCESS_TOKEN")
            version = os.getenv("VERSION")
            number_id = os.getenv("PHONE_NUMBER_ID")
            
            if not all([token, version, number_id]):
                request.session["_messages"] = [("error", "WhatsApp API credentials not configured")]
                return RedirectResponse(url=request.url_for("admin:list", identity=self.identity), status_code=302)
            
            total_sent = 0
            total_failed = 0
            
            # Get database session
            db = next(get_db())
            
            try:
                # Send template to each group
                for pk in pks:
                    group = db.query(Group).filter(Group.id == int(pk)).first()
                    if not group or not group.leads:
                        continue
                    
                    url = f"https://graph.facebook.com/{version}/{number_id}/messages"
                    headers = {
                        "Authorization": f"Bearer {token}",
                        "Content-type": "application/json"
                    }
                    
                    # Send to each lead in the group
                    for lead in group.leads:
                        data = {
                            "messaging_product": "whatsapp",
                            "to": lead.phone,
                            "type": "template",
                            "template": {
                                "name": template_name,
                                "language": {
                                    "code": language_code
                                }
                            }
                        }
                        
                        try:
                            response = requests.post(url=url, headers=headers, json=data)
                            if response.status_code == 200:
                                total_sent += 1
                            else:
                                total_failed += 1
                        except Exception:
                            total_failed += 1
            finally:
                db.close()
            
            request.session["_messages"] = [(
                "success" if total_failed == 0 else "warning",
                f"Template '{template_name}' sent to {total_sent} lead(s). {total_failed} failed."
            )]
            return RedirectResponse(url=request.url_for("admin:list", identity=self.identity), status_code=302)
        
        # Show template input form - Get group info from database
        db = next(get_db())
        group_names = []
        total_leads = 0
        
        try:
            for pk in pks:
                group = db.query(Group).filter(Group.id == int(pk)).first()
                if group:
                    group_names.append(group.name)
                    total_leads += len(group.leads) if group.leads else 0
        finally:
            db.close()
        
        # Build the action URL with pks
        action_url = str(request.url)
        
        html_form = f"""
        <!DOCTYPE html>
        
        <html>
        <head>
            <title>Send WhatsApp Template</title>
            <link rel="stylesheet" href="/static/css/tabler.min.css">
        </head>
        <body>
            <div class="container mt-5">
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">Send WhatsApp Template to Group(s)</h3>
                    </div>
                    <div class="card-body">
                        <p><strong>Selected Groups:</strong> {', '.join(group_names)}</p>
                        <p><strong>Total Recipients:</strong> {total_leads} lead(s)</p>
                        <form method="GET" action="{action_url}">
                            <input type="hidden" name="pks" value="{','.join(pks)}">
                            <div class="mb-3">
                                <label class="form-label">Template Name</label>
                                <input type="text" name="template_name" class="form-control" required 
                                    placeholder="e.g., hello_world">
                                <small class="form-hint">Enter the exact template name from your WhatsApp Business account</small>
                            </div>
                            <div class="mb-3">
                                <label class="form-label">Language Code</label>
                                <input type="text" name="language_code" class="form-control" value="en_US" required 
                                    placeholder="e.g., en_US, hi_IN">
                                <small class="form-hint">Language code for the template (default: en_US)</small>
                            </div>
                            <div class="d-flex gap-2">
                                <button type="submit" class="btn btn-primary">Send Template</button>
                                <a href="{request.url_for('admin:list', identity=self.identity)}" 
                                   class="btn btn-secondary">Cancel</a>
                            </div>
                        </form>
                    </div>
                </div>
            </div>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_form)


class TemplateStorageAdmin(ModelView,model=TemplateStorage):
    column_list = [TemplateStorage.template_name]