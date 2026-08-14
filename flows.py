"""
Milestone 3 — message orchestration for the WhatsApp chatbot.

This module is the single entry point for every inbound WhatsApp message. It
handles three pillars of Milestone 3:

1. Onboarding   — first contact sends welcome_template_v1 once, then a fixed
                  Meta-template flow: occasion → budget → trust → category.
2. AI replies   — after the flow (or for returning leads), small/common queries
                  are answered by the assistant; big/complex queries escalate
                  (handled inside ai.chat_with_assistant).
3. Referrals    — a fully managed, notification-based referral programme with
                  forwardable referral messages and support for referral chains
                  ("referrals from referrals").
"""

import os
import re
import random
import string
import logging
from datetime import datetime

from sqlalchemy.orm import joinedload

from db.models import SessionLocal, Lead, Referral, Product, Category, Metal, TemplateStorage
from send_msg import (
    send_txt_msg_async,
    send_interactive_buttons,
    send_template_async,
    send_img_async,
    send_document_async,
)

logger = logging.getLogger(__name__)


def _flow_log(msg: str) -> None:
    """Print + log so demo steps show in the webhook terminal."""
    line = f"[FLOW] {msg}"
    print(line, flush=True)
    logger.info(line)

# --- Configuration -----------------------------------------------------------
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "support@ridra.in")
# Poster/image shown on the onboarding welcome (optional).
ONBOARDING_POSTER_URL = os.getenv("ONBOARDING_POSTER_URL", "").strip()
# Business WhatsApp number (digits only) used to build wa.me forward links.
BUSINESS_WA_NUMBER = re.sub(r"\D", "", os.getenv("BUSINESS_WA_NUMBER", ""))

TEMPLATE_LANG = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")
WELCOME_TEMPLATE_NAME = os.getenv("WELCOME_TEMPLATE_NAME", "welcome_template_v1")
OCCASION_TEMPLATE_NAME = os.getenv("OCCASION_TEMPLATE_NAME", "occasion_template")
BUDGET_TEMPLATE_NAME = os.getenv("BUDGET_TEMPLATE_NAME", "budget_template")
TRUST_TEMPLATE_NAME = os.getenv("TRUST_TEMPLATE_NAME", "trust_template_v1")
CATEGORY_TEMPLATE_NAME = os.getenv("CATEGORY_TEMPLATE_NAME", "category_template_v1")
WELCOME_HEADER_MEDIA_URL = os.getenv(
    "WELCOME_HEADER_MEDIA_URL",
    "https://i.imgur.com/RYBkxXL.jpeg",
).strip()
JEWELLERY_HANDBOOK_URL = os.getenv("JEWELLERY_HANDBOOK_URL", "").strip()

# flow_stage values while the lead is inside the template flow
FLOW_WELCOME = "flow_welcome"
FLOW_OCCASION = "flow_occasion"
FLOW_BUDGET = "flow_budget"
FLOW_TRUST = "flow_trust"
FLOW_CATEGORY = "flow_category"
FLOW_INTENTS = {
    FLOW_WELCOME,
    FLOW_OCCASION,
    FLOW_BUDGET,
    FLOW_TRUST,
    FLOW_CATEGORY,
}

# Reply-button identifiers for the onboarding menu (fallback / follow-up).
BTN_BROWSE = "onb_browse"
BTN_REFER = "onb_refer"
BTN_CONTACT = "onb_contact"
BTN_EXPLORE = "flow_explore"
BTN_HANDBOOK = "flow_handbook"

# Referral codes look like RIDRA-AB12CD
REFERRAL_PREFIX = "RIDRA-"
REFERRAL_CODE_RE = re.compile(r"RIDRA-([A-Z0-9]{6})", re.IGNORECASE)


# --- Referral codes ----------------------------------------------------------

def generate_referral_code() -> str:
    """Generate a unique-ish referral code like RIDRA-AB12CD."""
    suffix = "".join(random.choices(string.ascii_uppercase + string.digits, k=6))
    return f"{REFERRAL_PREFIX}{suffix}"


