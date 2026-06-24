from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, date

db = SQLAlchemy()


class User(db.Model):
    __tablename__ = 'users'

    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # One user (parent) can have many athletes (children)
    athletes = db.relationship('Athlete', backref='user', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<User {self.email}>'


class Athlete(db.Model):
    __tablename__ = 'athletes'

    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)

    name = db.Column(db.String(100), nullable=False)
    age = db.Column(db.Integer, nullable=False)
    sport = db.Column(db.String(100))
    training_schedule = db.Column(db.String(255))
    dietary_notes = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    # One athlete has many meal logs
    meals = db.relationship('Meal', backref='athlete', lazy=True, cascade='all, delete-orphan')

    def __repr__(self):
        return f'<Athlete {self.name}>'


class Meal(db.Model):
    __tablename__ = 'meals'

    id = db.Column(db.Integer, primary_key=True)
    athlete_id = db.Column(db.Integer, db.ForeignKey('athletes.id'), nullable=False)

    food_name = db.Column(db.String(255), nullable=False)
    fdc_id = db.Column(db.String(50))          # USDA FoodData Central ID (optional)
    meal_time = db.Column(db.String(20))        # Breakfast, Lunch, Dinner, Snack
    portion_size = db.Column(db.Float, default=1.0)
    training_context = db.Column(db.String(255))

    # Nutrition (populated from USDA API or manual entry)
    calories = db.Column(db.Float)
    protein_g = db.Column(db.Float)
    carbs_g = db.Column(db.Float)
    fat_g = db.Column(db.Float)

    # AI feedback generated for this meal log
    ai_feedback = db.Column(db.Text)

    logged_date = db.Column(db.Date, default=date.today)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    def __repr__(self):
        return f'<Meal {self.food_name} for athlete {self.athlete_id}>'