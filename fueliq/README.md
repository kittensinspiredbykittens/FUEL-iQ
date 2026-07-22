# FUEL-iQ

**AI-Powered Nutrition Tracking for Young Athletes**

FuelIQ helps parents fuel their young athletes properly. It is not a weight loss app. It connects what an athlete eats to how they are training — providing real-time, sport-aware meal feedback powered by a free-tier Llama model on Groq.

---

## Tech Stack

| Layer | Technology |
|---|---|
| Backend | Python / Flask |
| Database | SQLite (local dev) |
| Nutrition Data | USDA FoodData Central API |
| AI Feedback | Groq API / Llama 3.1 |
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
pip install -r requirements.txt
```

### 4. Add API keys

Create a file called `.env` inside the `fueliq` folder:

```
SECRET_KEY=replace-with-a-long-random-value
USDA_API_KEY=your-data-gov-api-key
GROQ_API_KEY=your-groq-api-key
```

For password-reset email delivery, also configure:

```
SMTP_HOST=smtp.example.com
SMTP_PORT=587
SMTP_USERNAME=your-smtp-username
SMTP_PASSWORD=your-smtp-password
MAIL_FROM=FuelIQ <support@example.com>
```

When SMTP is not configured and the local-development secret is in use, FuelIQ
shows the time-limited reset link on the confirmation page for easy local testing.

### Presentation demo

Open `/demo` or select **Live demo** on the public landing page. FuelIQ creates
an isolated demo family with a rolling two-week soccer fueling history. The demo
includes an optional guided product tour and a reset control; it never modifies
real family accounts.

Get a free USDA key from the [FoodData Central API guide](https://fdc.nal.usda.gov/api-guide/).
Food search falls back to USDA's rate-limited `DEMO_KEY` during local development.

The support chatbot uses the built-in knowledge base first. Groq's free-tier
Llama model handles unmatched app questions and personalized meal insights.

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
