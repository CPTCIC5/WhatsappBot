from dotenv import load_dotenv
import os
import requests
from db.models import get_db, Group

load_dotenv()

token = os.getenv("ACCESS_TOKEN")
version = os.getenv("VERSION")
number_id = os.getenv("PHONE_NUMBER_ID")
# user = input("Enter the recipient's phone number (with country code, e.g., +1234567890): ")

############# FOR SENDING MESSAGES MANUALLY #############
def send_txt_msg(recipient_phone: str, message_text: str):
    """
    Send a text message to a specific WhatsApp number.
    
    Args:
        recipient_phone: The recipient's phone number (with country code)
        message_text: The message content to send
        
    Returns:
        requests.Response: The API response
    """
    url = f"https://graph.facebook.com/{version}/{number_id}/messages"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-type": "application/json"
    }

    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_phone,
        "type": "text",
        "text": {
            "body": message_text
        }
    }
    
    response = requests.post(url=url, headers=headers, json=data)
    return response

def send_group_messages(group_id: int, message_text: str):
    """
    Send a WhatsApp message to all leads in a specific group.
    
    Args:
        group_id: The ID of the group from the database
        message_text: The message content to send
        
    Returns:
        dict: Summary of sent messages with success/failure counts
    """
    db = next(get_db())
    
    try:
        # Fetch the group with its leads
        group = db.query(Group).filter(Group.id == group_id).first()
        
        if not group:
            return {"error": f"Group with ID {group_id} not found"}
        
        if not group.leads:
            return {"error": f"Group '{group.name}' has no leads"}
        
        results = {
            "group_name": group.name,
            "total_leads": len(group.leads),
            "successful": 0,
            "failed": 0,
            "details": []
        }
        
        url = f"https://graph.facebook.com/{version}/{number_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-type": "application/json"
        }
        
        # Send message to each lead in the group
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
                    results["successful"] += 1
                    results["details"].append({
                        "lead": lead.name,
                        "phone": lead.phone,
                        "status": "success"
                    })
                else:
                    results["failed"] += 1
                    results["details"].append({
                        "lead": lead.name,
                        "phone": lead.phone,
                        "status": "failed",
                        "error": response.json()
                    })
            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "lead": lead.name,
                    "phone": lead.phone,
                    "status": "failed",
                    "error": str(e)
                })
        
        return results
        
    finally:
        db.close()


# Example usage for individual message
# re = send_txt_msg()
# print(re.status_code)
# print(re.json())

# Example usage for group messages
# group_results = send_group_messages(group_id=1, message_text="Hello everyone in the group!")
# print(group_results)





def send_img(user_contact_number: str, link: str, caption: str): #JPG.JPEG,PNG
    url = f"https://graph.facebook.com/{version}/{number_id}/messages"
 
    headers = {
        "Authorization" : f"Bearer {token}",
        "Content-type": "application/json"
    }
 
    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": user_contact_number,
        "type": "image",
        "image": {
            "link": link,  
            "caption": caption 
        }
    }
 
    response = requests.post(url=url, headers=headers, json=data)
    return response

# print(send_img(user))

'''
def send_template_to_group(group_id: int, template_name: str, language_code: str = "en_US"):
    """
    Send a WhatsApp template message to all leads in a specific group.
    
    Args:
        group_id: The ID of the group from the database
        template_name: The name of the WhatsApp template to send
        language_code: The language code for the template (default: "en_US")
        
    Returns:
        dict: Summary of sent messages with success/failure counts
    """
    db = next(get_db())
    
    try:
        # Fetch the group with its leads
        group = db.query(Group).filter(Group.id == group_id).first()
        
        if not group:
            return {"error": f"Group with ID {group_id} not found"}
        
        if not group.leads:
            return {"error": f"Group '{group.name}' has no leads"}
        
        results = {
            "group_name": group.name,
            "template_name": template_name,
            "total_leads": len(group.leads),
            "successful": 0,
            "failed": 0,
            "details": []
        }
        
        url = f"https://graph.facebook.com/{version}/{number_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-type": "application/json"
        }
        
        # Send template message to each lead in the group
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
                    results["successful"] += 1
                    results["details"].append({
                        "lead": lead.name,
                        "phone": lead.phone,
                        "status": "success"
                    })
                else:
                    results["failed"] += 1
                    results["details"].append({
                        "lead": lead.name,
                        "phone": lead.phone,
                        "status": "failed",
                        "error": response.json()
                    })
            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "lead": lead.name,
                    "phone": lead.phone,
                    "status": "failed",
                    "error": str(e)
                })
        
        return results
        
    finally:
        db.close()
'''

