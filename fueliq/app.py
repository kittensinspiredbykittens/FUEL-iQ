from dotenv import load_dotenv
load_dotenv()

import os
from datetime import date
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.config['SECRET_KEY'] = 'fueliq-dev-secret-2025'
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///fueliq.db'
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)

# ── Models ────────────────────────────────────────────────────────────────────

class User(db.Model):
    id            = db.Column(db.Integer, primary_key=True)
    email         = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    athletes      = db.relationship('Athlete', backref='user', lazy=True, cascade='all, delete-orphan')

class Athlete(db.Model):
    id                = db.Column(db.Integer, primary_key=True)
    user_id           = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    name              = db.Column(db.String(100), nullable=False)
    age               = db.Column(db.Integer)
    sport             = db.Column(db.String(100))
    training_schedule = db.Column(db.String(255))
    dietary_notes     = db.Column(db.Text)
    meals             = db.relationship('Meal', backref='athlete', lazy=True, cascade='all, delete-orphan')

class Meal(db.Model):
    id               = db.Column(db.Integer, primary_key=True)
    athlete_id       = db.Column(db.Integer, db.ForeignKey('athlete.id'), nullable=False)
    food_name        = db.Column(db.String(255), nullable=False)
    meal_time        = db.Column(db.String(20))
    portion_size     = db.Column(db.Float, default=1.0)
    training_context = db.Column(db.String(255))
    calories         = db.Column(db.Float)
    protein_g        = db.Column(db.Float)
    carbs_g          = db.Column(db.Float)
    fat_g            = db.Column(db.Float)
    ai_feedback      = db.Column(db.Text)
    logged_date      = db.Column(db.String(20))

with app.app_context():
    db.create_all()

# ── Auth helper ───────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

# ── Routes ────────────────────────────────────────────────────────────────────

@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return render_template('landing.html')


@app.route('/register', methods=['GET', 'POST'])
def register():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')

        if not email or not password:
            flash('Email and password are required.', 'danger')
            return render_template('register.html')

        if User.query.filter_by(email=email).first():
            flash('An account with that email already exists.', 'warning')
            return render_template('register.html')

        user = User(
            email=email,
            password_hash=generate_password_hash(password, method='pbkdf2:sha256')
        )
        db.session.add(user)
        db.session.commit()
        flash('Account created! Please log in.', 'success')
        return redirect(url_for('login'))

    return render_template('register.html')


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email    = request.form.get('email', '').strip().lower()
        password = request.form.get('password', '')
        user     = User.query.filter_by(email=email).first()

        if user and check_password_hash(user.password_hash, password):
            session['user_id'] = user.id
            if user.athletes:
                session['athlete_id'] = user.athletes[0].id
            return redirect(url_for('dashboard'))

        flash('Invalid email or password.', 'danger')

    return render_template('login.html')


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))


@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    user    = User.query.get(session['user_id'])
    athlete = Athlete.query.get(session['athlete_id']) if session.get('athlete_id') else None

    if request.method == 'POST':
        name = request.form.get('name', '').strip()
        age  = request.form.get('age', '').strip()

        if not name:
            flash('Athlete name is required.', 'danger')
            return render_template('profile.html', athlete=athlete)

        if athlete:
            athlete.name              = name
            athlete.age               = int(age) if age else None
            athlete.sport             = request.form.get('sport', '').strip()
            athlete.training_schedule = request.form.get('training_schedule', '').strip()
            athlete.dietary_notes     = request.form.get('dietary_notes', '').strip()
        else:
            athlete = Athlete(
                user_id=user.id,
                name=name,
                age=int(age) if age else None,
                sport=request.form.get('sport', '').strip(),
                training_schedule=request.form.get('training_schedule', '').strip(),
                dietary_notes=request.form.get('dietary_notes', '').strip()
            )
            db.session.add(athlete)

        db.session.commit()
        session['athlete_id'] = athlete.id
        flash(f"{athlete.name}'s profile saved.", 'success')
        return redirect(url_for('dashboard'))

    return render_template('profile.html', athlete=athlete)


@app.route('/dashboard')
@login_required
def dashboard():
    athlete = Athlete.query.get(session['athlete_id']) if session.get('athlete_id') else None

    if not athlete:
        flash("Let's set up your first athlete profile.", 'info')
        return redirect(url_for('profile'))

    today = date.today().isoformat()
    meals = Meal.query.filter_by(athlete_id=athlete.id, logged_date=today).all()

    feedback = None
    for meal in reversed(meals):
        if meal.ai_feedback:
            feedback = meal.ai_feedback
            break

    return render_template('dashboard.html',
        athlete=athlete,
        meals=meals,
        feedback=feedback,
        today=date.today().strftime('%B %-d, %Y')
    )


@app.route('/meal/log', methods=['POST'])
@login_required
def log_meal():
    athlete = Athlete.query.get(session.get('athlete_id'))
    if not athlete:
        return redirect(url_for('profile'))

    food_name = request.form.get('food_name', '').strip()
    if not food_name:
        flash('Food name is required.', 'danger')
        return redirect(url_for('dashboard'))

    try:
        portion_size = float(request.form.get('portion_size', 1.0))
    except ValueError:
        portion_size = 1.0

    meal = Meal(
        athlete_id=athlete.id,
        food_name=food_name,
        meal_time=request.form.get('meal_time', 'Snack'),
        portion_size=portion_size,
        training_context=request.form.get('training_context', '').strip(),
        logged_date=date.today().isoformat()
    )
    db.session.add(meal)
    db.session.commit()

    meal.ai_feedback = generate_ai_feedback(athlete, meal)
    db.session.commit()

    flash(f'{food_name} logged.', 'success')
    return redirect(url_for('dashboard'))


@app.route('/analytics')
@login_required
def analytics():
    athlete = Athlete.query.get(session.get('athlete_id'))
    if not athlete:
        return redirect(url_for('profile'))
    return render_template('analytics.html', athlete=athlete)


# ── AI feedback ───────────────────────────────────────────────────────────────

def generate_ai_feedback(athlete, meal):
    try:
        import anthropic
        api_key = os.getenv('ANTHROPIC_API_KEY')
        if not api_key:
            return None

        client = anthropic.Anthropic(api_key=api_key)
        prompt = f"""You are FuelIQ, an AI nutrition coach for youth athletes.

Athlete: {athlete.name}, age {athlete.age}, sport: {athlete.sport or 'not specified'}
Training load: {athlete.training_schedule or 'not specified'}
Dietary notes: {athlete.dietary_notes or 'none'}

Meal logged: {meal.food_name} x{meal.portion_size} at {meal.meal_time}
Training today: {meal.training_context or 'not specified'}

Write 2-3 sentences of warm, practical, parent-friendly nutrition feedback.
Focus on how this meal fuels their sport. Give one simple actionable tip.
No bullet points. No jargon. No emojis. Plain encouraging language."""

        response = client.messages.create(
            model='claude-sonnet-4-6',
            max_tokens=250,
            messages=[{'role': 'user', 'content': prompt}]
        )
        return response.content[0].text
    except Exception:
        return None


if __name__ == '__main__':
    app.run(debug=True, port=5000)