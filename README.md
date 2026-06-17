# FitFindr

FitFindr is an AI-powered thrift-shopping assistant. Describe what you're looking for, and the agent searches mock secondhand listings, suggests outfits using your wardrobe, and generates a shareable fit-card caption.

## Setup

```bash
python -m venv .venv
source .venv/bin/activate          # Mac/Linux
pip install -r requirements.txt
```

Create a `.env` file in the project root:

```
GROQ_API_KEY=your_key_here
```

Get a free key at [console.groq.com](https://console.groq.com).

## Run

```bash
python app.py
```

Open the localhost URL shown in your terminal (usually http://localhost:7860).

Run tests:

```bash
pytest tests/
```

Run the agent from the CLI:

```bash
python agent.py
```

---

## Tool Inventory

| Tool | Inputs | Output | Purpose |
|------|--------|--------|---------|
| `search_listings(description, size, max_price)` | `description` (str): search keywords; `size` (str \| None): size filter; `max_price` (float \| None): max price inclusive | `list[dict]` — matching listings sorted by relevance; `[]` if none | Find secondhand items in the mock dataset |
| `suggest_outfit(new_item, wardrobe)` | `new_item` (dict): listing dict; `wardrobe` (dict): `{"items": [...]}` | `str` — outfit suggestions (never empty) | Style the found item with the user's wardrobe |
| `create_fit_card(outfit, new_item)` | `outfit` (str): suggestion from suggest_outfit; `new_item` (dict): listing dict | `str` — Instagram-style caption or error message | Generate a shareable OOTD caption |

Each listing dict contains: `id`, `title`, `description`, `category`, `style_tags`, `size`, `condition`, `price`, `colors`, `brand`, `platform`.

---

## Planning Loop

The agent uses a **conditional** planning loop — it does not always call all three tools.

1. **Parse** the user query with regex to extract `description`, `size`, and `max_price`. Store in `session["parsed"]`.
2. **Call `search_listings`** with parsed parameters. Store results in `session["search_results"]`.
3. **Branch on results:**
   - If empty → set `session["error"]` with actionable advice → **return early** (no suggest or fit card).
   - If found → set `session["selected_item"] = results[0]` → continue.
4. **Call `suggest_outfit(selected_item, wardrobe)`** → store in `session["outfit_suggestion"]`.
5. **Call `create_fit_card(outfit_suggestion, selected_item)`** → store in `session["fit_card"]`.
6. **Return** the completed session.

The loop responds to what each tool returns: an empty search stops the pipeline; a successful search drives the next two steps automatically.

---

## State Management

All state lives in a single `session` dict per interaction:

- `parsed` — extracted search parameters (set before search)
- `search_results` — full list from `search_listings`
- `selected_item` — top result, passed unchanged into `suggest_outfit` and `create_fit_card`
- `wardrobe` — user's wardrobe (from UI choice)
- `outfit_suggestion` — string from suggest, passed into create_fit_card
- `fit_card` — final caption
- `error` — set only on early termination (empty search)

The user never re-enters the found item — `selected_item` flows through the session automatically.

---

## Error Handling

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| `search_listings` | No matches | Sets `session["error"]` with the searched description, size, and price plus suggestions to broaden the search. Returns early; outfit and fit card panels stay empty. |
| `suggest_outfit` | Empty wardrobe | Tool returns general styling advice (not an error). Agent continues to fit card. |
| `create_fit_card` | Empty outfit string | Tool returns `"Cannot create a fit card: no outfit suggestion was provided."` — shown in the fit card panel. |

**Concrete example (tested):** Query `"designer ballgown size XXS under $5"` returns:

> No listings found for 'designer ballgown' (size: XXS, max price: $5). Try broadening your search — remove the size filter, raise your budget, or use different keywords like 'graphic tee' instead of a specific band name.

The agent does not call `suggest_outfit` or `create_fit_card` for this query.

**Empty wardrobe example (tested):**

```bash
python -c "
from tools import search_listings, suggest_outfit
from utils.data_loader import get_empty_wardrobe
results = search_listings('vintage graphic tee', size=None, max_price=50)
print(suggest_outfit(results[0], get_empty_wardrobe()))
"
```

Returns general pairing advice without crashing.

---

## Interaction Walkthrough

**User query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1 — Tool called:**
- Tool: `search_listings`
- Input: `description="vintage graphic tee"`, `size=None`, `max_price=30.0`
- Why: Parse query first; search is always the entry point
- Output: List of matches; top result stored as `selected_item` (e.g., Vintage Band Tee — Faded Grey, $19, depop)

**Step 2 — Tool called:**
- Tool: `suggest_outfit`
- Input: `new_item=selected_item`, `wardrobe=example_wardrobe`
- Why: Search succeeded; style the found item with owned pieces
- Output: Outfit suggestion referencing baggy jeans and chunky sneakers from the wardrobe

**Step 3 — Tool called:**
- Tool: `create_fit_card`
- Input: `outfit=outfit_suggestion`, `new_item=selected_item`
- Why: Outfit is ready; generate shareable caption
- Output: Casual Instagram-style caption mentioning item, price, and platform

**Final output to user:** Three panels — listing details, outfit idea, fit card caption.

---

## Spec Reflection

**One way planning.md helped during implementation:**

Writing the conditional branch for empty search results before coding made the agent structure obvious — the diagram and planning loop section specified exactly when to return early, which prevented accidentally calling `suggest_outfit` with no item. The tool return-value specs also made pytest assertions straightforward.

**One divergence from the spec, and why:**

The example interaction mentions a "Faded Band Tee — $22" but the dataset's closest match is "Vintage Band Tee — Faded Grey" at $19. The search logic and flow are identical; only the specific listing title differs because the mock data doesn't include that exact item.

---

## AI Usage

**Instance 1 — Tool implementations:**

Gave Cursor the Tool 1–3 spec blocks from `planning.md` (inputs, return types, failure modes) plus the `load_listings()` docstring. It generated `search_listings` with keyword scoring and `suggest_outfit` / `create_fit_card` with Groq prompts. I revised scoring to use substring matching on combined title/description/tags (not just title), and added `_fallback_outfit_suggestion` / `_fallback_fit_card` when the API is unavailable so tests pass without a key.

**Instance 2 — Planning loop:**

Shared the Architecture diagram and Planning Loop + State Management sections from `planning.md`. Cursor generated `run_agent()` and `_parse_query()`. I tightened the size regex to handle trailing punctuation and added `_no_results_message()` so the error text matched the spec table exactly.

---

## Project Structure

```
├── agent.py              # Planning loop and session state
├── app.py                # Gradio UI
├── tools.py              # search_listings, suggest_outfit, create_fit_card
├── planning.md           # Design spec (written before implementation)
├── data/
│   ├── listings.json
│   └── wardrobe_schema.json
├── utils/
│   └── data_loader.py
└── tests/
    └── test_tools.py
```