def ensure_referral_code(db, lead: Lead) -> str:
    """Assign a referral code to the lead if it doesn't have one yet."""
    if lead.referral_code:
        return lead.referral_code
    for _ in range(5):
        code = generate_referral_code()
        if not db.query(Lead).filter(Lead.referral_code == code).first():
            lead.referral_code = code
            db.commit()
            return code
    # Extremely unlikely fallback: append the lead id for uniqueness
    lead.referral_code = f"{generate_referral_code()}{lead.id}"
    db.commit()
    return lead.referral_code


def build_forward_message(lead: Lead) -> str:
    """Build the forwardable referral message a customer can send to friends."""
    name = lead.name or "a friend"
    code = lead.referral_code
    lines = [
        "Hi! ✨ I've been loving the jewelry at *Ridra Jewellers* 💎",
        "",
        "Check them out — just send this message to get a warm welcome:",
        "",
        f'"Hi Ridra! I was referred by {name}. My code: {code}"',
    ]
    if BUSINESS_WA_NUMBER:
        lines += ["", f"👉 https://wa.me/{BUSINESS_WA_NUMBER}"]
    return "\n".join(lines)


# --- Lead lifecycle ----------------------------------------------------------

def get_or_create_lead(db, wa_id: str, name: str | None) -> tuple[Lead, bool]:
    """Return (lead, created). Creates the lead (with an OpenAI conversation
    and a referral code) on first contact."""
    lead = db.query(Lead).filter(Lead.phone == wa_id).first()
    if lead:
        # Backfill conversation/referral code for older leads.
        if not lead.thread_id:
            lead.thread_id = _new_conversation_id()
        ensure_referral_code(db, lead)
        db.commit()
        return lead, False

    lead = Lead(
        phone=wa_id,
        name=name,
        thread_id=_new_conversation_id(),
        onboarding_state="new",
    )
    db.add(lead)
    db.commit()
    db.refresh(lead)
    ensure_referral_code(db, lead)
    logger.info(f"New lead created: {wa_id}")
    return lead, True


def _new_conversation_id() -> str | None:
    """Create an OpenAI conversation and return its id (None on failure)."""
    try:
        from openai import OpenAI

        return OpenAI().conversations.create().id
    except Exception as e:
        logger.error(f"Failed to create OpenAI conversation: {e}")
        return None


# --- Template flow helpers ---------------------------------------------------

def _first_name(lead: Lead) -> str:
    return (lead.name or "there").split(" ")[0]


def _is_handbook(text: str) -> bool:
    t = (text or "").lower()
    return any(w in t for w in ("handbook", "hand book", "pdf", "guide", BTN_HANDBOOK))


def _is_explore(text: str) -> bool:
    t = (text or "").lower()
    if _is_handbook(t):
        return False
    return any(
        w in t
        for w in ("explore", "collection", "browse", "see our", BTN_EXPLORE, BTN_BROWSE)
    )


def parse_budget(text: str) -> tuple[float | None, float | None]:
    """Parse a budget button/label into (min, max). Either side may be None."""
    if not text:
        return None, None
    t = text.lower().replace(",", "").replace("₹", "").replace("rs.", " ").replace("rs", " ")
    t = re.sub(
        r"(\d+(?:\.\d+)?)\s*k\b",
        lambda m: str(int(float(m.group(1)) * 1000)),
        t,
    )
    t = re.sub(
        r"(\d+(?:\.\d+)?)\s*(lakh|lac)s?\b",
        lambda m: str(int(float(m.group(1)) * 100_000)),
        t,
    )
    t = re.sub(
        r"(\d+(?:\.\d+)?)\s*crores?\b",
        lambda m: str(int(float(m.group(1)) * 10_000_000)),
        t,
    )
    nums = [float(x) for x in re.findall(r"\d+(?:\.\d+)?", t)]
    if not nums:
        return None, None
    if any(w in t for w in ("under", "below", "less", "upto", "up to", "<")):
        return None, nums[0]
    if any(w in t for w in ("above", "over", "more", "+", "greater")):
        return nums[0], None
    if len(nums) >= 2:
        return min(nums[0], nums[1]), max(nums[0], nums[1])
    return None, nums[0]


