from db.models import Product, Metal, Lead, Group, TemplateStorage, Referral, Feedback, Category, Review, Blog
from sqladmin import ModelView, action
from starlette.requests import Request
from starlette.responses import RedirectResponse
from starlette.datastructures import UploadFile as StarletteUploadFile
from wtforms import Form, TextAreaField, FileField, validators
from markupsafe import Markup
import os
import requests
from dotenv import load_dotenv

import azure_storage

load_dotenv()


def _image_cell(blob_or_url):
    """Render a small thumbnail (or '—') for a stored blob name / URL."""
    url = azure_storage.resolve_url(blob_or_url)
    if not url:
        return "—"
    return Markup(f'<img src="{url}" style="height:48px;border-radius:6px" />')

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
        Product.categories,
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
        Product.categories,
        Product.availability,
        Product.image_url
    ]

    column_labels = {
        "calculated_amount": "Amount (₹)",
        "gross_weight": "Gross Weight (g)",
        "metal_info": "Metal",
        "categories": "Categories",
        "availability": "Available",
        "image_url": "Image",
    }

    # Upload the image as a file (stored in Azure); the DB keeps the blob name.
    form_overrides = {"image_url": FileField}

    column_formatters = {
        "gross_weight": lambda m, a: f"{m.gross_weight:.3f}" if m.gross_weight else "0.000",
        "calculated_amount": lambda m, a: f"₹{m.calculated_amount:,.2f}" if m.calculated_amount else "₹0.00",
        "image_url": lambda m, a: _image_cell(m.image_url),
    }
    column_formatters_detail = {
        "image_url": lambda m, a: _image_cell(m.image_url),
    }

    async def on_model_change(self, data, model, is_created, request):
        """Upload a newly chosen image file to Azure and store its blob name."""
        upload = data.get("image_url")
        if isinstance(upload, StarletteUploadFile) and upload.filename:
            content = await upload.read()
            old = getattr(model, "image_url", None)
            data["image_url"] = azure_storage.upload_image(
                content, upload.content_type, prefix="products/"
            )
            if old and not is_created:
                azure_storage.delete_blob(old)
        else:
            # No new file chosen: keep existing value, don't overwrite with empty.
            data["image_url"] = None if is_created else getattr(model, "image_url", None)


