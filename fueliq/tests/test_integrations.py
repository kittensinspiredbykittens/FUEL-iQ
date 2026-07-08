import os

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
    fueliq.app.config.update(TESTING=True)
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