def _lead_placeholders(lead: Lead) -> dict[str, str]:
    first = _first_name(lead)
    return {
        "first_name": first,
        "name": first,
        "phone": lead.phone or "",
        "occasion": lead.occasion or "",
        "budget": lead.budget_label or "",
        "category": lead.preferred_category or "",
    }


def _fill_body_parameters(raw, lead: Lead) -> dict | None:
    """Turn stored JSON body params into Meta values, filling {placeholders}."""
    if not raw:
        return None
    if isinstance(raw, str):
        import json

        try:
            raw = json.loads(raw)
        except Exception:
            return None
    if not isinstance(raw, dict):
        return None
    mapping = _lead_placeholders(lead)
    filled: dict[str, str] = {}
    for key, value in raw.items():
        if value is None or value == "":
            continue
        text = str(value)
        for placeholder, replacement in mapping.items():
            text = text.replace("{" + placeholder + "}", replacement)
        filled[str(key)] = text
    return filled or None


def _template_header_url(row: TemplateStorage) -> str | None:
    import azure_storage

    return azure_storage.resolve_url(row.header_image_blob or row.header_media_url)


_FLOW_SLUG_FALLBACK = {
    "welcome": WELCOME_TEMPLATE_NAME,
    "occasion": OCCASION_TEMPLATE_NAME,
    "budget": BUDGET_TEMPLATE_NAME,
    "trust": TRUST_TEMPLATE_NAME,
    "category": CATEGORY_TEMPLATE_NAME,
}


async def _send_registered_template(db, lead: Lead, slug: str, **overrides) -> bool:
    """Send the Meta template registered under `slug`, with hardcoded fallback."""
    row = (
        db.query(TemplateStorage)
        .filter(TemplateStorage.slug == slug, TemplateStorage.is_active.is_(True))
        .first()
    )
    if row and row.template_name:
        kwargs: dict = {
            "use_named_parameters": bool(row.use_named_parameters),
        }
        body = _fill_body_parameters(row.body_parameters, lead)
        if body:
            kwargs["body_parameters"] = body
        header = _template_header_url(row)
        if header:
            kwargs["header_media_url"] = header
            kwargs["header_media_type"] = row.header_media_type or "image"
        kwargs.update({k: v for k, v in overrides.items() if v is not None})
        _flow_log(f"DB TEMPLATE slug={slug} meta={row.template_name}")
        return await _send_flow_template(
            lead,
            row.template_name,
            language_code=row.language_code or TEMPLATE_LANG,
            **kwargs,
        )

    fallback_name = _FLOW_SLUG_FALLBACK.get(slug)
    if not fallback_name:
        _flow_log(f"No registered or fallback template for slug={slug}")
        return False
    kwargs = {k: v for k, v in overrides.items() if v is not None}
    if slug == "welcome":
        kwargs.setdefault("body_parameters", {"name": _first_name(lead)})
        kwargs.setdefault(
            "header_media_url", WELCOME_HEADER_MEDIA_URL or ONBOARDING_POSTER_URL or None
        )
    _flow_log(f"FALLBACK TEMPLATE slug={slug} meta={fallback_name}")
    return await _send_flow_template(lead, fallback_name, **kwargs)


async def _send_flow_template(lead: Lead, template_name: str, language_code: str | None = None, **kwargs) -> bool:
    _flow_log(
        f"SEND TEMPLATE '{template_name}' → {lead.phone} "
        f"kwargs={ {k: v for k, v in kwargs.items() if v} }"
    )
    try:
        resp = await send_template_async(
            recipient_phone=lead.phone,
            template_name=template_name,
            language_code=language_code or TEMPLATE_LANG,
            **kwargs,
        )
        _flow_log(
            f"TEMPLATE '{template_name}' response {resp.status_code}: {resp.text}"
        )
        if resp.status_code == 200:
            return True
        logger.error(
            f"{template_name} send failed ({resp.status_code}) for "
            f"{lead.phone}: {resp.text}"
        )
    except Exception as e:
        _flow_log(f"TEMPLATE '{template_name}' ERRORED: {e}")
        logger.error(f"{template_name} send errored for {lead.phone}: {e}")
    return False


