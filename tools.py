"""
tools.py

The three required FitFindr tools. Each tool is a standalone function that
can be called and tested independently before being wired into the agent loop.

Complete and test each tool before moving to agent.py.

Tools:
    search_listings(description, size, max_price)  → list[dict]
    suggest_outfit(new_item, wardrobe)              → str
    create_fit_card(outfit, new_item)               → str
"""

import os
import re

from dotenv import load_dotenv
from groq import Groq

from utils.data_loader import load_listings

load_dotenv()

LLM_MODEL = "llama-3.3-70b-versatile"


# ── Groq client ───────────────────────────────────────────────────────────────

def _get_groq_client():
    """Initialize and return a Groq client using GROQ_API_KEY from .env."""
    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise ValueError(
            "GROQ_API_KEY not set. Add it to a .env file in the project root."
        )
    return Groq(api_key=api_key)


def _call_llm(prompt: str, temperature: float = 0.7) -> str:
    """Call Groq LLM and return the response text, with a simple fallback."""
    try:
        client = _get_groq_client()
        response = client.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "user", "content": prompt}],
            temperature=temperature,
            max_tokens=512,
        )
        return response.choices[0].message.content.strip()
    except Exception as exc:
        return f"[LLM unavailable: {exc}]"


def _tokenize(text: str) -> list[str]:
    """Split text into lowercase keyword tokens."""
    return [t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 1]


def _listing_search_text(listing: dict) -> str:
    """Combine searchable fields from a listing into one lowercase string."""
    tags = " ".join(listing.get("style_tags", []))
    colors = " ".join(listing.get("colors", []))
    brand = listing.get("brand") or ""
    return " ".join(
        [
            listing.get("title", ""),
            listing.get("description", ""),
            listing.get("category", ""),
            tags,
            colors,
            brand,
        ]
    ).lower()


def _score_listing(listing: dict, keywords: list[str]) -> int:
    """Score a listing by keyword overlap across searchable fields."""
    if not keywords:
        return 0
    text = _listing_search_text(listing)
    return sum(1 for kw in keywords if kw in text)


def _size_matches(listing_size: str, requested_size: str) -> bool:
    """Case-insensitive substring match (e.g. 'M' matches 'S/M')."""
    return requested_size.lower() in listing_size.lower()


# ── Tool 1: search_listings ───────────────────────────────────────────────────

def search_listings(
    description: str,
    size: str | None = None,
    max_price: float | None = None,
) -> list[dict]:
    """
    Search the mock listings dataset for items matching the description,
    optional size, and optional price ceiling.

    Args:
        description: Keywords describing what the user is looking for
                     (e.g., "vintage graphic tee").
        size:        Size string to filter by, or None to skip size filtering.
                     Matching is case-insensitive (e.g., "M" matches "S/M").
        max_price:   Maximum price (inclusive), or None to skip price filtering.

    Returns:
        A list of matching listing dicts, sorted by relevance (best match first).
        Returns an empty list if nothing matches — does NOT raise an exception.

    Each listing dict has the following fields:
        id, title, description, category, style_tags (list), size,
        condition, price (float), colors (list), brand, platform
    """
    listings = load_listings()
    keywords = _tokenize(description)

    scored: list[tuple[int, dict]] = []
    for listing in listings:
        if max_price is not None and listing["price"] > max_price:
            continue
        if size is not None and not _size_matches(listing["size"], size):
            continue

        score = _score_listing(listing, keywords)
        if score > 0:
            scored.append((score, listing))

    scored.sort(key=lambda pair: (-pair[0], pair[1]["price"]))
    return [listing for _, listing in scored]


# ── Tool 2: suggest_outfit ────────────────────────────────────────────────────

def _format_wardrobe_for_prompt(wardrobe: dict) -> str:
    """Format wardrobe items into a readable bullet list for the LLM."""
    lines = []
    for item in wardrobe.get("items", []):
        tags = ", ".join(item.get("style_tags", []))
        colors = ", ".join(item.get("colors", []))
        notes = item.get("notes") or ""
        line = f"- {item['name']} ({item['category']}, {colors}; tags: {tags})"
        if notes:
            line += f" — {notes}"
        lines.append(line)
    return "\n".join(lines)