class LeadAdmin(ModelView, model=Lead):
    name = "Lead"
    name_plural = "Leads"
    icon = "fa-solid fa-user"

    column_list = [
        Lead.id, Lead.name, Lead.tag, Lead.onboarding_state,
        Lead.referral_code, Lead.email, Lead.phone, Lead.created_at,
    ]
    column_searchable_list = [Lead.name, Lead.email, Lead.phone, Lead.referral_code]
    column_sortable_list = [Lead.id, Lead.name, Lead.created_at, Lead.onboarding_state]


    form_columns = [
        Lead.name, Lead.tag, Lead.onboarding_state, Lead.email, Lead.phone,
        Lead.referral_code,
    ]

    column_labels = {
        "created_at": "Created At",
        "onboarding_state": "Onboarding",
        "referral_code": "Referral Code",
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
        
        # Show template input form - Get group info and templates from database
        db = next(get_db())
        group_names = []
        total_leads = 0
        templates = []
        
        try:
            for pk in pks:
                group = db.query(Group).filter(Group.id == int(pk)).first()
                if group:
                    group_names.append(group.name)
                    total_leads += len(group.leads) if group.leads else 0
            
            # Fetch all templates from TemplateStorage
            templates = db.query(TemplateStorage).all()
        finally:
            db.close()
        
        # Build template options for dropdown
        template_options = ""
        if templates:
            for template in templates:
                note = f" - {template.template_note}" if template.template_note else ""
                template_options += f'<option value="{template.template_name}">{template.template_name}{note}</option>'
        else:
            template_options = '<option value="">No templates available</option>'
        
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
                                <select name="template_name" class="form-select" required>
                                    <option value="">Select a template...</option>
                                    {template_options}
                                </select>
                                <small class="form-hint">Select a template from your WhatsApp Business account</small>
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

    @action(
        name="send_template_advanced",
        label="Send Template (Advanced)",
        confirmation_message="Send advanced template to all leads in selected group(s)?",
        add_in_detail=True,
        add_in_list=True,
    )
    async def send_whatsapp_template_advanced(self, request: Request):
        """Send WhatsApp template with dynamic parameters and header media"""
        from db.models import get_db
        from starlette.responses import HTMLResponse
        import json
        
        # Get selected group IDs from the request
        pks = request.query_params.get("pks", "").split(",")
        
        if not pks or pks == [""]:
            request.session["_messages"] = [("error", "No groups selected")]
            return RedirectResponse(url=request.url_for("admin:list", identity=self.identity), status_code=302)
        
        # Check if form was submitted
        template_name = request.query_params.get("template_name", "").strip()
        
        if template_name:
            # Form submitted - process and send
            from send_msg import send_template_to_group
            
            language_code = request.query_params.get("language_code", "en_US").strip()
            header_media_url = request.query_params.get("header_media_url", "").strip()
            header_media_type = request.query_params.get("header_media_type", "image").strip()
            
            # Parse body parameters from form
            body_params_json = request.query_params.get("body_params", "").strip()
            body_parameters = {}
            
            if body_params_json:
                try:
                    body_parameters = json.loads(body_params_json)
                except:
                    pass
            
            total_sent = 0
            total_failed = 0
            
            # Send to each selected group
            for pk in pks:
                try:
                    result = send_template_to_group(
                        group_id=int(pk),
                        template_name=template_name,
                        language_code=language_code,
                        body_parameters=body_parameters if body_parameters else None,
                        header_media_url=header_media_url if header_media_url else None,
                        header_media_type=header_media_type,
                        use_named_parameters=True  # Use named parameters for WhatsApp templates
                    )
                    
                    if "error" not in result:
                        total_sent += result.get("successful", 0)
                        total_failed += result.get("failed", 0)
                except Exception as e:
                    total_failed += 1
            
            request.session["_messages"] = [(
                "success" if total_failed == 0 else "warning",
                f"Template sent to {total_sent} lead(s). {total_failed} failed."
            )]
            return RedirectResponse(url=request.url_for("admin:list", identity=self.identity), status_code=302)
        
        # Show form - Get group info and templates
        db = next(get_db())
        group_names = []
        total_leads = 0
        templates = []
        
        try:
            for pk in pks:
                group = db.query(Group).filter(Group.id == int(pk)).first()
                if group:
                    group_names.append(group.name)
                    total_leads += len(group.leads) if group.leads else 0
            
            templates = db.query(TemplateStorage).all()
        finally:
            db.close()
        
        # Build template options
        template_options = ""
        if templates:
            for template in templates:
                note = f" - {template.template_note}" if template.template_note else ""
                template_options += f'<option value="{template.template_name}">{template.template_name}{note}</option>'
        else:
            template_options = '<option value="">No templates available</option>'
        
        action_url = str(request.url)
        
        html_form = f"""
        <!DOCTYPE html>
        <html>
        <head>
            <title>Send Advanced WhatsApp Template</title>
            <link rel="stylesheet" href="/static/css/tabler.min.css">
            <style>
                .param-row {{
                    display: flex;
                    gap: 10px;
                    margin-bottom: 10px;
                    align-items: center;
                }}
                .param-row input {{
                    flex: 1;
                }}
                .param-row button {{
                    flex-shrink: 0;
                }}
            </style>
        </head>
        <body>
            <div class="container mt-5">
                <div class="card">
                    <div class="card-header">
                        <h3 class="card-title">Send Advanced WhatsApp Template</h3>
                    </div>
                    <div class="card-body">
                        <p><strong>Selected Groups:</strong> {', '.join(group_names)}</p>
                        <p><strong>Total Recipients:</strong> {total_leads} lead(s)</p>
                        
                        <form method="GET" action="{action_url}" id="templateForm">
                            <input type="hidden" name="pks" value="{','.join(pks)}">
                            <input type="hidden" name="body_params" id="bodyParamsInput">
                            
                            <div class="mb-3">
                                <label class="form-label">Template Name</label>
                                <select name="template_name" class="form-select" required>
                                    <option value="">Select a template...</option>
                                    {template_options}
                                </select>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">Language Code</label>
                                <input type="text" name="language_code" class="form-control" value="en_US" required>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">Header Image URL (Optional)</label>
                                <input type="url" name="header_media_url" class="form-control" 
                                    placeholder="https://example.com/image.jpg">
                                <small class="form-hint">Leave empty if template has no header image</small>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">Header Media Type</label>
                                <select name="header_media_type" class="form-select">
                                    <option value="image">Image</option>
                                    <option value="video">Video</option>
                                    <option value="document">Document</option>
                                </select>
                            </div>
                            
                            <div class="mb-3">
                                <label class="form-label">Body Parameters</label>
                                <small class="form-hint d-block mb-2">
                                    Add key-value pairs for template variables. 
                                    Use "name" as key to auto-fetch from lead name.
                                </small>
                                <div id="paramsContainer">
                                    <div class="param-row">
                                        <input type="text" class="form-control param-key" placeholder="Parameter name (e.g., name, jewel)">
                                        <input type="text" class="form-control param-value" placeholder="Value (leave empty for 'name' to auto-fetch)">
                                        <button type="button" class="btn btn-danger btn-sm" onclick="removeParam(this)">Remove</button>
                                    </div>
                                </div>
                                <button type="button" class="btn btn-secondary btn-sm mt-2" onclick="addParam()">Add Parameter</button>
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
            
            <script>
                function addParam() {{
                    const container = document.getElementById('paramsContainer');
                    const row = document.createElement('div');
                    row.className = 'param-row';
                    row.innerHTML = `
                        <input type="text" class="form-control param-key" placeholder="Parameter name (e.g., name, jewel)">
                        <input type="text" class="form-control param-value" placeholder="Value (leave empty for 'name' to auto-fetch)">
                        <button type="button" class="btn btn-danger btn-sm" onclick="removeParam(this)">Remove</button>
                    `;
                    container.appendChild(row);
                }}
                
                function removeParam(button) {{
                    button.parentElement.remove();
                }}
                
                document.getElementById('templateForm').addEventListener('submit', function(e) {{
                    const params = {{}};
                    const keys = document.querySelectorAll('.param-key');
                    const values = document.querySelectorAll('.param-value');
                    
                    keys.forEach((keyInput, index) => {{
                        const key = keyInput.value.trim();
                        const value = values[index].value.trim();
                        if (key) {{
                            params[key] = value;
                        }}
                    }});
                    
                    document.getElementById('bodyParamsInput').value = JSON.stringify(params);
                }});
            </script>
        </body>
        </html>
        """
        
        return HTMLResponse(content=html_form)


class TemplateStorageAdmin(ModelView, model=TemplateStorage):
    name = "Template"
    name_plural = "Templates"
    icon = "fa-solid fa-file-lines"

    column_list = [TemplateStorage.id, TemplateStorage.template_name, TemplateStorage.template_note]
    column_searchable_list = [TemplateStorage.template_name]
    column_sortable_list = [TemplateStorage.id, TemplateStorage.template_name]

    form_columns = [TemplateStorage.template_name, TemplateStorage.template_note]

    column_labels = {
        "template_name": "Template Name",
        "template_note": "Note"
    }


class ReferralAdmin(ModelView, model=Referral):
    name = "Referral"
    name_plural = "Referrals"
    icon = "fa-solid fa-share-nodes"

    column_list = [
        Referral.id,
        Referral.referrer,
        Referral.referred_name,
        Referral.referred_phone,
        Referral.referred_lead,
        Referral.status,
        Referral.referral_code,
        Referral.parent_referral,
        Referral.created_at,
        Referral.accepted_at,
    ]
    column_searchable_list = [Referral.referred_phone, Referral.referred_name, Referral.referral_code]
    column_sortable_list = [Referral.id, Referral.status, Referral.created_at, Referral.accepted_at]
    column_default_sort = [(Referral.created_at, True)]

    # Show the full referral tree on the detail page (referrals from referrals).
    column_details_list = [
        Referral.id,
        Referral.referrer,
        Referral.referred_name,
        Referral.referred_phone,
        Referral.referred_lead,
        Referral.status,
        Referral.referral_code,
        Referral.parent_referral,
        "child_referrals",
        Referral.created_at,
        Referral.accepted_at,
    ]

    form_columns = [
        Referral.referrer,
        Referral.referred_lead,
        Referral.referred_name,
        Referral.referred_phone,
        Referral.referral_code,
        Referral.status,
        Referral.parent_referral,
    ]

    column_labels = {
        "referrer": "Referred By",
        "referred_lead": "Joined Lead",
        "referred_name": "Friend Name",
        "referred_phone": "Friend Phone",
        "referral_code": "Code Used",
        "parent_referral": "Parent Referral",
        "child_referrals": "Referrals From This",
        "created_at": "Created At",
        "accepted_at": "Accepted At",
    }

    column_formatters = {
        "created_at": lambda m, a: m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else "",
        "accepted_at": lambda m, a: m.accepted_at.strftime("%Y-%m-%d %H:%M:%S") if m.accepted_at else "—",
    }


class FeedbackAdmin(ModelView, model=Feedback):
    name = "Feedback"
    name_plural = "Feedback"
    icon = "fa-solid fa-comment-dots"

    column_list = [
        Feedback.id,
        Feedback.name,
        Feedback.phone,
        Feedback.experience,
        Feedback.feedback_type,
        Feedback.product,
        Feedback.created_at,
    ]
    column_searchable_list = [Feedback.name, Feedback.phone]
    column_sortable_list = [Feedback.id, Feedback.experience, Feedback.feedback_type, Feedback.created_at]
    column_default_sort = [(Feedback.created_at, True)]

    form_columns = [
        Feedback.name,
        Feedback.phone,
        Feedback.experience,
        Feedback.feedback_type,
        Feedback.product,
        Feedback.description,
    ]

    column_labels = {
        "feedback_type": "Type",
        "product": "Product Purchased",
        "created_at": "Created At",
    }

    column_formatters = {
        "created_at": lambda m, a: m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else "",
    }


class CategoryAdmin(ModelView, model=Category):
    name = "Category"
    name_plural = "Categories"
    icon = "fa-solid fa-tags"

    column_list = [Category.id, Category.name, Category.products]
    column_searchable_list = [Category.name]
    column_sortable_list = [Category.id, Category.name]

    form_columns = [Category.name, Category.products]

    column_labels = {"products": "Items"}
    column_formatters = {
        "products": lambda m, a: f"{len(m.products)} item(s)" if m.products else "0 items",
    }


class ReviewAdmin(ModelView, model=Review):
    name = "Review"
    name_plural = "Reviews"
    icon = "fa-solid fa-star"

    column_list = [
        Review.id,
        Review.product,
        Review.rating,
        Review.name,
        Review.email,
        Review.created_at,
    ]
    column_searchable_list = [Review.name, Review.email]
    column_sortable_list = [Review.id, Review.rating, Review.created_at]
    column_default_sort = [(Review.created_at, True)]

    form_columns = [
        Review.product,
        Review.rating,
        Review.name,
        Review.email,
        Review.description,
    ]

    column_labels = {"product": "Item", "created_at": "Created At"}
    column_formatters = {
        "rating": lambda m, a: f"{m.rating}/5" if m.rating is not None else "",
        "created_at": lambda m, a: m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else "",
    }


class BlogAdmin(ModelView, model=Blog):
    name = "Blog"
    name_plural = "Blogs"
    icon = "fa-solid fa-newspaper"

    column_list = [Blog.id, Blog.heading, Blog.created_at]
    column_searchable_list = [Blog.heading]
    column_sortable_list = [Blog.id, Blog.heading, Blog.created_at]
    column_default_sort = [(Blog.created_at, True)]

    form_columns = [Blog.heading, Blog.description]

    column_labels = {"created_at": "Created At"}
    column_formatters = {
        "created_at": lambda m, a: m.created_at.strftime("%Y-%m-%d %H:%M:%S") if m.created_at else "",
    }