async def _send_handbook(lead: Lead) -> None:
    if not JEWELLERY_HANDBOOK_URL:
        await send_txt_msg_async(
            lead.phone,
            "Our jewellery handbook isn't available as a file just yet. "
            f"Email us at {CONTACT_EMAIL} and we'll share it with you ✨",
        )
        return
    try:
        resp = await send_document_async(
            recipient_phone=lead.phone,
            link=JEWELLERY_HANDBOOK_URL,
            filename="Ridra Jewellery Handbook.pdf",
            caption="Our jewellery handbook ✨",
        )
        if resp.status_code != 200:
            logger.error(
                f"Handbook send failed ({resp.status_code}) for "
                f"{lead.phone}: {resp.text}"
            )
            await send_txt_msg_async(
                lead.phone,
                "I couldn't send the handbook just now. Please try again in a moment ✨",
            )
    except Exception as e:
        logger.error(f"Handbook send errored for {lead.phone}: {e}")
        await send_txt_msg_async(
            lead.phone,
            "I couldn't send the handbook just now. Please try again in a moment ✨",
        )


def _product_image_url(product: Product) -> str | None:
    import azure_storage

    if product.image_url:
        return azure_storage.resolve_url(product.image_url)
    images = getattr(product, "images", None) or []
    if images:
        return azure_storage.resolve_url(images[0].blob_name)
    return None


def _match_category(db, text: str) -> Category | None:
    if not text:
        return None
    t = text.strip().lower()
    cats = db.query(Category).all()
    for cat in cats:
        if (cat.name or "").lower() == t:
            return cat
    for cat in cats:
        name = (cat.name or "").lower()
        if name and (name in t or t in name):
            return cat
    return None


def _products_for_category_budget(db, category: Category, lead: Lead, limit: int = 5):
    amount = Product.gross_weight * Metal.rate_per_gram
    q = (
        db.query(Product)
        .options(joinedload(Product.metal_info), joinedload(Product.images))
        .join(Product.metal_info)
        .filter(Product.availability.is_(True))
        .filter(Product.categories.any(Category.id == category.id))
    )
    if lead.budget_min is not None:
        q = q.filter(amount >= lead.budget_min)
    if lead.budget_max is not None:
        q = q.filter(amount <= lead.budget_max)
    return q.limit(limit).all()


async def _send_occasion(db, lead: Lead) -> None:
    if await _send_registered_template(db, lead, "occasion"):
        lead.flow_stage = FLOW_OCCASION
        db.commit()
        return
    await send_txt_msg_async(
        lead.phone,
        "What occasion are you shopping for? (e.g. wedding, gift, everyday) ✨",
    )
    lead.flow_stage = FLOW_OCCASION
    db.commit()


async def _send_budget(db, lead: Lead) -> None:
    if await _send_registered_template(db, lead, "budget"):
        lead.flow_stage = FLOW_BUDGET
        db.commit()
        return
    await send_txt_msg_async(
        lead.phone,
        "What's your budget range for this piece? 💎",
    )
    lead.flow_stage = FLOW_BUDGET
    db.commit()


async def _send_trust(db, lead: Lead) -> None:
    if await _send_registered_template(db, lead, "trust"):
        lead.flow_stage = FLOW_TRUST
        db.commit()
        return
    await send_txt_msg_async(
        lead.phone,
        "Would you like to *see our collection* or *read our handbook*? ✨",
    )
    lead.flow_stage = FLOW_TRUST
    db.commit()


