# IMPACT S2S — Wiki Survey System

A research-driven pairwise comparison survey for identifying the best implementation strategies for smoking cessation treatment in community mental health settings.

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run in EXAMPLE mode (25 example strategies, random pairs)
python app.py

# 3. OR run in PRODUCTION mode (117 real strategies, BT adaptive algorithm)
bash start_production.sh

# 4. Open in browser
# http://localhost:5000
# Admin portal: http://localhost:5000/admin
# Local access code defaults to admin2026. Production uses the ADMIN_CODE environment variable.
```

The database and data are created automatically on first run.

## Complete File Structure

Place every file exactly as shown below. The project root is `wiki-survey/`.

```
wiki-survey/
│
│── app.py                          # Flask application — all routes (survey + admin APIs)
│── algorithm.py                    # Bradley-Terry MAP model + adaptive pair selection
│── config.py                       # Configuration with env var toggles
│── models.py                       # SQLAlchemy database models (7 tables incl. AlgorithmLog)
│── seed_data.py                    # 25 example strategies for dev/testing
│── load_csv.py                     # Loads real strategies from CSV into database
│── requirements.txt                # Python dependencies
│── start_production.sh             # Script: cleans DB, sets SURVEY_MODE=production, launches app
│
├── data/
│   └── Strategies.csv              # Real 117 strategies from the research team
│
├── static/
│   ├── css/
│   │   └── style.css               # Complete stylesheet (all pages + responsive)
│   └── images/
│       └── background.jpg          # Blue geometric background for landing page hero
│
├── templates/
│   ├── base.html                   # Base HTML template (shared head, toast, JS helpers)
│   ├── index.html                  # Landing page (hero + role select + consent) + About section
│   ├── survey.html                 # Main voting page (pairs, sidebar, gamification, quick guide)
│   └── admin/
│       ├── login.html              # Admin access code gate page
│       └── dashboard.html          # Admin portal (rankings, review, can't decide,
│                                   #   participants, strategy library, algorithm logs)
│
└── instance/
    └── wiki_survey.db              # SQLite database (auto-created on first run, do not commit)
