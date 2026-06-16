# FuelIQ
### AI-Powered Nutrition Tracking for Young Athletes

FuelIQ is a web application that helps parents fuel their young athletes properly. It is **not** a weight loss app. It connects what an athlete eats to how they are training — providing real-time, sport-aware meal feedback and an end-of-day AI-generated fueling summary.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python / Flask |
| Database | PostgreSQL |
| Nutrition Data | USDA FoodData Central API |
| AI Feedback | Anthropic Claude API |
| Frontend | HTML, CSS, JavaScript |
| Charts | Chart.js |
| Email | Resend API |
| Deployment | Railway |

---

## Team & Ownership

| Member | Responsibility |
|---|---|
| Member 1 | Backend architecture, database schema, user auth |
| Member 2 | USDA API integration, food search, nutrient retrieval |
| Member 3 | Claude API integration — meal feedback + daily summary prompt engineering |
| Member 4 | Frontend UI, meal logging interface, training context inputs |
| Member 5 | Dashboard, Chart.js analytics, presentation design |

---

## Getting Started

### 1. Clone the repo
```bash
git clone https://github.com/your-org/fueliq.git
cd fueliq
```

### 2. Create a virtual environment
```bash
python3 -m venv venv
source venv/bin/activate  # Mac/Linux
venv\Scripts\activate     # Windows
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set up environment variables
```bash
cp .env.example .env
# Fill in your API keys in .env
```

You'll need:
- **USDA API Key** — free at https://fdc.nal.usda.gov/api-guide.html (use `DEMO_KEY` for testing)
- **Anthropic API Key** — https://console.anthropic.com
- **DATABASE_URL** — PostgreSQL connection string (Railway recommended)
- **FLASK_SECRET_KEY** — any random string

### 5. Run the app
```bash
python app.py
```

Visit `http://localhost:5000`

---

## Data Sources

- **USDA FoodData Central** — 600,000+ foods, free REST API, no auth required for `DEMO_KEY`
  - Docs: https://fdc.nal.usda.gov/api-guide.html
- **AAP Guidelines** — Youth athlete caloric and macro needs by age group
- **ACSM** — Sport-specific nutritional recommendations (used to calibrate AI prompts)

---

## Project Timeline

| Week | Milestone |
|---|---|
| 4 | User auth & athlete profile setup |
| 5 | USDA food search integration |
| 6 | Meal logging system |
| 7 | AI meal-level feedback (Claude API) |
| 8 | Daily summary intelligence |
| 9 | Analytics dashboard |
| 10 | Final testing & presentation |

---

## Key Principles

- **Never ask for weight.** Guidance is based on age range, sport, and training load only.
- **Not a diet app.** All AI output frames nutrition around fueling, energy, and recovery — never restriction.
- **Parent-first language.** All feedback is written for parents, not clinicians.

---

## Branch Strategy

- `main` — stable, demo-ready code only
- `dev` — active development, merge PRs here first
- `feature/your-name-feature` — individual feature branches

Never push directly to `main`.