async def _send_category(db, lead: Lead) -> None:
    if await _send_registered_template(db, lead, "category"):
        lead.flow_stage = FLOW_CATEGORY
        db.commit()
        return
    names = [c.name for c in db.query(Category).all() if c.name]
    hint = f" Pick one: {', '.join(names)}." if names else ""
    await send_txt_msg_async(
        lead.phone,
        f"Which category would you like to explore?{hint} ✨",
    )
    lead.flow_stage = FLOW_CATEGORY
    db.commit()


async def _show_category_products(db, lead: Lead, reply: str) -> None:
    category = _match_category(db, reply)
    if not category:
        names = [c.name for c in db.query(Category).all() if c.name]
        hint = f" ({', '.join(names)})" if names else ""
        await send_txt_msg_async(
            lead.phone,
            f"Please tap a category from the options above{hint} ✨",
        )
        return

    lead.preferred_category = category.name
    products = _products_for_category_budget(db, category, lead)
    db.commit()

    if not products:
        budget_bit = f" in {lead.budget_label}" if lead.budget_label else ""
        await send_txt_msg_async(
            lead.phone,
            f"I don't have *{category.name}* pieces{budget_bit} in stock right now. "
            "Tell me what you're looking for and I'll help you find something ✨",
        )
    else:
        budget_bit = f" within {lead.budget_label}" if lead.budget_label else ""
        await send_txt_msg_async(
            lead.phone,
            f"Here are some *{category.name}* pieces{budget_bit} 💎",
        )
        for product in products:
            price = product.calculated_amount
            caption = f"*{product.name}*"
            if price:
                caption += f"\n₹{price:,.0f}"
            if product.description:
                caption += f"\n{product.description[:120]}"
            image_url = _product_image_url(product)
            try:
                if image_url:
                    await send_img_async(lead.phone, image_url, caption)
                else:
                    await send_txt_msg_async(lead.phone, caption)
            except Exception as e:
                logger.error(f"Failed to send product {product.id} to {lead.phone}: {e}")
        await send_txt_msg_async(
            lead.phone,
            "Want to see more, or have a style in mind? Just tell me ✨",
        )

    lead.flow_stage = None
    lead.onboarding_state = "engaged"
    db.commit()


# --- Onboarding --------------------------------------------------------------

async def send_welcome(db, lead: Lead) -> None:
    """Send welcome_template_v1 on first contact only, then wait for a button tap."""
    _flow_log(
        f"STEP send_welcome() first-contact lead={lead.phone} "
        f"name={lead.name!r} state={lead.onboarding_state}"
    )
    sent = await _send_registered_template(db, lead, "welcome")
    if not sent:
        await _send_welcome_menu(lead)

    lead.onboarding_state = "welcomed"
    lead.flow_stage = FLOW_WELCOME
    db.commit()
    _flow_log(
        f"STEP send_welcome() done sent={sent} "
        f"onboarding_state=welcomed flow_stage={FLOW_WELCOME}"
    )


async def _send_welcome_menu(lead: Lead) -> None:
    """Interactive fallback when the welcome template can't be sent."""
    body = (
        f"Welcome to *Ridra Jewellers*, {_first_name(lead)}! ✨\n\n"
        "Every piece here tells a story 💎 What would you like to do?"
    )
    buttons = [
        {"id": BTN_EXPLORE, "title": "Explore collection"},
        {"id": BTN_HANDBOOK, "title": "Jewellery handbook"},
    ]
    try:
        await send_interactive_buttons(
            recipient_phone=lead.phone,
            body_text=body,
            buttons=buttons,
            header_image_url=WELCOME_HEADER_MEDIA_URL or ONBOARDING_POSTER_URL or None,
            footer_text="Ridra Jewellers",
        )
    except Exception as e:
        logger.error(f"Interactive welcome failed for {lead.phone}: {e}")
        await send_txt_msg_async(
            lead.phone,
            f"{body}\n\nReply: Explore our collection, or Jewellery handbook.",
        )


