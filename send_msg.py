from dotenv import load_dotenv
import os
import requests
from db.models import get_db, Group

load_dotenv()

token = os.getenv("ACCESS_TOKEN")
version = os.getenv("VERSION")
number_id = os.getenv("PHONE_NUMBER_ID")
user = input("Enter the recipient's phone number (with country code, e.g., +1234567890): ")

############# FOR SENDING MESSAGES MANUALLY #############
def send_txt_msg():
    url = f"https://graph.facebook.com/v24.0/{number_id}/messages"

    headers = {
        "Authorization" : f"Bearer {token}",
        "Content-type": "application/json"
    }

    data = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": user,
        "type": "text",
    
        "text": {
            "body": "Hey i am sending this msg from vscode lol. " # use body to send msgs 
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
