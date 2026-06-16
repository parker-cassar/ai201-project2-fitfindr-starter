# FitFindr — planning.md

> Complete this document before writing any implementation code.
> Your spec and agent diagram are what you'll use to direct AI tools (Claude, Copilot, etc.) to generate your implementation — the more specific they are, the more useful the generated code will be.
> Your planning.md will be reviewed as part of your submission.
> Update it before starting any stretch features.

---

## A Complete Interaction (overview)

FitFindr is a thrift-shopping assistant that takes a natural-language query (what the user wants, optional size and price), searches mock secondhand listings, picks the best match, suggests how to style it with the user's wardrobe, and generates a shareable fit-card caption. **search_listings** runs first; if it returns nothing, the agent stops and tells the user what to adjust — it never calls **suggest_outfit** with empty input. When search succeeds, the top listing flows through session state into **suggest_outfit** and then **create_fit_card** without the user re-entering the item.

---

## Tools

List every tool your agent will use. For each tool, fill in all four fields.
You must have at least 3 tools. The three required tools are listed — add any additional tools below them.

### Tool 1: search_listings

**What it does:**
Searches the mock listings dataset (`data/listings.json`) for items whose title, description, style tags, and category overlap with the user's keyword description, optionally filtered by size and maximum price. Returns matching listings sorted by relevance score (best match first).

**Input parameters:**
- `description` (str): Keywords describing what the user wants (e.g., `"vintage graphic tee"`). Split into lowercase tokens for scoring.
- `size` (str | None): Size string to filter by, or `None` to skip. Matching is case-insensitive; the listing's `size` field must contain the requested size as a substring (e.g., `"M"` matches `"S/M"`).
- `max_price` (float | None): Maximum price inclusive, or `None` to skip price filtering.

**What it returns:**
A `list[dict]` of matching listing dicts, sorted by relevance (highest score first). Each dict contains: `id`, `title`, `description`, `category`, `style_tags` (list[str]), `size`, `condition`, `price` (float), `colors` (list[str]), `brand` (str | None), `platform` (str). Returns `[]` if nothing matches — never raises.

**What happens if it fails or returns nothing:**
The agent sets `session["error"]` to a specific message listing what was searched (description, size, max price) and suggests loosening constraints (remove size filter, raise budget, try broader keywords). It returns the session early without calling `suggest_outfit` or `create_fit_card`.

---

### Tool 2: suggest_outfit

**What it does:**
Given a specific listing the user is considering and their current wardrobe, calls Groq (`llama-3.3-70b-versatile`) to suggest 1–2 complete outfit combinations. If the wardrobe is empty, returns general styling advice for the new item instead of referencing named wardrobe pieces.

**Input parameters:**
- `new_item` (dict): A listing dict from `search_listings` (must include `title`, `description`, `category`, `style_tags`, `colors`, `price`, `platform`).
- `wardrobe` (dict): Wardrobe dict with an `items` key — list of wardrobe item dicts (`id`, `name`, `category`, `colors`, `style_tags`, optional `notes`). May be empty.

**What it returns:**
A non-empty `str` with outfit suggestions (2–4 paragraphs). Names specific wardrobe pieces when available; otherwise gives general pairing advice (bottoms, shoes, layering) for the item's vibe.

**What happens if it fails or returns nothing:**
The tool itself always returns a useful string (empty wardrobe is handled inside the tool). If the LLM call fails (API error), return a fallback string with basic styling tips derived from the item's `style_tags` and `category` — never raise or return `""`. The agent stores the result in `session["outfit_suggestion"]` and proceeds to `create_fit_card`.

---

### Tool 3: create_fit_card

**What it does:**
Calls Groq (`llama-3.3-70b-versatile`, temperature 0.9) to generate a short, casual Instagram/TikTok-style caption for the outfit. Mentions item name, price, and platform naturally once each.

**Input parameters:**
- `outfit` (str): The outfit suggestion string from `suggest_outfit()`.
- `new_item` (dict): The listing dict for the thrifted item.

**What it returns:**
A `str` — either a 2–4 sentence shareable caption, or a descriptive error message if `outfit` is empty/whitespace (e.g., `"Cannot create a fit card: no outfit suggestion was provided."`). Never raises.