# Example usage for template messages
# template_results = send_template_to_group(group_id=1, template_name="hello_world")
# print(template_results)

def send_template_to_group(
    group_id: int,
    template_name: str,
    language_code: str = "en_US",
    body_parameters: dict = None,       # e.g. {"name": "", "jewel": "Necklace Set"}
    header_media_url: str = None,             # e.g. "https://example.com/image.jpg"
    header_media_type: str = "image",         # "image", "video", or "document"
    use_named_parameters: bool = True,  # Set to True for named parameters, False for positional
):
    """
    Send a WhatsApp template message to all leads in a specific group.
    Args:
        group_id: The ID of the group from the database
        template_name: The name of the WhatsApp template to send
        language_code: The language code for the template (default: "en_US")
        body_parameters: Dict of parameter names and values. If parameter name is "name" and value is empty, 
                        it will auto-fetch from lead.name
        header_media_url: Optional URL for media in the header (image/video/document)
        header_media_type: Type of media — "image", "video", or "document"
        use_named_parameters: Whether to use named parameters (True) or positional (False)
    Returns:
        dict: Summary of sent messages with success/failure counts
    """
    db = next(get_db())
    try:
        group = db.query(Group).filter(Group.id == group_id).first()
        if not group:
            return {"error": f"Group with ID {group_id} not found"}
        if not group.leads:
            return {"error": f"Group '{group.name}' has no leads"}

        results = {
            "group_name": group.name,
            "template_name": template_name,
            "total_leads": len(group.leads),
            "successful": 0,
            "failed": 0,
            "details": []
        }

        url = f"https://graph.facebook.com/{version}/{number_id}/messages"
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-type": "application/json"
        }

        for lead in group.leads:
            # Build the components list for each lead
            components = []

            # Header component (media)
            if header_media_url:
                components.append({
                    "type": "header",
                    "parameters": [
                        {
                            "type": header_media_type,
                            header_media_type: {
                                "link": header_media_url
                            }
                        }
                    ]
                })

            # Body component (text parameters)
            if body_parameters:
                body_params_list = []
                for param_name, param_value in body_parameters.items():
                    # Auto-fetch lead name if parameter name is "name" and value is empty
                    if param_name.lower() == "name" and not param_value:
                        param_value = lead.name
                    
                    # Only add if value is not empty
                    if param_value:
                        if use_named_parameters:
                            # Named parameter format (newer WhatsApp API)
                            body_params_list.append({
                                "type": "text",
                                "text": str(param_value),
                                "parameter_name": param_name
                            })
                        else:
                            # Positional parameter format (older WhatsApp API)
                            body_params_list.append({
                                "type": "text",
                                "text": str(param_value)
                            })
                
                if body_params_list:
                    components.append({
                        "type": "body",
                        "parameters": body_params_list
                    })

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

            # Only attach components if there are any
            if components:
                data["template"]["components"] = components

            try:
                response = requests.post(url=url, headers=headers, json=data)
                if response.status_code == 200:
                    results["successful"] += 1
                    results["details"].append({
                        "lead": lead.name,
                        "phone": lead.phone,
                        "status": "success"
                    })
                else:
                    results["failed"] += 1
                    results["details"].append({
                        "lead": lead.name,
                        "phone": lead.phone,
                        "status": "failed",
                        "error": response.json()
                    })
            except Exception as e:
                results["failed"] += 1
                results["details"].append({
                    "lead": lead.name,
                    "phone": lead.phone,
                    "status": "failed",
                    "error": str(e)
                })

        return results
    finally:
        db.close()


