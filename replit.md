# Nexacart — E-Commerce Web App

## Overview
Nexacart is a full-featured e-commerce web application built with Flask and SQLite. It supports user registration/login, product browsing across 30+ categories (326+ products), shopping cart, wishlist, order history, promo codes, and an admin panel.

## Architecture
- **Backend:** Flask 3.0.3 (Python)
- **Database:** SQLite (`ecommerce.db`, auto-created on first run)
- **Templating:** Jinja2 (28+ HTML templates in `templates/`)
- **Frontend:** Vanilla CSS + JavaScript (`static/css/`, `static/js/`)
- **Auth:** Werkzeug password hashing + Flask sessions
- **Payment:** Stripe (placeholder keys — configure before production use)

## Project Layout
```
app.py              # Main Flask app (routes, DB init, helpers)
requirements.txt    # Python dependencies
templates/          # Jinja2 HTML templates
static/
  css/style.css     # Global styles
  js/main.js        # Client-side logic
  product_images/   # Product images organized by ID
  assets/           # General images/SVGs
ecommerce.db        # SQLite DB (auto-generated)
```

## Running the App
- **Workflow:** "Start application" runs `python app.py` on port 5000
- **Dev server:** Flask on `0.0.0.0:5000`
- **Deployment:** Gunicorn on `0.0.0.0:5000` (autoscale)

## Key Configuration
- `app.secret_key` — set in `app.py` (change for production)
- `ADMIN_SECRET` — default: `nexacart_admin_2026`
- `STRIPE_PUBLISHABLE_KEY` / `STRIPE_SECRET_KEY` — placeholder, replace with real keys
- `GST_RATE` — 9%
- `PER_PAGE` — 24 products per page

## Dependencies
- Flask==3.0.3
- Werkzeug==3.0.3
- gunicorn==22.0.0
