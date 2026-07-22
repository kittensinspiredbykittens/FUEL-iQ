import os
import re
from datetime import date

os.environ['DATABASE_URL'] = 'sqlite:///:memory:'
os.environ['SECRET_KEY'] = 'test-secret'

import app as fueliq


class FakeResponse:
    def __init__(self, payload):
        self.payload = payload

    def json(self):
        return self.payload

    def raise_for_status(self):
        return None


def make_user_and_athlete():
    user = fueliq.User(
        email='parent@example.com',
        password_hash='not-used-in-tests',
    )
    fueliq.db.session.add(user)
    fueliq.db.session.flush()
    athlete = fueliq.Athlete(
        user_id=user.id,
        name='Sam',
        age=14,
        sport='Soccer',
        training_schedule='Practice five days a week',
    )
    fueliq.db.session.add(athlete)
    fueliq.db.session.commit()
    return user.id, athlete.id


def setup_function():
    fueliq.app.config.update(
        TESTING=True,
        DEV_LOGIN_ENABLED=False,
    )
    with fueliq.app.app_context():
        fueliq.db.drop_all()
        fueliq.db.create_all()


def login_session(client, user_id, athlete_id=None):
    with client.session_transaction() as session:
        session['user_id'] = user_id
        if athlete_id:
            session['athlete_id'] = athlete_id


def banana_search_result():
    return {
        'fdcId': 2709224,
        'description': 'Banana, raw',
        'dataType': 'Survey (FNDDS)',
        'foodMeasures': [{
            'rank': 1,
            'gramWeight': 126,
            'disseminationText': '1 banana',
        }],
        'foodNutrients': [
            {'nutrientId': 1003, 'unitName': 'G', 'value': 0.74},
            {'nutrientId': 1004, 'unitName': 'G', 'value': 0.28},
            {'nutrientId': 1005, 'unitName': 'G', 'value': 22.71},
            {'nutrientId': 1008, 'unitName': 'KCAL', 'value': 97},
            {'nutrientId': 1079, 'unitName': 'G', 'value': 1.7},
            {'nutrientId': 1090, 'unitName': 'MG', 'value': 28},
        ],
    }


def banana_detail():
    result = banana_search_result()
    result.pop('foodMeasures')
    result['foodPortions'] = [{
        'sequenceNumber': 1,
        'gramWeight': 126,
        'portionDescription': '1 banana',
    }]
    result['foodNutrients'] = [
        {
            'nutrient': {'id': nutrient['nutrientId'], 'unitName': nutrient['unitName']},
            'amount': nutrient['value'],
        }
        for nutrient in result['foodNutrients']
    ]
    return result


def test_food_search_requires_login():
    client = fueliq.app.test_client()
    response = client.get('/api/foods/search?q=banana')
    assert response.status_code == 302
    assert '/login' in response.headers['Location']


def test_food_search_returns_nutrients_for_usda_serving(monkeypatch):
    client = fueliq.app.test_client()
    with fueliq.app.app_context():
        user_id, _ = make_user_and_athlete()
    login_session(client, user_id)

    monkeypatch.setattr(
        fueliq.requests,
        'post',
        lambda *args, **kwargs: FakeResponse({'foods': [banana_search_result()]}),
    )
    response = client.get('/api/foods/search?q=banana')

    assert response.status_code == 200
    food = response.get_json()['foods'][0]
    assert food['fdc_id'] == 2709224
    assert food['serving_label'] == '1 banana (126 g)'
    assert food['calories'] == 122
    assert food['carbs_g'] == 28.6


def test_logging_selected_food_saves_scaled_nutrients(monkeypatch):
    client = fueliq.app.test_client()
    with fueliq.app.app_context():
        user_id, athlete_id = make_user_and_athlete()
    login_session(client, user_id, athlete_id)

    monkeypatch.setattr(fueliq, 'get_usda_food', lambda fdc_id: banana_detail())
    monkeypatch.setattr(fueliq, 'generate_ai_feedback', lambda athlete, meal: None)
    response = client.post('/meal/log', data={
        'fdc_id': '2709224',
        'portion_size': '1',
        'meal_time': 'Pre-workout',
        'training_context': 'Moderate practice',
    })

    assert response.status_code == 302
    with fueliq.app.app_context():
        meal = fueliq.Meal.query.one()
        assert meal.food_name == 'Banana, Raw'
        assert meal.fdc_id == 2709224
        assert meal.serving_size_g == 126
        assert meal.calories == 122.22
        assert meal.carbs_g == 28.61
        assert meal.magnesium_mg == 35.28


def test_chatbot_answers_app_guidance_without_an_api_key():
    client = fueliq.app.test_client()
    with fueliq.app.app_context():
        user_id, athlete_id = make_user_and_athlete()
    login_session(client, user_id, athlete_id)

    response = client.post('/api/chat', json={'message': 'How do I log a meal?'})

    assert response.status_code == 200
    assert 'USDA search box' in response.get_json()['reply']