async def handle_flow_reply(db, lead: Lead, reply: str | None) -> None:
    """Advance the template onboarding flow from a button tap or short reply."""
    if not reply or not reply.strip():
        await send_txt_msg_async(lead.phone, "Please tap one of the options above ✨")
        return

    reply = reply.strip()
    intent = lead.flow_stage
    _flow_log(f"STEP handle_flow_reply() stage={intent} reply={reply!r}")

    if intent == FLOW_WELCOME:
        if _is_handbook(reply):
            _flow_log("BRANCH welcome → handbook PDF")
            await _send_handbook(lead)
            return
        if _is_explore(reply):
            _flow_log("BRANCH welcome → occasion_template")
            await _send_occasion(db, lead)
            return
        _flow_log("BRANCH welcome → unmatched reply, prompt buttons")
        await send_txt_msg_async(
            lead.phone,
            "Please tap *Explore our collection* or *Jewellery handbook* ✨",
        )
        return

    if intent == FLOW_OCCASION:
        _flow_log(f"BRANCH occasion saved={reply!r} → budget_template")
        lead.occasion = reply[:120]
        db.commit()
        await _send_budget(db, lead)
        return

    if intent == FLOW_BUDGET:
        bmin, bmax = parse_budget(reply)
        _flow_log(
            f"BRANCH budget saved={reply!r} min={bmin} max={bmax} → trust_template"
        )
        lead.budget_label = reply[:120]
        lead.budget_min, lead.budget_max = bmin, bmax
        db.commit()
        await _send_trust(db, lead)
        return

    if intent == FLOW_TRUST:
        if _is_handbook(reply):
            _flow_log("BRANCH trust → handbook PDF")
            await _send_handbook(lead)
            return
        if _is_explore(reply) or "see" in reply.lower():
            _flow_log("BRANCH trust → category_template")
            await _send_category(db, lead)
            return
        _flow_log("BRANCH trust → unmatched reply, prompt buttons")
        await send_txt_msg_async(
            lead.phone,
            "Please tap *See our collection* or *Read our handbook* ✨",
        )
        return

    if intent == FLOW_CATEGORY:
        _flow_log(f"BRANCH category reply={reply!r} → search products")
        await _show_category_products(db, lead, reply)
        return


# --- Onboarding button actions ----------------------------------------------

async def handle_action(db, lead: Lead, action_id: str) -> None:
    """Handle leftover interactive-menu taps (refer / contact) outside the flow."""
    if action_id == BTN_REFER:
        await _action_refer(db, lead)
        return
    if action_id == BTN_CONTACT:
        await _action_contact(db, lead)
        if lead.onboarding_state != "engaged":
            lead.onboarding_state = "engaged"
            db.commit()
        return
    if action_id in (BTN_BROWSE, BTN_EXPLORE) or _is_explore(action_id):
        await _send_occasion(db, lead)
        return
    if _is_handbook(action_id):
        await _send_handbook(lead)
        return
    logger.info(f"Unknown action id '{action_id}' from {lead.phone}")
    await send_txt_msg_async(
        lead.phone,
        "Tell me what you're looking for and I'll help you find it! ✨",
    )


async def _action_contact(db, lead: Lead) -> None:
    await send_txt_msg_async(
        lead.phone,
        "We'd love to help you personally! 💎\n\n"
        f"📧 Email: {CONTACT_EMAIL}\n"
        "You can also keep chatting here for anything you need. ✨",
    )


async def _action_refer(db, lead: Lead) -> None:
    """Send the customer their forwardable referral message and invite them to
    share a friend's number so we can track the referral."""
    ensure_referral_code(db, lead)
    intro = (
        "Love it! 🎁 Share Ridra with someone special and we'll welcome them "
        "warmly. Just forward the message below to them 👇"
    )
    await send_txt_msg_async(lead.phone, intro)
    await send_txt_msg_async(lead.phone, build_forward_message(lead))
    await send_txt_msg_async(
        lead.phone,
        "Or send me your friend's WhatsApp number and I'll note the referral. "
        "You'll get a notification the moment they join! 🔔",
    )
    lead.pending_intent = "awaiting_referral"
    db.commit()


