# 🚀 Nexacart — Full Deployment Guide

## ─── PART 1: Push to GitHub ───────────────────────────────

### Step 1 — Install Git (Windows)
Download and install from: https://git-scm.com/download/win
Accept all defaults during installation.

### Step 2 — Open terminal in your project folder
Right-click the `market` folder → "Open in Terminal" (or PowerShell)

### Step 3 — Initialize and commit
```bash
git init
git add .
git commit -m "Nexacart v1.0 - Production Ready"
```

### Step 4 — Create GitHub repository
1. Go to https://github.com and sign in (create account if needed)
2. Click **+** (top right) → **New repository**
3. Repository name: `nexacart`
4. Set to **Private** (recommended) or Public
5. ❌ Do NOT check "Add README" or "Add .gitignore"
6. Click **Create repository**

### Step 5 — Connect and push
GitHub will show you commands. Run them:
```bash
git remote add origin https://github.com/YOUR_USERNAME/nexacart.git
git branch -M main
git push -u origin main
```
Enter your GitHub username and password (or Personal Access Token).

✅ Your code is now on GitHub!

---

## ─── PART 2: Deploy on Render.com (FREE) ──────────────────

Render gives you a free web service. First deployment takes ~5 minutes.

### Step 1 — Sign up
Go to https://render.com → **Sign up with GitHub**

### Step 2 — Create Web Service
1. Click **New +** → **Web Service**
2. Click **Connect a repository** → select `nexacart`
3. Fill in the form:

| Field | Value |
|-------|-------|
| Name | `nexacart` |
| Region | `Singapore` (closest to India) |
| Branch | `main` |
| Runtime | `Python 3` |
| Build Command | `pip install -r requirements.txt` |
| Start Command | `gunicorn app:app --workers=2 --timeout=120 --bind=0.0.0.0:$PORT` |
| Instance Type | `Free` |

### Step 3 — Add Environment Variables
Click the **Environment** tab → **Add Environment Variable** for each:

| Key | Value | Notes |
|-----|-------|-------|
| `SECRET_KEY` | Click "Generate" | Random secret key |
| `ADMIN_SECRET` | `YourAdminPassword123` | Admin panel password |
| `ADMIN_INVITE_CODE` | `YourAdminCode2025` | Code to create admin accounts |
| `MERCHANT_UPI_ID` | `yourname@upi` | Your UPI ID for payments |
| `MERCHANT_NAME` | `Nexacart` | Store name on UPI screen |
| `STRIPE_PUBLISHABLE_KEY` | `pk_test_...` | From stripe.com (optional) |
| `STRIPE_SECRET_KEY` | `sk_test_...` | From stripe.com (optional) |

### Step 4 — Deploy
Click **Create Web Service** → Wait 3-5 minutes

✅ Your app is live at: `https://nexacart.onrender.com`

### Step 5 — First-time setup after deployment
1. Go to `https://nexacart.onrender.com/register`
2. Select **Admin** account type
3. Enter your `ADMIN_INVITE_CODE`
4. Create your admin account
5. Visit `https://nexacart.onrender.com/admin` to access the admin panel

---

## ─── PART 3: Deploy on Railway.app (Alternative) ──────────

### Steps
1. Go to https://railway.app → **Login with GitHub**
2. **New Project** → **Deploy from GitHub** → select `nexacart`
3. Click **Variables** tab → Add same environment variables as above
4. **Settings** → **Networking** → **Generate Domain**

✅ Live in ~2 minutes!

---

## ─── PART 4: Deploy on PythonAnywhere (Beginner-Friendly) ─

### Steps
1. Sign up at https://www.pythonanywhere.com (free)
2. **Files** tab → Upload your zipped `market` folder
3. **Consoles** → **Bash**:
```bash
unzip market.zip
cd market
pip3 install --user flask werkzeug gunicorn
```
4. **Web** tab → **Add a new web app** → Flask → Python 3.10
5. Set **Source code**: `/home/yourusername/market`
6. Set **WSGI file** path to: `/home/yourusername/market/app.py`
7. **Environment variables** (in WSGI config):
```python
import os
os.environ['SECRET_KEY'] = 'your-secret-key'
os.environ['ADMIN_SECRET'] = 'your-admin-password'
os.environ['ADMIN_INVITE_CODE'] = 'your-invite-code'
os.environ['MERCHANT_UPI_ID'] = 'yourname@upi'
os.environ['MERCHANT_NAME'] = 'Nexacart'
```
8. Click **Reload**

✅ Live at: `https://yourusername.pythonanywhere.com`

---

## ─── Environment Variables Reference ──────────────────────

| Variable | Required | Description | Default |
|----------|----------|-------------|---------|
| `SECRET_KEY` | ✅ Yes | Flask session signing key | Dev key |
| `ADMIN_SECRET` | ✅ Yes | Admin panel password | `nexacart_admin_2025` |
| `ADMIN_INVITE_CODE` | ✅ Yes | Code for admin registration | `NEXACART_ADMIN_2025` |
| `MERCHANT_UPI_ID` | ✅ Yes | Your UPI ID for customer payments | `nexacart@upi` |
| `MERCHANT_NAME` | ✅ Yes | Business name on UPI screen | `Nexacart` |
| `STRIPE_PUBLISHABLE_KEY` | For card pay | From stripe.com | Test key |
| `STRIPE_SECRET_KEY` | For card pay | From stripe.com | Test key |
| `DATABASE_PATH` | Optional | SQLite file path | `ecommerce.db` |
| `FLASK_DEBUG` | Optional | `false` in production | `false` |

---

## ─── Security Checklist ────────────────────────────────────

Before going live, verify:
- [ ] `SECRET_KEY` is a long random string (min 32 characters)
- [ ] `ADMIN_SECRET` is changed from the default
- [ ] `ADMIN_INVITE_CODE` is changed from the default
- [ ] `FLASK_DEBUG` is `false` (default)
- [ ] `.env` file is NOT on GitHub (it's in `.gitignore`)
- [ ] `ecommerce.db` is NOT on GitHub (it's in `.gitignore`)

---

## ─── How Account Types Work ────────────────────────────────

| Account Type | Registration | After Login |
|-------------|--------------|-------------|
| **Customer** | Select "Customer" | Shops, cart, orders, wishlist |
| **Admin** | Select "Admin" + enter ADMIN_INVITE_CODE | Goes to /admin dashboard |

**Admin Panel URL**: `/admin` (login with admin account credentials)

---

## ─── Updating Your Deployed App ────────────────────────────

When you make changes to the code:
```bash
git add .
git commit -m "Update: describe what you changed"
git push
```
Render/Railway automatically redeploys on every push to `main`. ✅

---

## ─── Health Check ───────────────────────────────────────────

Your app has a health check endpoint:
`https://your-app.onrender.com/health`

Returns: `{"status": "ok", "db": "connected"}`

Render uses this to monitor your app automatically.