def test_password_reset_changes_password_and_invalidates_link():
    client = fueliq.app.test_client()
    with fueliq.app.app_context():
        user = fueliq.User(
            email='parent@example.com',
            password_hash=fueliq.generate_password_hash('old-password'),
        )
        fueliq.db.session.add(user)
        fueliq.db.session.commit()

    response = client.post('/forgot-password', data={'email': 'parent@example.com'})
    match = re.search(rb'href="([^"]*/reset-password/[^"]+)"', response.data)
    assert response.status_code == 200
    assert match

    reset_path = match.group(1).decode().replace('http://localhost', '')
    response = client.post(reset_path, data={
        'password': 'new-password',
        'confirm_password': 'new-password',
    })
    assert response.status_code == 302
    assert response.headers['Location'].endswith('/login')

    with fueliq.app.app_context():
        user = fueliq.User.query.filter_by(email='parent@example.com').one()
        assert fueliq.check_password_hash(user.password_hash, 'new-password')

    reused = client.get(reset_path, follow_redirects=True)
    assert b'invalid or has expired' in reused.data


def test_password_reset_request_does_not_reveal_unknown_email():
    client = fueliq.app.test_client()
    response = client.post('/forgot-password', data={'email': 'missing@example.com'})

    assert response.status_code == 200
    assert b'If an account matches that email' in response.data
    assert b'/reset-password/' not in response.data


def test_password_reset_requires_eight_character_password():
    client = fueliq.app.test_client()
    with fueliq.app.app_context():
        user = fueliq.User(
            email='parent@example.com',
            password_hash=fueliq.generate_password_hash('old-password'),
        )
        fueliq.db.session.add(user)
        fueliq.db.session.commit()
        token = fueliq.password_reset_token(user)

    response = client.post(f'/reset-password/{token}', data={
        'password': 'short',
        'confirm_password': 'short',
    })
    assert response.status_code == 200
    assert b'at least 8 characters' in response.data


def test_development_login_is_disabled_by_default():
    client = fueliq.app.test_client()
    fueliq.app.config['DEV_LOGIN_ENABLED'] = False
    assert client.get('/dev-login').status_code == 404


def test_development_login_signs_into_first_local_account():
    client = fueliq.app.test_client()
    with fueliq.app.app_context():
        user_id, athlete_id = make_user_and_athlete()
    fueliq.app.config['DEV_LOGIN_ENABLED'] = True

    response = client.get('/dev-login')

    assert response.status_code == 302
    assert response.headers['Location'].endswith('/dashboard')
    with client.session_transaction() as active_session:
        assert active_session['user_id'] == user_id
        assert active_session['athlete_id'] == athlete_id


def test_demo_mode_is_available_as_a_standard_feature():
    client = fueliq.app.test_client()
    response = client.get('/demo')
    assert response.status_code == 302
    assert '/dashboard?demo_welcome=1' in response.headers['Location']


def test_landing_page_always_offers_demo_before_login():
    client = fueliq.app.test_client()
    page = client.get('/')

    assert page.status_code == 200
    assert b'Explore the live demo' in page.data
    assert b'href="/demo"' in page.data
    assert b'No login required' in page.data


def test_demo_mode_seeds_resets_and_restores_the_previous_account():
    client = fueliq.app.test_client()
    with fueliq.app.app_context():
        user_id, athlete_id = make_user_and_athlete()
        fueliq.db.session.add(fueliq.Meal(
            athlete_id=athlete_id,
            food_name='Real Family Meal',
            logged_date=date.today().isoformat(),
        ))
        fueliq.db.session.commit()
    login_session(client, user_id, athlete_id)
    response = client.get('/demo')
    assert response.status_code == 302
    assert '/dashboard?demo_welcome=1' in response.headers['Location']

    with client.session_transaction() as active_session:
        assert active_session['demo_mode'] is True
        assert active_session['demo_return_user_id'] == user_id

    page = client.get(response.headers['Location'])
    assert b'Jordan' in page.data
    assert b'Presentation ready' in page.data
    assert b'data-tour="meal-logger"' in page.data

    with fueliq.app.app_context():
        demo_user = fueliq.User.query.filter_by(
            email=fueliq.app.config['DEMO_ACCOUNT_EMAIL']
        ).one()
        demo_athlete = fueliq.Athlete.query.filter_by(user_id=demo_user.id).one()
        demo_meal_count = fueliq.Meal.query.filter_by(athlete_id=demo_athlete.id).count()
        assert demo_meal_count >= 40
        assert fueliq.Meal.query.filter_by(food_name='Real Family Meal').count() == 1

    reset = client.post('/demo/reset')
    assert reset.status_code == 302
    with fueliq.app.app_context():
        assert fueliq.Meal.query.filter_by(athlete_id=demo_athlete.id).count() == demo_meal_count

    exit_response = client.get('/demo/exit')
    assert exit_response.status_code == 302
    with client.session_transaction() as active_session:
        assert active_session['user_id'] == user_id
        assert active_session['athlete_id'] == athlete_id
        assert 'demo_mode' not in active_session