# --- Referral processing -----------------------------------------------------

def _parent_referral_for(db, referrer: Lead) -> Referral | None:
    """If the referrer themselves joined via a referral, return that referral
    so we can link the chain (referrals from referrals)."""
    return (
        db.query(Referral)
        .filter(Referral.referred_lead_id == referrer.id, Referral.status == "accepted")
        .order_by(Referral.accepted_at.desc())
        .first()
    )


async def maybe_accept_referral(db, lead: Lead, content: str) -> bool:
    """If `content` carries a referral code from another customer, record an
    accepted referral and notify the referrer. Returns True if accepted."""
    match = REFERRAL_CODE_RE.search(content or "")
    if not match:
        return False

    code = f"{REFERRAL_PREFIX}{match.group(1).upper()}"
    referrer = db.query(Lead).filter(Lead.referral_code.ilike(code)).first()
    if not referrer or referrer.id == lead.id:
        return False

    # Don't double-credit: skip if this lead is already an accepted referral.
    already = (
        db.query(Referral)
        .filter(Referral.referred_lead_id == lead.id, Referral.status == "accepted")
        .first()
    )
    if already:
        return False

    # Reuse a matching pending referral (created when the referrer shared the
    # friend's number) if one exists, otherwise create a fresh record.
    referral = (
        db.query(Referral)
        .filter(
            Referral.referrer_id == referrer.id,
            Referral.status == "pending",
            Referral.referred_phone == lead.phone,
        )
        .first()
    )
    if not referral:
        referral = Referral(
            referrer_id=referrer.id,
            referral_code=code,
            parent_referral_id=(
                _parent_referral_for(db, referrer).id
                if _parent_referral_for(db, referrer)
                else None
            ),
        )
        db.add(referral)

    referral.referred_lead_id = lead.id
    referral.referred_phone = lead.phone
    referral.referred_name = lead.name
    referral.status = "accepted"
    referral.accepted_at = datetime.utcnow()
    db.commit()

    # Notify the referrer.
    new_name = lead.name or "Someone you referred"
    try:
        await send_txt_msg_async(
            referrer.phone,
            f"🎉 Great news! *{new_name}* just joined Ridra Jewellers using your "
            "referral. Thank you for sharing the sparkle! 💎",
        )
    except Exception as e:
        logger.error(f"Failed to notify referrer {referrer.phone}: {e}")

    logger.info(f"Referral accepted: referrer={referrer.id} -> lead={lead.id}")
    return True


async def process_referral_submission(db, lead: Lead, content: str) -> bool:
    """When a customer (with pending_intent='awaiting_referral') sends a phone
    number, record pending referral(s) so the team can manage/track them."""
    phones = _extract_phones(content)
    lead.pending_intent = None

    if not phones:
        db.commit()
        await send_txt_msg_async(
            lead.phone,
            "No worries! You can forward the message above to anyone, anytime. ✨",
        )
        return True

    ensure_referral_code(db, lead)
    parent = _parent_referral_for(db, lead)
    created = 0
    for phone in phones:
        exists = (
            db.query(Referral)
            .filter(
                Referral.referrer_id == lead.id,
                Referral.referred_phone == phone,
            )
            .first()
        )
        if exists:
            continue
        db.add(
            Referral(
                referrer_id=lead.id,
                referred_phone=phone,
                referral_code=lead.referral_code,
                status="pending",
                parent_referral_id=parent.id if parent else None,
            )
        )
        created += 1
    db.commit()

    await send_txt_msg_async(
        lead.phone,
        f"Noted! 📝 I've saved {created} referral(s). Ask your friend to send us "
        f"the message with your code *{lead.referral_code}* — you'll be notified "
        "the moment they join! 🔔",
    )
    return True


