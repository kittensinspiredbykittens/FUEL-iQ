# FUEL-iQ

**AI-Powered Nutrition Tracking for Young Athletes**

FuelIQ helps parents fuel their young athletes properly. It is not a weight loss app. It connects what an athlete eats to how they are training — providing real-time, sport-aware meal feedback powered by Claude AI.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python / Flask |
| Database | SQLite (local dev) |
| Nutrition Data | USDA FoodData Central API |
| AI Feedback | Anthropic Claude API |
| Frontend | HTML / CSS |

---

## Getting Started

### 1. Clone the repo

```bash
git clone https://github.com/kittensinspiredbykittens/FUEL-iQ.git
cd FUEL-iQ/fueliq
```

### 2. Create a virtual environment

```bash
python3 -m venv venv
source venv/bin/activate        # Mac/Linux
venv\Scripts\activate           # Windows
```

### 3. Install dependencies

```bash
pip install flask flask-sqlalchemy werkzeug python-dotenv anthropic
```

### 4. Add your Anthropic API key (optional for local testing)

Create a file called `.env` inside the `fueliq` folder:

```
ANTHROPIC_API_KEY=sk-ant-your-key-here
```

AI feedback will silently skip if no key is present — everything else works without it.

### 5. Run the app

```bash
python3 app.py
```

Visit **http://localhost:5000**

The database (`fueliq.db`) is created automatically on first run. No setup needed.

---

## Project Structure

```
FUEL-iQ/
└── fueliq/
    ├── app.py              # All routes, models, and AI logic
    └── templates/
        ├── base.html       # Shared layout and nav
        ├── login.html
        ├── register.html
        ├── profile.html    # Athlete profile setup
        ├── dashboard.html  # Meal logging + AI feedback
        └── analytics.html
```

---

## Key Principles

- **Never ask for weight.** Guidance is based on age, sport, and training load only.
- **Not a diet app.** All AI output frames nutrition around fueling, energy, and recovery — never restriction.
- **Parent-first language.** All feedback is written for parents, not clinicians.

---

## Data Sources

- **USDA FoodData Central** — 600,000+ foods, free REST API
- **AAP Guidelines** — Youth athlete caloric and macro needs by age group
- **ACSM** — Sport-specific nutritional recommendations

---

## Branch Strategy

- `main` — stable, demo-ready code only
- `dev` — active development, merge PRs here first
- `feature/your-name-feature` — individual feature branches

Never push directly to main.
