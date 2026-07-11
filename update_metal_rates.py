import os
import requests
from dotenv import load_dotenv
from db.models import SessionLocal, Metal

def fetch_and_update_rates():
    load_dotenv()
    
    api_key = os.getenv("METAL_PRICE_API_KEY")
    base_url = os.getenv("METAL_PRICE_BASE_URL", "https://api.metalpriceapi.com/v1/latest")
    
    if not api_key:
        print("Error: METAL_PRICE_API_KEY not found in environment variables.")
        return

    # Fetch global gold rate (XAU) and INR conversion
    params = {
        "api_key": api_key,
        "base": "USD",
        "currencies": "INR,XAU"
    }
    
    print(f"Fetching metal rates from {base_url}...")
    try:
        response = requests.get(base_url, params=params)
        response.raise_for_status()
        data = response.json()
    except requests.exceptions.RequestException as e:
        print(f"Failed to fetch data: {e}")
        return
        
    if not data.get("success"):
        print(f"API Error: {data.get('error')}")
        return
        
    rates = data.get("rates", {})
    inr_rate = rates.get("INR")
    xau_rate = rates.get("XAU")
    
    if not inr_rate or not xau_rate:
        print("Required rates (INR, XAU) missing in response.")
        return
        
    # Calculate 1 Troy Ounce of Gold in INR
    # Base is USD, so 1 USD = xau_rate XAU
    # Price of 1 XAU in USD = 1 / xau_rate
    price_xau_usd = 1.0 / xau_rate
    
    # Convert to INR (1 USD = inr_rate INR)
    price_xau_inr = price_xau_usd * inr_rate
    
    # 1 Troy Ounce = 31.1034768 grams
    grams_per_troy_ounce = 31.1034768
    
    # Base 24K price per gram (International Spot Rate)
    base_price_24k_per_gram = price_xau_inr / grams_per_troy_ounce
    
    # Apply Indian market premium (import duty, GST, local premium)
    # Market rate for Faridabad is typically ~13.4% higher than international spot
    premium_multiplier = float(os.getenv("INDIA_GOLD_PREMIUM_MULTIPLIER", "1.134"))
    price_24k_per_gram = base_price_24k_per_gram * premium_multiplier
    
    karat_calculations = {
        "24K": price_24k_per_gram,
        "22K": price_24k_per_gram * (22 / 24),
        "20K": price_24k_per_gram * (20 / 24),
        "18K": price_24k_per_gram * (18 / 24),
        "14K": price_24k_per_gram * (14 / 24)
    }
    
    print("\n--- Calculated Gold Rates (per gram in INR) ---")
    for k, price in karat_calculations.items():
        print(f"{k}: ₹{price:.2f}")
        
    # Update Database
    db = SessionLocal()
    try:
        for karat, price in karat_calculations.items():
            # Check if exists
            metal_record = db.query(Metal).filter(Metal.metal == "Gold", Metal.karat == karat).first()
            if metal_record:
                metal_record.rate_per_gram = round(price, 2)
                print(f"Updated Gold {karat} to {metal_record.rate_per_gram}")
            else:
                new_metal = Metal(metal="Gold", karat=karat, rate_per_gram=round(price, 2))
                db.add(new_metal)
                print(f"Created Gold {karat} with rate {new_metal.rate_per_gram}")
        db.commit()
        print("\nSuccessfully updated database!")
    except Exception as e:
        db.rollback()
        print(f"Database error: {e}")
    finally:
        db.close()

if __name__ == "__main__":
    fetch_and_update_rates()