def _fallback_outfit_suggestion(new_item: dict) -> str:
    """Basic styling advice when the LLM is unavailable."""
    tags = ", ".join(new_item.get("style_tags", []))
    category = new_item.get("category", "piece")
    return (
        f"For this {new_item['title']} ({tags}), try pairing it with "
        f"complementary {category} basics — neutral bottoms if it's a top, "
        f"or a simple tee if it's a bottom. Add shoes that match the "
        f"{tags.split(',')[0] if tags else 'casual'} vibe."
    )


def suggest_outfit(new_item: dict, wardrobe: dict) -> str:
    """
    Given a thrifted item and the user's wardrobe, suggest 1–2 complete outfits.

    Args:
        new_item: A listing dict (the item the user is considering buying).
        wardrobe: A wardrobe dict with an 'items' key containing a list of
                  wardrobe item dicts. May be empty — handle this gracefully.

    Returns:
        A non-empty string with outfit suggestions.
        If the wardrobe is empty, offer general styling advice for the item
        rather than raising an exception or returning an empty string.
    """
    item_title = new_item.get("title", "this item")
    item_desc = new_item.get("description", "")
    item_tags = ", ".join(new_item.get("style_tags", []))
    item_colors = ", ".join(new_item.get("colors", []))
    wardrobe_items = wardrobe.get("items", [])

    if not wardrobe_items:
        prompt = f"""You are a personal stylist. A user found this secondhand item and has no wardrobe saved yet.

Item: {item_title}
Description: {item_desc}
Style tags: {item_tags}
Colors: {item_colors}

Suggest 1–2 complete outfit ideas using general item types (e.g., "wide-leg jeans", "chunky sneakers") — do not reference specific owned pieces. Include styling tips (tucking, layering, accessories). Keep it practical and friendly."""
    else:
        wardrobe_text = _format_wardrobe_for_prompt(wardrobe)
        prompt = f"""You are a personal stylist. A user found this secondhand item and wants outfit ideas using pieces they already own.

New item: {item_title}
Description: {item_desc}
Style tags: {item_tags}
Colors: {item_colors}

Their wardrobe:
{wardrobe_text}

Suggest 1–2 complete outfits that incorporate the new item AND name specific pieces from their wardrobe. Include practical styling tips. Keep it friendly and specific."""

    result = _call_llm(prompt, temperature=0.7)
    if result.startswith("[LLM unavailable"):
        return _fallback_outfit_suggestion(new_item)
    return result if result else _fallback_outfit_suggestion(new_item)


# ── Tool 3: create_fit_card ───────────────────────────────────────────────────

def _fallback_fit_card(outfit: str, new_item: dict) -> str:
    """Simple template caption when the LLM is unavailable."""
    platform = new_item.get("platform", "depop")
    price = new_item.get("price", 0)
    title = new_item.get("title", "this find")
    return (
        f"scored this {title.lower()} on {platform} for ${price:.0f} and "
        f"it's giving exactly the vibe i wanted. full fit breakdown in my stories ✨"
    )


def create_fit_card(outfit: str, new_item: dict) -> str:
    """
    Generate a short, shareable outfit caption for the thrifted find.

    Args:
        outfit:   The outfit suggestion string from suggest_outfit().
        new_item: The listing dict for the thrifted item.

    Returns:
        A 2–4 sentence string usable as an Instagram/TikTok caption.
        If outfit is empty or missing, return a descriptive error message
        string — do NOT raise an exception.
    """
    if not outfit or not outfit.strip():
        return "Cannot create a fit card: no outfit suggestion was provided."

    title = new_item.get("title", "item")
    price = new_item.get("price", 0)
    platform = new_item.get("platform", "depop")
    tags = ", ".join(new_item.get("style_tags", []))

    prompt = f"""Write a short Instagram/TikTok outfit caption (2–4 sentences) for this thrift find.

Item: {title} — ${price:.0f} on {platform}
Style: {tags}
Outfit idea: {outfit}

Rules:
- Sound casual and authentic, like a real OOTD post — NOT a product description
- Mention the item name, price, and platform naturally (once each)
- Capture the outfit vibe in specific terms
- Use lowercase, emojis sparingly, conversational tone
- Make it feel unique to this specific outfit"""

    result = _call_llm(prompt, temperature=0.9)
    if result.startswith("[LLM unavailable"):
        return _fallback_fit_card(outfit, new_item)
    return result if result else _fallback_fit_card(outfit, new_item)
