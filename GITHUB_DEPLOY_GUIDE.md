# 📤 Step-by-Step: Push to GitHub & Deploy

---

## PART 1 — Push to GitHub

### Step 1: Install Git (if not already installed)
Download from https://git-scm.com/download/win

### Step 2: Open PowerShell in the project folder
```
Right-click the "market" folder → "Open in Terminal" or "Open PowerShell window here"
```

### Step 3: Initialize Git and push
Run these commands ONE BY ONE:

```bash
git init
git add .
git commit -m "Initial commit - Nexacart e-commerce app"
```

### Step 4: Create a GitHub repository
1. Go to https://github.com → Sign in
2. Click the **+** button (top right) → **New repository**
3. Name it: `nexacart`
4. Set to **Public** or **Private**
5. Do NOT check "Initialize with README" (you already have one)
6. Click **Create repository**

### Step 5: Connect and push
Copy the commands GitHub shows you, they look like:
```bash
git remote add origin https://github.com/YOUR_USERNAME/nexacart.git
git branch -M main
git push -u origin main
```

✅ Your code is now on GitHub!

---

## PART 2 — Deploy FREE on Render.com

Render gives you a **free web service** — perfect for this app.

### Step 1: Sign up
Go to https://render.com → Sign up with GitHub

### Step 2: Create Web Service
1. Click **New +** → **Web Service**
2. Click **Connect a repository** → select your `nexacart` repo
3. Fill in:
   - **Name:** nexacart
   - **Region:** Choose nearest to you (e.g., Singapore for India)
   - **Branch:** main
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `gunicorn app:app`
   - **Instance Type:** Free

### Step 3: Set Environment Variables
Click **Environment** → Add these:

| Key | Value |
|-----|-------|
| `SECRET_KEY` | any random string like `nx8f2k9p3m7q1r4s` |
| `ADMIN_SECRET` | your admin password |
| `STRIPE_PUBLISHABLE_KEY` | from stripe.com (optional) |
| `STRIPE_SECRET_KEY` | from stripe.com (optional) |

### Step 4: Deploy
Click **Create Web Service** → wait 2-3 minutes

Your app will be live at: `https://nexacart.onrender.com`

---

## PART 3 — Deploy FREE on Railway.app (Alternative)

### Step 1: Sign up
Go to https://railway.app → Login with GitHub

### Step 2: New Project
1. Click **New Project** → **Deploy from GitHub repo**
2. Select your `nexacart` repository
3. Railway detects the Procfile automatically

### Step 3: Add Variables
Go to **Variables** tab → Add same env vars as above

### Step 4: Generate Domain
Go to **Settings** → **Networking** → **Generate Domain**

✅ Live in ~2 minutes!

---

## PART 4 — Deploy FREE on PythonAnywhere (Easiest for beginners)

### Step 1: Sign up
Go to https://www.pythonanywhere.com → Create free account

### Step 2: Upload files
1. Go to **Files** tab
2. Upload your entire `market` folder (zip it first)
3. Extract it in `/home/yourusername/nexacart/`

### Step 3: Create Web App
1. Go to **Web** tab → **Add a new web app**
2. Choose **Flask** → Python 3.10
3. Set source code: `/home/yourusername/nexacart/app.py`
4. Set working directory: `/home/yourusername/nexacart/`

### Step 4: Install packages
Go to **Consoles** → **Bash**:
```bash
pip3 install --user flask werkzeug gunicorn
```

### Step 5: Reload
Click **Reload** on the Web tab

✅ Live at: `https://yourusername.pythonanywhere.com`

---

## ⚠️ Important Notes

1. **Database:** The free tier uses SQLite. Data resets on Render/Railway free tier when the server sleeps. For permanent data, upgrade to a paid plan or use an external database.

2. **Free tier sleep:** On Render free tier, the app sleeps after 15 minutes of inactivity. First load after sleep takes ~30 seconds.

3. **Never commit `.env`** — it contains your secret keys. The `.gitignore` already excludes it.

4. **Admin password:** Change `ADMIN_SECRET` in your environment variables before going live.