#Example CLI command to test
"""
send_template_to_group(
    group_id=1,
    template_name="monday_template",
    body_parameters={"name": "Aryan", "jewel": "Necklace Set"},
    header_media_url="https://i.imgur.com/RYBkxXL.jpeg",
    header_media_type="image",
    use_named_parameters=True  # Set to True for named parameters (default), False for positional
)

# For auto-fetch lead name, leave the value empty:
send_template_to_group(
    group_id=1,
    template_name="monday_template",
    body_parameters={"name": "", "jewel": "Necklace Set"},  # name will auto-fetch from lead.name
    header_media_url="https://i.imgur.com/RYBkxXL.jpeg",
    header_media_type="image"
)
"""

async def send_txt_msg_async(recipient_phone: str, message_text: str):
    """
    Simple async version of send_txt_msg for better performance.
    
    Args:
        recipient_phone: The recipient's phone number (with country code)
        message_text: The message content to send
        
    Returns:
        httpx.Response: The API response
    """
    import httpx
    
    url = f"https://graph.facebook.com/{version}/{number_id}/messages"

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-type": "application/json"
    }

    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_phone,
        "type": "text",
        "text": {
            "body": message_text
        }
    }
    
    # Simple async client with reasonable timeout
    async with httpx.AsyncClient(timeout=30.0) as client:
        response = await client.post(url=url, headers=headers, json=data)
        return response


# ---------------------------------------------------------------------------
# Milestone 3: interactive onboarding helpers (async)
# ---------------------------------------------------------------------------

async def _post_async(data: dict):
    """POST a payload to the WhatsApp messages endpoint asynchronously."""
    import httpx

    url = f"https://graph.facebook.com/{version}/{number_id}/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-type": "application/json",
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        return await client.post(url=url, headers=headers, json=data)


async def send_img_async(recipient_phone: str, link: str, caption: str = ""):
    """Async version of send_img (JPG/JPEG/PNG)."""
    return await _post_async({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_phone,
        "type": "image",
        "image": {"link": link, "caption": caption},
    })


async def send_template_async(
    recipient_phone: str,
    template_name: str,
    language_code: str = "en_US",
    body_parameters: list | None = None,
    header_media_url: str | None = None,
    header_media_type: str = "image",
):
    """Send a WhatsApp approved template to a single recipient (async).

    Args:
        recipient_phone: recipient WhatsApp number
        template_name: name of the approved template (e.g. "welcome_template")
        language_code: template language code
        body_parameters: optional list of text values for body {{1}}, {{2}}...
        header_media_url: optional media URL for a dynamic header
        header_media_type: "image", "video", or "document"
    """
    components = []
    if header_media_url:
        components.append({
            "type": "header",
            "parameters": [
                {"type": header_media_type, header_media_type: {"link": header_media_url}}
            ],
        })
    if body_parameters:
        components.append({
            "type": "body",
            "parameters": [{"type": "text", "text": str(v)} for v in body_parameters],
        })

    template: dict = {"name": template_name, "language": {"code": language_code}}
    if components:
        template["components"] = components

    return await _post_async({
        "messaging_product": "whatsapp",
        "to": recipient_phone,
        "type": "template",
        "template": template,
    })


async def send_interactive_buttons(
    recipient_phone: str,
    body_text: str,
    buttons: list,
    header_image_url: str | None = None,
    header_text: str | None = None,
    footer_text: str | None = None,
):
    """Send an interactive reply-button message (max 3 buttons).

    Args:
        recipient_phone: recipient WhatsApp number
        body_text: main message body
        buttons: list of {"id": str, "title": str} (title <= 20 chars)
        header_image_url: optional poster/image shown above the body
        header_text: optional text header (ignored if header_image_url given)
        footer_text: optional small footer text
    """
    action_buttons = [
        {"type": "reply", "reply": {"id": b["id"], "title": b["title"][:20]}}
        for b in buttons[:3]
    ]

    interactive: dict = {
        "type": "button",
        "body": {"text": body_text},
        "action": {"buttons": action_buttons},
    }

    if header_image_url:
        interactive["header"] = {"type": "image", "image": {"link": header_image_url}}
    elif header_text:
        interactive["header"] = {"type": "text", "text": header_text[:60]}

    if footer_text:
        interactive["footer"] = {"text": footer_text[:60]}

    return await _post_async({
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": recipient_phone,
        "type": "interactive",
        "interactive": interactive,
    })