**What happens if it fails or returns nothing:**
If `outfit` is empty, return the error message string and store it in `session["fit_card"]`. The agent still completes (no early return) but the fit card panel shows the error. If the LLM fails, return a simple template-based caption as fallback.

---

### Additional Tools (if any)

None for the required submission.

---

## Planning Loop

**How does your agent decide which tool to call next?**

The planning loop is a conditional sequence — not a fixed pipeline that always runs all three tools.

1. **Initialize** `session = _new_session(query, wardrobe)`.
2. **Parse query** with regex: extract `max_price` (patterns like `under $30`, `under 30`), `size` (pattern `size M`, `size 8`), and `description` (remaining text after stripping price/size phrases). Store in `session["parsed"]`.
3. **Call `search_listings`** with parsed params. Store in `session["search_results"]`.
4. **Branch on search results:**
   - If `search_results` is empty → set `session["error"]` to actionable message → **return session** (stop; do not call other tools).
   - If non-empty → set `session["selected_item"] = search_results[0]` → continue.
5. **Call `suggest_outfit(selected_item, wardrobe)`**. Store in `session["outfit_suggestion"]`.
6. **Call `create_fit_card(outfit_suggestion, selected_item)`**. Store in `session["fit_card"]`.
7. **Return session**.

The agent is done when either an error short-circuits at step 4, or all three tools have run and `fit_card` is populated.

---

## State Management

**How does information from one tool get passed to the next?**

A single `session` dict is the source of truth for one interaction:

| Field | Set when | Used by |
|-------|----------|---------|
| `query` | init | reference only |
| `parsed` | after query parse | `search_listings` inputs |
| `search_results` | after search | selecting `selected_item` |
| `selected_item` | top search result | `suggest_outfit`, `create_fit_card` |
| `wardrobe` | init (from UI) | `suggest_outfit` |
| `outfit_suggestion` | after suggest | `create_fit_card` |
| `fit_card` | after fit card | returned to UI |
| `error` | on early exit | returned to UI |

The same `selected_item` dict object flows from search → suggest → fit card without re-parsing or re-entering. `outfit_suggestion` string flows directly into `create_fit_card`.

---

## Error Handling

For each tool, describe the specific failure mode you're handling and what the agent does in response.

| Tool | Failure mode | Agent response |
|------|-------------|----------------|
| search_listings | No results match the query | Sets `session["error"]` to: `"No listings found for '{description}' (size: {size or 'any'}, max price: ${max_price or 'any'}). Try broadening your search — remove the size filter, raise your budget, or use different keywords like 'graphic tee' instead of a specific band name."` Returns session with `fit_card=None`, `outfit_suggestion=None`. |
| suggest_outfit | Wardrobe is empty | Tool returns general styling advice (not an error). Agent proceeds normally; UI shows general pairing tips in the outfit panel. |
| create_fit_card | Outfit input is missing or incomplete | Tool returns `"Cannot create a fit card: no outfit suggestion was provided."` Agent stores this in `session["fit_card"]`; user sees the message in the fit card panel. |

---

## Architecture

```mermaid
flowchart TD
    U[User query + wardrobe choice] --> PL[Planning Loop]
    PL --> P[Parse query → session.parsed]
    P --> SL[search_listings]
    SL -->|results = []| ERR[Set session.error → return early]
    SL -->|results found| SI[session.selected_item = results0]
    SI --> SO[suggest_outfit]
    SO --> OS[session.outfit_suggestion]
    OS --> FC[create_fit_card]
    FC --> FK[session.fit_card]
    FK --> OUT[Return session → Gradio UI]
    ERR --> OUT

    subgraph Session State
        S1[parsed]
        S2[search_results]
        S3[selected_item]
        S4[outfit_suggestion]
        S5[fit_card]
        S6[error]
    end

    PL -.-> Session State
    SL -.-> S2
    SI -.-> S3
    SO -.-> S4
    FC -.-> S5
    ERR -.-> S6
```

ASCII equivalent:

```
User query + wardrobe
    │
    ▼
Planning Loop ─────────────────────────────────────────────┐
    │                                                      │
    ├─► Parse query → session["parsed"]                    │
    │                                                      │
    ├─► search_listings(description, size, max_price)    │
    │       │ results=[]                                   │
    │       ├──► [ERROR] set session["error"] → return ────┤
    │       │                                              │
    │       │ results=[item, ...]                          │
    │       ▼                                              │
    │   session["selected_item"] = results[0]              │
    │       │                                              │
    ├─► suggest_outfit(selected_item, wardrobe)            │
    │       │                                              │
    │   session["outfit_suggestion"] = "..."                 │
    │       │                                              │
    └─► create_fit_card(outfit_suggestion, selected_item)  │
            │                                              │
        session["fit_card"] = "..."                        │
            │                                              │
            ▼                                              │
        Return session ────────────────────────────────────┘
```

---

## AI Tool Plan

**Milestone 3 — Individual tool implementations:**

- **Tool:** Cursor AI (Claude)
- **Input:** Tool 1 spec block (inputs, return value, failure mode) + `load_listings()` docstring from `utils/data_loader.py`
- **Expected output:** `search_listings()` implementation with keyword scoring, size/price filters, empty-list return
- **Verification:** Run `pytest tests/test_tools.py::test_search_*` and manual call with `"vintage graphic tee"`, `size=None`, `max_price=50` — confirm non-empty results; call with `"designer ballgown"`, `size="XXS"`, `max_price=5` — confirm `[]`

- **Tool:** Cursor AI
- **Input:** Tool 2 spec + wardrobe schema example + Groq client pattern from starter
- **Expected output:** `suggest_outfit()` with empty-wardrobe branch and LLM prompt
- **Verification:** Call with `get_empty_wardrobe()` — non-empty string returned; call with `get_example_wardrobe()` — mentions wardrobe item names

- **Tool:** Cursor AI
- **Input:** Tool 3 spec + temperature requirement
- **Expected output:** `create_fit_card()` with empty-outfit guard and LLM call at temp 0.9
- **Verification:** Call with `create_fit_card('', item)` — error string; call twice with same input — outputs differ

**Milestone 4 — Planning loop and state management:**

- **Tool:** Cursor AI
- **Input:** Planning Loop section + State Management section + Architecture diagram
- **Expected output:** `run_agent()` in `agent.py` with conditional branch on empty search results
- **Verification:** Run `python agent.py` — happy path prints title, outfit, fit card; no-results path prints error and `fit_card` is None. Print `session["selected_item"]` id matches what went into `suggest_outfit`.

---

## A Complete Interaction (Step by Step)

Write out what a full user interaction looks like from start to finish — tool call by tool call. Use a specific example query.

**Example user query:** "I'm looking for a vintage graphic tee under $30. I mostly wear baggy jeans and chunky sneakers. What's out there and how would I style it?"

**Step 1:**
Agent parses query → `parsed = {description: "vintage graphic tee", size: None, max_price: 30.0}` (size not specified; wardrobe context in query is ignored for search).
Calls `search_listings("vintage graphic tee", size=None, max_price=30.0)`.
Returns ~3 matches; top result: **Vintage Band Tee — Faded Grey** ($19, depop, size L).
Stores in `session["search_results"]` and `session["selected_item"]`.

**Step 2:**
Calls `suggest_outfit(selected_item, example_wardrobe)`.
LLM pairs the band tee with **Baggy straight-leg jeans** and **Chunky white sneakers** from the wardrobe, suggests rolling sleeves and a half-tuck.
Stores in `session["outfit_suggestion"]`.

**Step 3:**
Calls `create_fit_card(outfit_suggestion, selected_item)`.
LLM generates a casual caption mentioning the faded grey tee, $19, depop, and the wide-leg + chunky sneaker vibe.
Stores in `session["fit_card"]`.

**Final output to user:**
- **Listing panel:** Vintage Band Tee — Faded Grey, $19, depop, size L, good condition
- **Outfit panel:** Styling suggestion referencing baggy jeans and chunky sneakers
- **Fit card panel:** Short Instagram-style caption ready to copy
