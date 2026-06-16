"""
FuelIQ — AI-Powered Nutrition Tracking for Young Athletes
==========================================================
Stack: Python / Flask / PostgreSQL / USDA FoodData Central API / Anthropic Claude API
Team:  5 members (see README for ownership breakdown)

Routes
------
GET  /                  → Landing / login redirect
GET  /register          → Registration page
POST /register          → Create account
GET  /login             → Login page
POST /login             → Authenticate
GET  /logout            → Log out
GET  /dashboard         → Athlete dashboard (requires login)
GET  /profile           → Athlete profile setup
POST /profile           → Save profile
GET  /food/search       → USDA food search (JSON)
POST /meal/log          → Log a meal entry
GET  /meal/feedback     → AI meal-level feedback (JSON)
GET  /summary/daily     → AI daily summary (JSON)
GET  /analytics         → Analytics dashboard
"""

import os
import json
import requests
from datetime import date, datetime
from functools import wraps

import anthropic
import psycopg2
import psycopg2.extras
from flask import (Flask, render_template, request, redirect,
                   url_for, session, jsonify, g)
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = os.environ.get("FLASK_SECRET_KEY", "dev-secret-change-me")

# ---------------------------------------------------------------------------
# Database
# ---------------------------------------------------------------------------

def get_db():
    """Return a database connection, creating one per request if needed."""
    if "db" not in g:
        g.db = psycopg2.connect(
            os.environ["DATABASE_URL"],
            cursor_factory=psycopg2.extras.RealDictCursor
        )
    return g.db

@app.teardown_appcontext
def close_db(error):
    db = g.pop("db", None)
    if db is not None:
        db.close()

