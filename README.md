# 🛍️ Nexacart — E-Commerce Web App

A full-featured e-commerce platform built with Python Flask.

## ✨ Features

- 326+ products across 30 categories
- User registration with email + phone verification
- Login via username, email, or phone number
- Forgot password / reset password flow
- Database-backed cart, wishlist, and order history
- Product detail pages with real reviews, image zoom, variant/size selector
- **Shareable product links** — share on WhatsApp, Telegram, Email, Twitter, Facebook
- Category filter bar with price, brand, rating filters
- Recently viewed products
- **Admin Panel** at `/admin/login` — manage products, orders, users
- Stripe payment integration (test mode)
- Responsive design

---

## 🚀 Quick Start (Local)

### 1. Clone the repo
```bash
git clone https://github.com/YOUR_USERNAME/nexacart_e-commerce.git
cd nexacart
```

### 2. Create virtual environment
```bash
python -m venv venv

# Windows
venv\Scripts\activate

# Mac/Linux
source venv/bin/activate
```

### 3. Install dependencies
```bash
pip install -r requirements.txt
```

### 4. Set environment variables (optional for local dev)
```bash
# Copy the example file
copy .env.example .env     # Windows
cp .env.example .env       # Mac/Linux

# Edit .env with your values (optional for local testing)
```

### 5. Run the app
```bash
python app.py
```

Open **http://127.0.0.1:5000** in your browser.

> ⚠️ **First run:** Delete `ecommerce.db` if upgrading from an older version — the database schema has changed.

---

## 🔑 Admin Panel

URL: `http://127.0.0.1:5000/admin/login`  
Default password: `nexacart_admin_2025`

Change it by setting the `ADMIN_SECRET` environment variable.

---

## ☁️ Deploy to Render.com (Free)

1. Push this repo to GitHub
2. Go to [render.com](https://render.com) → New Web Service
3. Connect your GitHub repo
4. Set these environment variables in Render dashboard:
   - `SECRET_KEY` → any long random string
   - `ADMIN_SECRET` → your chosen admin password
   - `STRIPE_PUBLISHABLE_KEY` → from Stripe dashboard
   - `STRIPE_SECRET_KEY` → from Stripe dashboard
5. Build command: `pip install -r requirements.txt`
6. Start command: `gunicorn app:app`
7. Click **Deploy**

---

## ☁️ Deploy to Railway.app

1. Push repo to GitHub
2. Go to [railway.app](https://railway.app) → New Project → Deploy from GitHub
3. Add the same environment variables listed above
4. Railway auto-detects `Procfile` and deploys

---

## ☁️ Deploy to Heroku

```bash
heroku create nexacart-app
heroku config:set SECRET_KEY=your-secret-key
heroku config:set ADMIN_SECRET=your-admin-password
git push heroku main
```

---

## 📁 Project Structure

```
nexacart/
├── app.py                  ← Main Flask application
├── requirements.txt        ← Python dependencies
├── Procfile               ← For Heroku/Render deployment
├── render.yaml            ← Render.com config
├── runtime.txt            ← Python version
├── .env.example           ← Environment variable template
├── .gitignore             ← Files excluded from Git
├── static/
│   ├── css/style.css      ← All styles
│   ├── js/main.js         ← Client-side JavaScript
│   ├── assets/            ← Product images (PNG + SVG)
│   ├── favicon.ico        ← Browser tab icon
│   └── favicon.svg
└── templates/             ← 28 Jinja2 HTML templates
    ├── base.html
    ├── home.html
    ├── products.html
    ├── product_detail.html
    ├── cart.html
    ├── checkout.html
    ├── login.html
    ├── register.html
    ├── forgot_password.html
    ├── reset_password.html
    ├── share_preview.html
    ├── admin_*.html        ← Admin panel templates
    └── ...
```

---

## 🛠️ Tech Stack

- **Backend:** Python 3.11 + Flask 3.0
- **Database:** SQLite (local) — upgrade to PostgreSQL for production
- **Frontend:** Vanilla HTML/CSS/JS + Jinja2
- **Payments:** Stripe (test mode)
- **Auth:** Werkzeug password hashing
- **Server:** Gunicorn (production)

---

## ⚠️ Before Going Live

1. Set a strong `SECRET_KEY` environment variable
2. Set a strong `ADMIN_SECRET` environment variable
3. Add real Stripe keys (`STRIPE_PUBLISHABLE_KEY`, `STRIPE_SECRET_KEY`)
4. Switch from SQLite to PostgreSQL for multi-user production use
5. Set up real email/SMS for password reset links

---

## 📧 Contact

Built with ❤️ using Python Flask.