def test_chatbot_uses_free_groq_fallback_for_unmatched_questions(monkeypatch):
    client = fueliq.app.test_client()
    with fueliq.app.app_context():
        user_id, athlete_id = make_user_and_athlete()
    login_session(client, user_id, athlete_id)

    monkeypatch.setenv('GROQ_API_KEY', 'test-key')
    monkeypatch.setattr(
        fueliq.requests,
        'post',
        lambda *args, **kwargs: FakeResponse({
            'choices': [{
                'message': {
                    'content': 'The multi-athlete switcher is not available yet.'
                }
            }]
        }),
    )

    response = client.post('/api/chat', json={
        'message': 'Can I switch between two athletes?',
    })

    assert response.status_code == 200
    assert response.get_json()['reply'] == (
        'The multi-athlete switcher is not available yet.'
    )


def test_meal_feedback_uses_local_fallback_when_groq_is_unavailable(monkeypatch):
    athlete = fueliq.Athlete(name='Sam', sport='Soccer')
    meal = fueliq.Meal(
        food_name='Banana, Raw',
        carbs_g=28.6,
        protein_g=0.9,
        training_context='Before practice',
    )
    monkeypatch.setattr(fueliq, 'groq_completion', lambda *args, **kwargs: None)

    feedback = fueliq.generate_ai_feedback(athlete, meal)

    assert 'training energy for Soccer' in feedback
    assert 'Before activity' in feedback


def test_fueling_summary_compares_logged_macro_distribution():
    meals = [
        fueliq.Meal(
            food_name='Balanced test meal',
            carbs_g=60,
            protein_g=20,
            fat_g=12,
            calories=428,
            fiber_g=8,
        )
    ]

    summary = fueliq.build_fueling_summary(meals)

    assert summary['meal_count'] == 1
    assert summary['totals']['fiber_g'] == 8
    assert summary['percentages']['carbs'] == 56.1
    assert summary['percentages']['protein'] == 18.7
    assert summary['percentages']['fat'] == 25.2
    assert summary['goals_met'] == 3
    assert summary['status'] == 'Balanced fueling mix'


def test_analytics_builds_daily_history_and_current_streak():
    meals = [
        fueliq.Meal(
            food_name='Oatmeal', logged_date='2026-07-20', meal_time='Breakfast',
            calories=250, carbs_g=45, protein_g=10, fat_g=4, fiber_g=6,
        ),
        fueliq.Meal(
            food_name='Yogurt', logged_date='2026-07-20', meal_time='Snack',
            calories=140, carbs_g=18, protein_g=12, fat_g=3, calcium_mg=180,
        ),
        fueliq.Meal(
            food_name='Rice Bowl', logged_date='2026-07-22', meal_time='Lunch',
            calories=480, carbs_g=70, protein_g=24, fat_g=12, iron_mg=3.2,
        ),
    ]

    analytics = fueliq.build_analytics(
        meals,
        days=7,
        anchor_date=date(2026, 7, 22),
    )

    assert analytics['meal_count'] == 3
    assert analytics['active_days'] == 2
    assert analytics['logging_rate'] == 29
    assert analytics['average_meals'] == 1.5
    assert analytics['current_streak'] == 1
    assert analytics['daily'][-1]['calories'] == 480
    assert analytics['timing_breakdown'][0]['label'] == 'Breakfast'
    assert analytics['recent_meals'][0].food_name == 'Rice Bowl'


def test_analytics_route_scopes_meals_to_current_athlete():
    client = fueliq.app.test_client()
    today = date.today().isoformat()
    with fueliq.app.app_context():
        user_id, athlete_id = make_user_and_athlete()
        fueliq.db.session.add(fueliq.Meal(
            athlete_id=athlete_id,
            food_name='Visible Oatmeal',
            logged_date=today,
            calories=250,
        ))
        other_user = fueliq.User(email='other@example.com', password_hash='unused')
        fueliq.db.session.add(other_user)
        fueliq.db.session.flush()
        other_athlete = fueliq.Athlete(user_id=other_user.id, name='Other')
        fueliq.db.session.add(other_athlete)
        fueliq.db.session.flush()
        fueliq.db.session.add(fueliq.Meal(
            athlete_id=other_athlete.id,
            food_name='Hidden Meal',
            logged_date=today,
            calories=999,
        ))
        fueliq.db.session.commit()
    login_session(client, user_id, athlete_id)

    response = client.get('/analytics?days=14')

    assert response.status_code == 200
    assert b'Visible Oatmeal' in response.data
    assert b'Hidden Meal' not in response.data
    assert b'14 days' in response.data