def init_db():
    """Create all tables if they don't exist. Called on app startup."""
    conn = get_db()
    cur  = conn.cursor()

    # Users — parents / family accounts
    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id            SERIAL PRIMARY KEY,
            email         TEXT NOT NULL UNIQUE,
            password_hash TEXT NOT NULL,
            family_name   TEXT,
            created_at    TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # Athlete profiles — one user can have multiple athletes
    cur.execute("""
        CREATE TABLE IF NOT EXISTS athletes (
            id                SERIAL PRIMARY KEY,
            user_id           INTEGER NOT NULL REFERENCES users(id),
            name              TEXT NOT NULL,
            age               INTEGER NOT NULL,
            sport             TEXT,
            training_schedule TEXT,
            dietary_notes     TEXT,
            created_at        TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # Meal logs — each entry is one food item in a meal
    cur.execute("""
        CREATE TABLE IF NOT EXISTS meal_logs (
            id              SERIAL PRIMARY KEY,
            athlete_id      INTEGER NOT NULL REFERENCES athletes(id),
            food_name       TEXT NOT NULL,
            usda_fdc_id     TEXT,
            portion_size    NUMERIC,
            portion_unit    TEXT,
            meal_time       TEXT,
            training_context TEXT,
            calories        NUMERIC,
            protein_g       NUMERIC,
            carbs_g         NUMERIC,
            fat_g           NUMERIC,
            fiber_g         NUMERIC,
            iron_mg         NUMERIC,
            calcium_mg      NUMERIC,
            logged_date     DATE DEFAULT CURRENT_DATE,
            logged_at       TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    # AI feedback — stores meal-level and daily summary responses
    cur.execute("""
        CREATE TABLE IF NOT EXISTS ai_feedback (
            id            SERIAL PRIMARY KEY,
            athlete_id    INTEGER NOT NULL REFERENCES athletes(id),
            feedback_type TEXT NOT NULL CHECK (feedback_type IN ('meal', 'daily')),
            feedback_text TEXT NOT NULL,
            logged_date   DATE DEFAULT CURRENT_DATE,
            created_at    TIMESTAMPTZ DEFAULT NOW()
        )
    """)

    conn.commit()
    cur.close()


# ---------------------------------------------------------------------------
# Auth helpers
# ---------------------------------------------------------------------------

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def current_user_id():
    return session.get("user_id")


# ---------------------------------------------------------------------------
# USDA FoodData Central API
# ---------------------------------------------------------------------------

USDA_BASE = "https://api.nal.usda.gov/fdc/v1"
USDA_KEY  = os.environ.get("USDA_API_KEY", "DEMO_KEY")

def search_usda(query, page_size=10):
    """Search USDA FoodData Central for foods matching query."""
    url    = f"{USDA_BASE}/foods/search"
    params = {
        "query":    query,
        "pageSize": page_size,
        "api_key":  USDA_KEY,
    }
    resp = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json().get("foods", [])

def get_usda_nutrients(fdc_id):
    """Fetch full nutrient data for a specific food by FDC ID."""
    url    = f"{USDA_BASE}/food/{fdc_id}"
    params = {"api_key": USDA_KEY}
    resp   = requests.get(url, params=params, timeout=10)
    resp.raise_for_status()
    return resp.json()

def extract_key_nutrients(food_data):
    """Pull the nutrients we care about from a USDA food response."""
    nutrient_map = {
        1008: "calories",
        1003: "protein_g",
        1005: "carbs_g",
        1004: "fat_g",
        1079: "fiber_g",
        1089: "iron_mg",
        1087: "calcium_mg",
    }
    result = {v: 0 for v in nutrient_map.values()}
    for n in food_data.get("foodNutrients", []):
        nid = n.get("nutrient", {}).get("id") or n.get("nutrientId")
        if nid in nutrient_map:
            result[nutrient_map[nid]] = round(n.get("amount", 0), 2)
    return result


# ---------------------------------------------------------------------------
# Claude API — Meal Feedback
# ---------------------------------------------------------------------------

claude = anthropic.Anthropic(api_key=os.environ.get("ANTHROPIC_API_KEY"))

MEAL_FEEDBACK_SYSTEM = """You are FuelIQ, an AI nutrition assistant for parents of young athletes.
Your job is to evaluate whether a logged meal supports a child's athletic training and recovery.

You are NOT a weight loss tool. Never reference weight, body fat, BMI, or caloric restriction.
Frame all feedback around performance, energy, and recovery.

Guidelines by age group:
- Ages 6–9 (FUNdamentals): Focus on enjoyment, variety, hydration, and consistent fueling.
- Ages 10–12 (Learning to Train): Introduce pre/post workout timing, adequate protein for growth.
- Ages 13–15 (Training to Train): Highest energy demands, iron awareness for girls, avoid under-fueling.
- Ages 15–18 (Training to Compete): Sport-specific macro timing, recovery nutrition windows.

Always write in warm, plain language appropriate for parents. Be encouraging, never alarming.
Keep responses to 3–5 sentences."""

def get_meal_feedback(athlete, meal_items, training_context):
    """Call Claude API to evaluate a meal against training context."""
    meal_summary = "\n".join([
        f"- {item['food_name']}: {item.get('calories', '?')} cal, "
        f"{item.get('protein_g', '?')}g protein, {item.get('carbs_g', '?')}g carbs"
        for item in meal_items
    ])

    prompt = f"""Athlete: {athlete['name']}, Age {athlete['age']}, Sport: {athlete.get('sport', 'general')}
Training today: {training_context}

Meal logged:
{meal_summary}

Does this meal support their training and recovery? Give brief, parent-friendly feedback."""

    message = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=300,
        system=MEAL_FEEDBACK_SYSTEM,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


# ---------------------------------------------------------------------------
# Claude API — Daily Summary
# ---------------------------------------------------------------------------

DAILY_SUMMARY_SYSTEM = """You are FuelIQ, an AI nutrition assistant for parents of young athletes.
Generate a concise end-of-day fueling summary.

Answer one core question for the parent: Did my child eat enough of the right things today?

Use this assessment scale:
- Well Fueled: Met energy and key nutrient needs for their training load
- Adequately Fueled: Close to needs, minor gaps
- Under-Fueled: Significant gaps that could affect recovery or next-day performance

Never mention weight, body composition, or caloric restriction.
End with one specific, actionable recommendation for tomorrow.
Keep response to 4–6 sentences."""

def get_daily_summary(athlete, daily_totals, training_context):
    """Call Claude API to generate end-of-day nutrition summary."""
    prompt = f"""Athlete: {athlete['name']}, Age {athlete['age']}, Sport: {athlete.get('sport', 'general')}
Training today: {training_context}

Today's nutrition totals:
- Calories: {daily_totals.get('calories', 0)} kcal
- Protein: {daily_totals.get('protein_g', 0)}g
- Carbohydrates: {daily_totals.get('carbs_g', 0)}g
- Fat: {daily_totals.get('fat_g', 0)}g
- Iron: {daily_totals.get('iron_mg', 0)}mg
- Calcium: {daily_totals.get('calcium_mg', 0)}mg

Generate a daily fueling summary for the parent."""

    message = claude.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=400,
        system=DAILY_SUMMARY_SYSTEM,
        messages=[{"role": "user", "content": prompt}]
    )
    return message.content[0].text


# ---------------------------------------------------------------------------
# Routes — Auth
# ---------------------------------------------------------------------------

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/register", methods=["GET", "POST"])
def register():
    # TODO: Member 1 — implement registration form and password hashing
    return "Register page — coming soon"

@app.route("/login", methods=["GET", "POST"])
def login():
    # TODO: Member 1 — implement login form and session management
    return "Login page — coming soon"

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------------------------
# Routes — Athlete Profile
# ---------------------------------------------------------------------------

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    # TODO: Member 1 — athlete profile setup (name, age, sport, training schedule, dietary notes)
    return "Profile page — coming soon"


# ---------------------------------------------------------------------------
# Routes — Dashboard
# ---------------------------------------------------------------------------

@app.route("/dashboard")
@login_required
def dashboard():
    # TODO: Member 4 — main dashboard showing today's meals, AI feedback, and quick log button
    return "Dashboard — coming soon"


# ---------------------------------------------------------------------------
# Routes — Food Search (USDA)
# ---------------------------------------------------------------------------

@app.route("/food/search")
@login_required
def food_search():
    """Search USDA FoodData Central. Returns JSON."""
    query = request.args.get("q", "").strip()
    if not query:
        return jsonify({"error": "Query required"}), 400
    try:
        results = search_usda(query)
        foods = [
            {
                "fdc_id":      f.get("fdcId"),
                "description": f.get("description"),
                "brand":       f.get("brandOwner", ""),
                "calories":    next((n["value"] for n in f.get("foodNutrients", [])
                                     if n.get("nutrientId") == 1008), None),
            }
            for f in results
        ]
        return jsonify({"foods": foods})
    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ---------------------------------------------------------------------------
# Routes — Meal Logging
# ---------------------------------------------------------------------------

@app.route("/meal/log", methods=["POST"])
@login_required
def log_meal():
    # TODO: Member 4 — save meal log entry to DB, trigger AI feedback
    return jsonify({"status": "coming soon"})

@app.route("/meal/feedback")
@login_required
def meal_feedback():
    # TODO: Member 3 — retrieve or generate AI meal feedback for athlete + date
    return jsonify({"feedback": "coming soon"})


# ---------------------------------------------------------------------------
# Routes — Daily Summary
# ---------------------------------------------------------------------------

@app.route("/summary/daily")
@login_required
def daily_summary():
    # TODO: Member 3 — generate and return AI daily summary for athlete + date
    return jsonify({"summary": "coming soon"})


# ---------------------------------------------------------------------------
# Routes — Analytics
# ---------------------------------------------------------------------------

@app.route("/analytics")
@login_required
def analytics():
    # TODO: Member 5 — analytics dashboard with Chart.js macro trends and training load alignment
    return "Analytics — coming soon"


# ---------------------------------------------------------------------------
# App startup
# ---------------------------------------------------------------------------

with app.app_context():
    try:
        init_db()
        print("[FuelIQ] Database initialized")
    except Exception as e:
        print(f"[FuelIQ] DB init warning: {e}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=True)