```

### File-by-file description

| File | What it does | When it changes |
|------|-------------|-----------------|
| `app.py` | All Flask routes: page routes (`/`, `/survey`, `/admin`, `/admin/dashboard`) and API endpoints (`/api/*`). Handles mode toggle between example and production. | If you add new pages or API endpoints |
| `algorithm.py` | Bradley-Terry MAP estimation (L-BFGS-B), adaptive pair selection with proxy uncertainty, opponent diversity fix for sparse-data phase, ranking computation. | If you tune the algorithm |
| `config.py` | All environment variable toggles: `SURVEY_MODE`, `STRATEGIES_CSV`, `BT_SIGMA2`, `BT_PROXY`, `ADMIN_CODE`, `SECRET_KEY`, `DATABASE_URL`. | If you add new config options |
| `models.py` | Database tables: `strategies`, `sessions`, `comparisons`, `cant_decides`, `submitted_ideas`, `exposure_counts`, `algorithm_logs`. | If you add new database fields |
| `seed_data.py` | 25 example strategies across all 4 levels (used in example mode only). | If you want different test data |
| `load_csv.py` | Reads `data/Strategies.csv` (cp1252 encoding), skips empty rows, inserts into `strategies` table. | If CSV format changes |
| `requirements.txt` | Python packages: Flask, Flask-SQLAlchemy, gunicorn, numpy, scipy, pandas. | If you add new dependencies |
| `start_production.sh` | Convenience script: deletes existing DB, sets `SURVEY_MODE=production`, runs `python app.py`. | If you change default production settings |
| `data/Strategies.csv` | The real 117 strategies with all columns (ID, Choice, Level, ERIC, Source, etc.). | When the research team updates strategies |
| `static/css/style.css` | All CSS: landing page, survey page, sidebar, cards, modals, admin dashboard, responsive breakpoints. | For visual changes |
| `static/images/background.jpg` | Blue geometric pattern used as landing page hero background. | To change the background image |
| `templates/base.html` | HTML skeleton: charset, viewport, stylesheet link, toast notification, `api()` and `showToast()` JS helpers. | Rarely |
| `templates/index.html` | Landing page hero (title, roles, consent), About section, consent modal. | For copy or layout changes |
| `templates/survey.html` | Voting page: navbar, sidebar with level tabs + progress bar, strategy pair cards, "I Can't Decide", idea submission, celebration modal, quick guide overlay with onion diagram. | For survey UI changes |
| `templates/admin/login.html` | Admin gate: access code input, redirects to `/admin/dashboard` on success. | For login page styling |
| `templates/admin/dashboard.html` | Full admin portal with 6 tabs: Overall Ranking, Review Strategies, I Can't Decide, Participants, Strategy Library, Algorithm Logs. Includes edit modals for ideas and strategies. | For admin feature changes |

## Mode Toggle (Fallback)

Switch between modes via the `SURVEY_MODE` environment variable:

| Mode | Strategies | Pair Selection | Rankings | Algorithm Logs |
|------|-----------|---------------|----------|---------------|
| `example` (default) | 25 example | Random | Win rate | Not recorded |
| `production` | 117 from CSV | Bradley-Terry MAP adaptive | BT model scores | Full audit trail |

```bash
# Example mode (default)
python app.py

# Production mode (recommended: use the script)
bash start_production.sh

# Production with custom settings
SURVEY_MODE=production BT_SIGMA2=1.5 BT_PROXY=exposure python app.py
```

**Important:** When switching modes, delete the database (`instance/wiki_survey.db`) to start fresh.

## URL Map

| URL | Who sees it | What it does |
|-----|-------------|-------------|
| `/` | Everyone | Landing page with role selection, consent, and About section |
| `/survey` | Participants | Main voting page (requires active session) |
| `/admin` | Staff only | Access code login gate |
| `/admin/dashboard` | Staff only | Admin portal (requires authentication) |

Survey participants never see admin links. Staff access `/admin` directly by URL.

## Admin Portal Tabs

| Tab | Description |
|-----|-------------|
| **Overall Ranking** | Top 12 strategies by score, filterable by role/level/ERIC. Download CSV. |
| **Review Strategies** | User-submitted ideas: approve, reject, mark duplicate, edit all fields. |
| **I Can't Decide** | All "can't decide" responses with pair, reason, level, and user role. |
| **Participants** | Session tracking: ID, role, date, duration, votes, ideas, levels visited. |
| **Strategy Library** | Searchable list of all strategies. Edit full fields, toggle active, delete. |
| **Algorithm Logs** | Full audit trail: focal/opponent selection, MAP state, exposure, outcome, winner. Export as JSON. |

## Configuration

| Variable | Default | Description |
|----------|---------|-------------|
| `SURVEY_MODE` | `example` | `example` or `production` |
| `STRATEGIES_CSV` | `data/Strategies.csv` | Path to real CSV |
| `BT_SIGMA2` | `1.0` | BT prior variance (higher = less shrinkage) |
| `BT_PROXY` | `top_heavy` | `exposure` or `top_heavy` |
| `ADMIN_CODE` | local fallback only | Admin portal access code. Production must set this environment variable. |
| `SECRET_KEY` | (auto) | Flask session secret |
| `DATABASE_URL` | `sqlite:///wiki_survey.db` | Database URI |

## Development Stages

| Stage | Description | Status |
|-------|-------------|--------|
| 1 | User-facing survey (landing, voting, gamification, quick guide) | ✅ Complete |
| 2 | Admin portal (rankings, review, analytics, participants) | ✅ Complete |
| 3 | Real CSV data + Bradley-Terry MAP algorithm + logging | ✅ Complete |
| 4 | Testing, polish, production deployment | ✅ Complete |

## Tech Stack

- **Backend:** Python / Flask + SQLAlchemy + SQLite
- **Frontend:** HTML + CSS (custom) + Vanilla JS
- **Algorithm:** SciPy (L-BFGS-B optimizer) + NumPy
- **Fonts:** DM Serif Display + DM Sans (Google Fonts CDN)
- **Production server:** Gunicorn (in requirements.txt)

## License

Released under the [MIT License](LICENSE).