def _extract_phones(text: str) -> list[str]:
    """Extract WhatsApp-style phone numbers (10+ digits) from text."""
    if not text:
        return []
    out: list[str] = []
    for raw in re.findall(r"\+?[\d\s\-\.\(\)]{10,}", text):
        digits = re.sub(r"\D", "", raw)
        if len(digits) >= 10 and digits not in out:
            out.append(digits)
    return out


# --- AI replies --------------------------------------------------------------

async def ai_reply(db, lead: Lead, content: str) -> None:
    """Generate an AI reply (with built-in escalation) and send it."""
    from ai import chat_with_assistant

    response = chat_with_assistant(lead.id, content)
    if response:
        await send_txt_msg_async(lead.phone, response)


# --- Main router -------------------------------------------------------------

def _extract_reply(message: dict) -> str | None:
    """Unified text from a typed message, template quick-reply, or interactive tap."""
    mtype = message.get("type")
    if mtype == "text":
        return message.get("text", {}).get("body")
    if mtype == "button":
        btn = message.get("button", {}) or {}
        return btn.get("text") or btn.get("payload")
    if mtype == "interactive":
        interactive = message.get("interactive", {}) or {}
        itype = interactive.get("type")
        if itype == "button_reply":
            reply = interactive.get("button_reply", {}) or {}
            return reply.get("id") or reply.get("title")
        if itype == "list_reply":
            reply = interactive.get("list_reply", {}) or {}
            return reply.get("title") or reply.get("id")
    return None


def _map_to_action(text: str | None) -> str | None:
    """Map leftover interactive-menu taps (refer / contact) after the flow."""
    if not text:
        return None
    t = text.lower()
    if "refer" in t:
        return BTN_REFER
    if "talk" in t or "contact" in t or "support" in t:
        return BTN_CONTACT
    return None


async def handle_incoming_message(wa_id: str, name: str | None, message: dict) -> None:
    """Single entry point for every inbound message. Owns its DB session."""
    db = SessionLocal()
    try:
        lead, created = get_or_create_lead(db, wa_id, name)
        reply = _extract_reply(message)
        _flow_log(
            f"STEP handle_incoming_message() wa_id={wa_id} created={created} "
            f"type={message.get('type')} state={lead.onboarding_state} "
            f"flow={lead.flow_stage} reply={reply!r} msg={message}"
        )

        # 1) First-ever interaction — welcome template once (same idea as thread_id).
        if lead.onboarding_state == "new":
            _flow_log("ROUTE first-contact → send_welcome()")
            if reply:
                await maybe_accept_referral(db, lead, reply)
            await send_welcome(db, lead)
            return

        # 2) Pending referral submission (customer sharing a friend's number).
        if lead.pending_intent == "awaiting_referral":
            await process_referral_submission(db, lead, reply or "")
            return

        # 3) Template onboarding flow (welcome → occasion → budget → trust → category).
        if lead.flow_stage in FLOW_INTENTS:
            _flow_log(f"ROUTE in-flow stage={lead.flow_stage} → handle_flow_reply()")
            await handle_flow_reply(db, lead, reply)
            return

        content = reply or ""

        # 4) Referral acceptance — if their message carries someone's code.
        accepted = await maybe_accept_referral(db, lead, content) if content else False

        # 5) Leftover interactive-menu actions (refer / contact).
        action_id = _map_to_action(reply)
        if action_id:
            await handle_action(db, lead, action_id)
            return

        if not content:
            return

        if accepted:
            await send_txt_msg_async(
                lead.phone,
                "And welcome to the Ridra family! 💎 What can I help you "
                "discover today? ✨",
            )
            if lead.onboarding_state != "engaged":
                lead.onboarding_state = "engaged"
                db.commit()
            return

        # 6) Everything else → AI assistant.
        _flow_log(f"ROUTE AI chat content={content!r}")
        if lead.onboarding_state != "engaged":
            lead.onboarding_state = "engaged"
            db.commit()
        await ai_reply(db, lead, content)

    except Exception as e:
        logger.error(f"Error handling message from {wa_id}: {e}")
    finally:
        db.close()
