"""
Milestone 3 — message orchestration for the WhatsApp chatbot.

This module is the single entry point for every inbound WhatsApp message. It
handles three pillars of Milestone 3:

1. Onboarding   — new customers get an interactive welcome (poster + reply
                  buttons) that keeps them inside a guided process.
2. AI replies   — small/common queries are answered by the assistant; big or
                  complex queries are escalated to the team's contact email
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

from db.models import SessionLocal, Lead, Referral
from send_msg import (
    send_txt_msg_async,
    send_interactive_buttons,
    send_template_async,
    send_img_async,
)

logger = logging.getLogger(__name__)

# --- Configuration -----------------------------------------------------------
CONTACT_EMAIL = os.getenv("CONTACT_EMAIL", "support@ridra.in")
# Poster/image shown on the onboarding welcome (optional).
ONBOARDING_POSTER_URL = os.getenv("ONBOARDING_POSTER_URL", "").strip()
# Business WhatsApp number (digits only) used to build wa.me forward links.
BUSINESS_WA_NUMBER = re.sub(r"\D", "", os.getenv("BUSINESS_WA_NUMBER", ""))

# Approved WhatsApp template sent as the first-contact welcome (TemplateStorage
# id=6 -> "welcome_template"). Configurable via env.
WELCOME_TEMPLATE_NAME = os.getenv("WELCOME_TEMPLATE_NAME", "welcome_template")
WELCOME_TEMPLATE_LANG = os.getenv("WELCOME_TEMPLATE_LANG", "en_US")

# Reply-button identifiers for the onboarding menu (fallback / follow-up).
BTN_BROWSE = "onb_browse"
BTN_REFER = "onb_refer"
BTN_CONTACT = "onb_contact"

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


# --- Onboarding --------------------------------------------------------------

async def send_welcome(db, lead: Lead) -> None:
    """Send the onboarding welcome on first contact and mark the lead welcomed.

    Primary path: the approved WhatsApp template `welcome_template` (with its
    attached poster). If that fails (e.g. not approved yet), fall back to the
    interactive button menu so onboarding still works.
    """
    sent = False
    try:
        resp = await send_template_async(
            recipient_phone=lead.phone,
            template_name=WELCOME_TEMPLATE_NAME,
            language_code=WELCOME_TEMPLATE_LANG,
        )
        sent = resp.status_code == 200
        if not sent:
            logger.error(
                f"welcome_template send failed ({resp.status_code}) for "
                f"{lead.phone}: {resp.text}"
            )
    except Exception as e:
        logger.error(f"welcome_template send errored for {lead.phone}: {e}")

    if not sent:
        await _send_welcome_menu(lead)

    lead.onboarding_state = "welcomed"
    db.commit()


async def _send_welcome_menu(lead: Lead) -> None:
    """Interactive onboarding menu — fallback when the template can't be sent."""
    name = (lead.name or "there").split(" ")[0]
    body = (
        f"Welcome to *Ridra Jewellers*, {name}! ✨\n\n"
        "Every piece here tells a story 💎 What would you like to do?"
    )
    buttons = [
        {"id": BTN_BROWSE, "title": "💎 Browse Jewelry"},
        {"id": BTN_REFER, "title": "🎁 Refer a Friend"},
        {"id": BTN_CONTACT, "title": "📞 Talk to Us"},
    ]
    try:
        await send_interactive_buttons(
            recipient_phone=lead.phone,
            body_text=body,
            buttons=buttons,
            header_image_url=ONBOARDING_POSTER_URL or None,
            footer_text="Ridra Jewellers",
        )
    except Exception as e:
        logger.error(f"Interactive welcome failed for {lead.phone}: {e}")
        await send_txt_msg_async(lead.phone, f"{body}\n\nReply: Browse, Refer, or Contact.")


# --- Onboarding button actions ----------------------------------------------

