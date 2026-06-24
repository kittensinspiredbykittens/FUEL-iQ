import os
from datetime import date
from flask import Flask, render_template, request, redirect, url_for, flash, session
from werkzeug.security import generate_password_hash, check_password_hash
from dotenv import load_dotenv
from models import db, User, Athlete, Meal

load_dotenv()

app = Flask(__name__)

# ── Configuration ────────────────────────────────────────────────────────────
app.config['SECRET_KEY'] = os.getenv('SECRET_KEY', 'dev_secret_key_change_in_prod')
app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv(
    'DATABASE_URL',
    'postgresql://localhost/fueliq'
)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db.init_app(app)

with app.app_context():
    db.create_all()


# ── Auth helpers ─────────────────────────────────────────────────────────────
def login_required(f):
    """Decorator to protect routes that require a logged-in user."""
    from functools import wraps
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Please log in to continue.', 'info')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated


def get_current_athlete():
    """Return the active athlete from session, or None."""
    athlete_id = session.get('athlete_id')
    if athlete_id:
        return Athlete.query.get(athlete_id)
    return None


# ── Index ─────────────────────────────────────────────────────────────────────
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))


# ── Register ──────────────────────────────────────────────────────────────────
@app.route('/register', methods=['GET', 'POST'])
def register():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and password are required.', 'danger')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'warning')
            return render_template('register.html')

        hashed_pw = generate_password_hash(password, method='pbkdf2:sha256')
        new_user = User(email=email, password_hash=hashed_pw)

        try:
            db.session.add(new_user)
            db.session.commit()
            flash('Account created! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            db.session.rollback()
            flash('Something went wrong. Please try again.', 'danger')

    return render_template('register.html')


# ── Login ─────────────────────────────────────────────────────────────────────
@app.route('/login', methods=['GET', 'POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))

    if request.method == 'POST':
        email = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        user = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            session['user_email'] = user.email

            # If they have athletes, auto-select the first one
            if user.athletes:
                session['athlete_id'] = user.athletes[0].id

            flash('Welcome back!', 'success')
            return redirect(url_for('dashboard'))
        else:
            flash('Invalid email or password.', 'danger')

    return render_template('login.html')


# ── Logout ────────────────────────────────────────────────────────────────────
@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.', 'info')
    return redirect(url_for('login'))


# ── Profile (create / edit athlete) ──────────────────────────────────────────
@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user = User.query.get(session['user_id'])
    athlete = get_current_athlete()

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        age = request.form.get('age', '').strip()
        sport = request.form.get('sport', '').strip()
        training_schedule = request.form.get('training_schedule', '').strip()
        dietary_notes = request.form.get('dietary_notes', '').strip()

        if not name or not age:
            flash('Athlete name and age are required.', 'danger')
            return render_template('profile.html', user=user, athlete=athlete)

        try:
            age_int = int(age)
        except ValueError:
            flash('Age must be a number.', 'danger')
            return render_template('profile.html', user=user, athlete=athlete)

        if athlete:
            # Update existing
            athlete.name = name
            athlete.age = age_int
            athlete.sport = sport
            athlete.training_schedule = training_schedule
            athlete.dietary_notes = dietary_notes
        else:
            # Create new athlete for this user
            athlete = Athlete(
                user_id=user.id,
                name=name,
                age=age_int,
                sport=sport,
                training_schedule=training_schedule,
                dietary_notes=dietary_notes
            )
            db.session.add(athlete)

        try:
            db.session.commit()
            session['athlete_id'] = athlete.id
            flash(f"{athlete.name}'s profile saved.", 'success')
            return redirect(url_for('dashboard'))
        except Exception:
            db.session.rollback()
            flash('Could not save profile. Please try again.', 'danger')

    return render_template('profile.html', user=user, athlete=athlete)


# ── Switch athlete (for multi-child families) ─────────────────────────────────
@app.route('/athlete/switch/<int:athlete_id>')
@login_required
def switch_athlete(athlete_id):
    user = User.query.get(session['user_id'])
    athlete = Athlete.query.filter_by(id=athlete_id, user_id=user.id).first()
    if athlete:
        session['athlete_id'] = athlete.id
    return redirect(url_for('dashboard'))


# ── Dashboard ─────────────────────────────────────────────────────────────────
@app.route('/dashboard')
@login_required
def dashboard():
    user = User.query.get(session['user_id'])
    athlete = get_current_athlete()

    if not athlete:
        flash("Let's set up your first athlete profile.", 'info')
        return redirect(url_for('profile'))

    # Today's meals for this athlete
    today = date.today()
    meals = Meal.query.filter_by(
        athlete_id=athlete.id,
        logged_date=today
    ).order_by(Meal.created_at.asc()).all()

    # Latest AI feedback (from the most recent meal logged today)
    latest_feedback = None
    for meal in reversed(meals):
        if meal.ai_feedback:
            latest_feedback = meal.ai_feedback
            break

    return render_template(
        'dashboard.html',
        user=user,
        athlete=athlete,
        meals=meals,
        feedback=latest_feedback,
        today=today.strftime('%A, %B %-d')
    )


# ── Meal logging ──────────────────────────────────────────────────────────────
@app.route('/meal/log', methods=['POST'])
@login_required
def log_meal():
    athlete = get_current_athlete()
    if not athlete:
        flash('No athlete profile found.', 'danger')
        return redirect(url_for('profile'))

    food_name = request.form.get('food_name', '').strip()
    if not food_name:
        flash('Food name is required.', 'danger')
        return redirect(url_for('dashboard'))

    fdc_id = request.form.get('fdc_id', '').strip() or None
    meal_time = request.form.get('meal_time', 'Snack')
    training_context = request.form.get('training_context', '').strip()

    try:
        portion_size = float(request.form.get('portion_size', 1.0))
    except ValueError:
        portion_size = 1.0

    # --- USDA FDC lookup (if FDC ID provided) ---
    calories, protein_g, carbs_g, fat_g = None, None, None, None
    if fdc_id:
        nutrition = fetch_usda_nutrition(fdc_id, portion_size)
        if nutrition:
            calories = nutrition.get('calories')
            protein_g = nutrition.get('protein_g')
            carbs_g = nutrition.get('carbs_g')
            fat_g = nutrition.get('fat_g')

    meal = Meal(
        athlete_id=athlete.id,
        food_name=food_name,
        fdc_id=fdc_id,
        meal_time=meal_time,
        portion_size=portion_size,
        training_context=training_context,
        calories=calories,
        protein_g=protein_g,
        carbs_g=carbs_g,
        fat_g=fat_g,
    )

    db.session.add(meal)
    db.session.commit()

    # --- Generate AI feedback ---
    feedback = generate_ai_feedback(athlete, meal)
    if feedback:
        meal.ai_feedback = feedback
        db.session.commit()

    flash(f'{food_name} logged for {meal_time}.', 'success')
    return redirect(url_for('dashboard'))


# ── USDA FDC helper ───────────────────────────────────────────────────────────
def fetch_usda_nutrition(fdc_id, portion_size=1.0):
    """Fetch nutrition data from USDA FoodData Central API."""
    import requests as req

    api_key = os.getenv('USDA_API_KEY', 'DEMO_KEY')
    url = f'https://api.nal.usda.gov/fdc/v1/food/{fdc_id}?api_key={api_key}'

    try:
        response = req.get(url, timeout=5)
        if response.status_code != 200:
            return None

        data = response.json()
        nutrients = {n['nutrient']['name']: n['amount'] for n in data.get('foodNutrients', [])}

        return {
            'calories':  round((nutrients.get('Energy', 0) or 0) * portion_size, 1),
            'protein_g': round((nutrients.get('Protein', 0) or 0) * portion_size, 1),
            'carbs_g':   round((nutrients.get('Carbohydrate, by difference', 0) or 0) * portion_size, 1),
            'fat_g':     round((nutrients.get('Total lipid (fat)', 0) or 0) * portion_size, 1),
        }
    except Exception:
        return None


# ── Claude AI feedback helper ─────────────────────────────────────────────────
def generate_ai_feedback(athlete, meal):
    """Call Claude to generate parent-facing nutrition feedback."""
    import anthropic

    api_key = os.getenv('ANTHROPIC_API_KEY')
    if not api_key:
        return None

    client = anthropic.Anthropic(api_key=api_key)

    nutrition_summary = ''
    if meal.calories:
        nutrition_summary = (
            f"Nutrition: {meal.calories} kcal, "
            f"{meal.protein_g}g protein, "
            f"{meal.carbs_g}g carbs, "
            f"{meal.fat_g}g fat."
        )

    prompt = f"""You are FuelIQ, an AI nutrition coach for youth athletes.

Athlete profile:
- Name: {athlete.name}
- Age: {athlete.age}
- Sport: {athlete.sport or 'not specified'}
- Training schedule: {athlete.training_schedule or 'not specified'}
- Dietary notes: {athlete.dietary_notes or 'none'}

Meal just logged:
- Food: {meal.food_name} (x{meal.portion_size} serving)
- Meal time: {meal.meal_time}
- Training context today: {meal.training_context or 'not specified'}
- {nutrition_summary}

Write a 2-3 sentence parent-friendly insight about this meal for this athlete. 
Focus on: how well it fuels their sport and training load, any timing considerations, 
and one simple, actionable suggestion. Keep it warm, clear, and practical. 
No jargon. No bullet points. Just plain encouraging guidance."""

    try:
        message = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=300,
            messages=[{'role': 'user', 'content': prompt}]
        )
        return message.content[0].text
    except Exception:
        return None


# ── Analytics (placeholder) ───────────────────────────────────────────────────
@app.route('/analytics')
@login_required
def analytics():
    athlete = get_current_athlete()
    if not athlete:
        return redirect(url_for('profile'))
    return render_template('analytics.html', athlete=athlete)


if __name__ == '__main__':
    app.run(debug=True, port=5000)