async def handle_action(db, lead: Lead, action_id: str) -> None:
    """Handle a tap on one of the onboarding reply buttons."""
    if action_id == BTN_BROWSE:
        await _action_browse(db, lead)
    elif action_id == BTN_REFER:
        await _action_refer(db, lead)
    elif action_id == BTN_CONTACT:
        await _action_contact(db, lead)
    else:
        logger.info(f"Unknown action id '{action_id}' from {lead.phone}")
        await send_txt_msg_async(
            lead.phone,
            "Tell me what you're looking for and I'll help you find it! ✨",
        )

    if lead.onboarding_state != "engaged":
        lead.onboarding_state = "engaged"
        db.commit()


async def _action_browse(db, lead: Lead) -> None:
    await send_txt_msg_async(
        lead.phone,
        "Wonderful! 💎 Tell me what you're dreaming of — a gift, something for a "
        "special occasion, or just to treat yourself? I can also share today's "
        "gold rates or show you specific pieces. ✨",
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

def _extract_text(message: dict) -> str | None:
    if message.get("type") == "text":
        return message.get("text", {}).get("body")
    return None


def _map_to_action(text: str | None) -> str | None:
    """Map free text / button payload to an onboarding action id, if it clearly
    matches one. Used for template quick-reply buttons whose payload/title we
    don't control."""
    if not text:
        return None
    t = text.lower()
    if "refer" in t:
        return BTN_REFER
    if "browse" in t or "collection" in t or "jewel" in t or "shop" in t:
        return BTN_BROWSE
    if "talk" in t or "contact" in t or "support" in t or "help" in t:
        return BTN_CONTACT
    return None


def _extract_action_id(message: dict) -> str | None:
    """Pull an onboarding action id from an interactive reply (button/list) or
    from a template quick-reply button (type 'button')."""
    mtype = message.get("type")
    if mtype == "interactive":
        interactive = message.get("interactive", {})
        itype = interactive.get("type")
        if itype == "button_reply":
            return interactive.get("button_reply", {}).get("id")
        if itype == "list_reply":
            return interactive.get("list_reply", {}).get("id")
        return None
    if mtype == "button":
        # Template quick-reply button: {"button": {"payload": ..., "text": ...}}
        btn = message.get("button", {})
        return _map_to_action(btn.get("payload") or btn.get("text"))
    return None


async def handle_incoming_message(wa_id: str, name: str | None, message: dict) -> None:
    """Single entry point for every inbound message. Owns its DB session."""
    db = SessionLocal()
    try:
        lead, created = get_or_create_lead(db, wa_id, name)

        # 1) Interactive button taps — always handled directly.
        action_id = _extract_action_id(message)
        if action_id:
            await handle_action(db, lead, action_id)
            return

        content = _extract_text(message)
        if not content:
            # Unsupported message type — gently guide onboarding if needed.
            if lead.onboarding_state == "new":
                await send_welcome(db, lead)
            return

        # 2) Referral acceptance — if their message carries someone's code.
        accepted = await maybe_accept_referral(db, lead, content)

        # 3) Pending referral submission (customer sharing a friend's number).
        if lead.pending_intent == "awaiting_referral":
            await process_referral_submission(db, lead, content)
            return

        # 4) Onboarding — first-ever message gets the interactive welcome.
        if lead.onboarding_state == "new":
            await send_welcome(db, lead)
            return

        if accepted:
            # Referral just accepted; welcome them into the conversation.
            await send_txt_msg_async(
                lead.phone,
                "And welcome to the Ridra family! 💎 What can I help you "
                "discover today? ✨",
            )
            if lead.onboarding_state != "engaged":
                lead.onboarding_state = "engaged"
                db.commit()
            return

        # 5) Everything else → AI assistant (resolves small queries, escalates big ones).
        if lead.onboarding_state != "engaged":
            lead.onboarding_state = "engaged"
            db.commit()
        await ai_reply(db, lead, content)

    except Exception as e:
        logger.error(f"Error handling message from {wa_id}: {e}")
    finally:
        db.close()
