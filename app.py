from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
import psycopg2, datetime, random, hashlib, os
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps


# ─── PostgreSQL / SQLite Compatibility Layer ──────────────────────────────────
class CompatRow:
    """Row wrapper supporting both row["column"] and row[0] access."""
    def __init__(self, row, description):
        self._row = row
        self._keys = [d[0] for d in description]
        self._dict = {k: v for k, v in zip(self._keys, row)}

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._row[key]
        return self._dict[key]

    def __iter__(self):
        return iter(self._row)

    def __len__(self):
        return len(self._row)

    def keys(self):
        return self._keys

    def get(self, key, default=None):
        return self._dict.get(key, default)

    def __contains__(self, key):
        return key in self._dict


class CompatCursor:
    """Cursor wrapper that converts ? to %s and wraps rows as CompatRow."""
    def __init__(self, cursor):
        self._cur = cursor

    def execute(self, sql, params=()):
        sql = sql.replace('?', '%s')
        self._cur.execute(sql, params)
        return self

    def executemany(self, sql, params_list):
        sql = sql.replace('?', '%s')
        self._cur.executemany(sql, params_list)
        return self

    def fetchone(self):
        if self._cur.description is None:
            return None
        row = self._cur.fetchone()
        if row is None:
            return None
        return CompatRow(row, self._cur.description)

    def fetchall(self):
        if self._cur.description is None:
            return []
        rows = self._cur.fetchall()
        return [CompatRow(row, self._cur.description) for row in rows]


class CompatConn:
    """Connection wrapper providing sqlite3-like API over psycopg2."""
    def __init__(self, conn):
        self._conn = conn

    def execute(self, sql, params=()):
        cur = CompatCursor(self._conn.cursor())
        cur.execute(sql, params)
        return cur

    def executemany(self, sql, params_list):
        cur = CompatCursor(self._conn.cursor())
        cur.executemany(sql, params_list)
        return cur

    def commit(self):
        self._conn.commit()

    def close(self):
        self._conn.close()

    def rollback(self):
        self._conn.rollback()
# ─────────────────────────────────────────────────────────────────────────────

app = Flask(__name__)
app.secret_key = os.environ.get("SESSION_SECRET", os.urandom(32))
@app.context_processor
def inject_globals():
    """Make get_img and other helpers available in ALL templates."""
    from datetime import datetime
    return dict(get_img=get_product_image, get_imgs=get_product_images, current_year=datetime.now().year)

@app.after_request
def add_security_headers(resp):
    """Add security headers to every response."""
    resp.headers['X-Content-Type-Options'] = 'nosniff'
    resp.headers['X-Frame-Options']        = 'SAMEORIGIN'
    resp.headers['X-XSS-Protection']       = '1; mode=block'
    resp.headers['Referrer-Policy']        = 'strict-origin-when-cross-origin'
    return resp

@app.errorhandler(404)
def page_not_found(e):
    return render_template('error.html', code=404,
        message="Page not found.",
        detail="The page you're looking for doesn't exist."), 404

@app.errorhandler(500)
def server_error(e):
    return render_template('error.html', code=500,
        message="Something went wrong.",
        detail="We're on it! Please try again in a moment."), 500

@app.route("/health")
def health_check():
    """Health check endpoint for deployment platforms."""
    try:
        conn = get_db()
        conn.execute("SELECT 1").fetchone()
        conn.close()
        return jsonify({"status":"ok","db":"connected"}), 200
    except Exception as e:
        return jsonify({"status":"error","detail":str(e)}), 500


ADMIN_SECRET = "nexacart_admin_2026"

STRIPE_PUBLISHABLE_KEY = "pk_test_YOUR_PUBLISHABLE_KEY"
STRIPE_SECRET_KEY      = "sk_test_YOUR_SECRET_KEY"

PROMO_CODES = {
    "SAVE10":10, "MARKET20":20, "TECH15":15, "WELCOME5":5,
    "FASHION30":30, "BEAUTY15":15, "FOOD20":20, "SUMMER25":25,
    "WINTER20":20, "MONSOON15":15, "FIRST50":50,
}
GST_RATE  = 0.09
PER_PAGE  = 24   # products per page


# ─── Product Image System ─────────────────────────────────────────────
# Images live in:  static/product_images/<product_id>/1.png  (up to 4.png)
# No code changes needed — just drop image files in the right folder.
# Supported formats: .jpg  .jpeg  .png

def get_product_images(product_id):
    """Return list of ONLY actually-uploaded images (up to 6) for a product.
    Never returns dummy/placeholder paths for slots with no file."""
    folder = os.path.join(os.path.dirname(__file__), "static", "product_images", str(product_id))
    images = []
    for i in range(1, 7):   # support up to 6 images
        for ext in ("jpg", "jpeg", "png", "webp"):
            path = os.path.join(folder, f"{i}.{ext}")
            if os.path.exists(path):
                images.append(f"product_images/{product_id}/{i}.{ext}")
                break
    return images  # returns EMPTY list if no images uploaded — caller handles fallback

def get_product_image(product_id, name="", category=""):
    """Return the main image path for a product (for backward compat).
    Returns a category-colored placeholder if no image uploaded."""
    imgs = get_product_images(product_id)
    return imgs[0] if imgs else f"product_images/{product_id}/1.png"



CATEGORY_META = {
    "Electronics":         ("⚡", "bg-blue"),
    "Laptops & Computers": ("💻", "bg-indigo"),
    "Smartphones":         ("📱", "bg-purple"),
    "Audio":               ("🎧", "bg-violet"),
    "Wearables":           ("⌚", "bg-blue"),
    "Clothing — Men":      ("👔", "bg-green"),
    "Clothing — Women":    ("👗", "bg-pink"),
    "Clothing — Kids":     ("👕", "bg-yellow"),
    "Fashion Accessories": ("👜", "bg-rose"),
    "Footwear":            ("👟", "bg-orange"),
    "Beauty & Skincare":   ("💄", "bg-pink"),
    "Hair Care":           ("💇", "bg-rose"),
    "Fragrances":          ("🌸", "bg-violet"),
    "Home & Living":       ("🛋️", "bg-green"),
    "Kitchen & Dining":    ("🍳", "bg-orange"),
    "Appliances":          ("🏠", "bg-blue"),
    "Groceries & Food":    ("🛒", "bg-yellow"),
    "Health & Wellness":   ("💊", "bg-green"),
    "Sports & Fitness":    ("🏋️", "bg-orange"),
    "Books & Stationery":  ("📚", "bg-indigo"),
    "Toys & Games":        ("🎮", "bg-purple"),
    "Furniture":           ("🪑", "bg-green"),
    "Pet Supplies":        ("🐾", "bg-yellow"),
    "Automotive":          ("🚗", "bg-indigo"),
    "Outdoor & Garden":    ("🌿", "bg-green"),
    "Baby & Maternity":    ("🍼", "bg-pink"),
    "Stationery & Office": ("🖊️", "bg-indigo"),
    "Musical Instruments": ("🎸", "bg-violet"),
    "Travel & Luggage":    ("✈️", "bg-blue"),
    "Jewellery":           ("💍", "bg-rose"),
}

SUPER_CATS = {
    "Tech & Gadgets":  ["Electronics","Laptops & Computers","Smartphones","Audio","Wearables"],
    "Fashion":         ["Clothing — Men","Clothing — Women","Clothing — Kids","Fashion Accessories","Footwear","Jewellery"],
    "Beauty":          ["Beauty & Skincare","Hair Care","Fragrances"],
    "Home & Kitchen":  ["Home & Living","Kitchen & Dining","Appliances","Furniture","Outdoor & Garden"],
    "Food & Health":   ["Groceries & Food","Health & Wellness","Baby & Maternity"],
    "Sports & More":   ["Sports & Fitness","Books & Stationery","Stationery & Office","Toys & Games","Musical Instruments","Pet Supplies","Automotive","Travel & Luggage"],
}

# Season → categories to highlight
SEASON_PRODUCTS = {
    "Summer":  ["Sports & Fitness","Clothing — Men","Clothing — Women","Footwear","Beauty & Skincare","Outdoor & Garden","Travel & Luggage"],
    "Monsoon": ["Footwear","Appliances","Groceries & Food","Health & Wellness","Home & Living","Clothing — Men","Clothing — Women"],
    "Winter":  ["Clothing — Men","Clothing — Women","Clothing — Kids","Appliances","Health & Wellness","Footwear","Home & Living"],
    "Spring":  ["Beauty & Skincare","Fragrances","Outdoor & Garden","Clothing — Women","Sports & Fitness","Home & Living","Jewellery"],
}



def get_season():
    m = datetime.date.today().month
    if m in [3,4,5]:   return "Spring"
    if m in [6,7,8]:   return "Summer" if m==6 else "Monsoon"
    if m in [9,10,11]: return "Monsoon" if m<=10 else "Winter"
    return "Winter"

def login_required(f):
    @wraps(f)
    def decorated(*a,**kw):
        if "user" not in session: return redirect(url_for("login"))
        return f(*a,**kw)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*a,**kw):
        if not session.get("is_admin"): return redirect(url_for("admin_login"))
        return f(*a,**kw)
    return decorated

# ═══════════════════════════════════════════════════════════
# DATABASE
# ═══════════════════════════════════════════════════════════
def get_db():
    url = os.environ.get("DATABASE_URL", "")
    if not url:
        raise RuntimeError("DATABASE_URL environment variable is not set.")
    conn = psycopg2.connect(url)
    return CompatConn(conn)

def init_db():
    conn = get_db()
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users(
            id           SERIAL PRIMARY KEY,
            username     TEXT UNIQUE,
            password     TEXT,
            email        TEXT,
            phone        TEXT,
            country_code TEXT DEFAULT '+91',
            address      TEXT,
            city         TEXT,
            pincode      TEXT,
            is_verified  INTEGER DEFAULT 0,
            role         TEXT DEFAULT 'customer',
            joined       TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS password_resets(
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER REFERENCES users(id),
            token      TEXT UNIQUE,
            expires_at TEXT,
            used       INTEGER DEFAULT 0
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS products(
            id       SERIAL PRIMARY KEY,
            name     TEXT, price REAL, category TEXT, icon TEXT, badge TEXT,
            rating   REAL DEFAULT 4.0, reviews INTEGER DEFAULT 0,
            trending INTEGER DEFAULT 0, image TEXT,
            stock    INTEGER DEFAULT 100,
            variants TEXT DEFAULT ''
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS cart(
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER REFERENCES users(id),
            product_id INTEGER,
            quantity   INTEGER DEFAULT 1,
            variant    TEXT DEFAULT '',
            added_at   TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS wishlist(
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER REFERENCES users(id),
            product_id INTEGER,
            added_at   TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_id, product_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS orders(
            id             SERIAL PRIMARY KEY,
            user_id        INTEGER REFERENCES users(id),
            order_ref      TEXT UNIQUE,
            total          REAL, subtotal REAL, discount_amt REAL, gst_amt REAL,
            promo_code     TEXT, status TEXT DEFAULT 'Confirmed',
            address        TEXT, city TEXT, pincode TEXT,
            payment_method TEXT DEFAULT 'Stripe/Card',
            payment_txn_id TEXT DEFAULT '',
            created_at     TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS order_items(
            id         SERIAL PRIMARY KEY,
            order_id   INTEGER REFERENCES orders(id),
            product_id INTEGER,
            name       TEXT, price REAL, quantity INTEGER DEFAULT 1, variant TEXT
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS reviews(
            id         SERIAL PRIMARY KEY,
            product_id INTEGER,
            user_id    INTEGER REFERENCES users(id),
            rating     INTEGER CHECK(rating BETWEEN 1 AND 5),
            title      TEXT, body TEXT,
            created_at TIMESTAMP DEFAULT NOW(),
            UNIQUE(product_id, user_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS recently_viewed(
            id         SERIAL PRIMARY KEY,
            user_id    INTEGER REFERENCES users(id),
            product_id INTEGER,
            viewed_at  TIMESTAMP DEFAULT NOW(),
            UNIQUE(user_id, product_id)
        )
    """)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS admin_requests(
            id         SERIAL PRIMARY KEY,
            username   TEXT, email TEXT, phone TEXT,
            reason     TEXT, status TEXT DEFAULT 'pending',
            created_at TIMESTAMP DEFAULT NOW()
        )
    """)
    conn.commit()
    conn.close()

def seed_default_users():
    """Seed default admin and customer accounts if no users exist."""
    conn = get_db()
    count = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    if count == 0:
        conn.execute(
            "INSERT INTO users(username,password,email,phone,country_code,is_verified,role) VALUES(?,?,?,?,?,1,?)",
            ("admin", generate_password_hash("Admin@1234"), "admin@nexacart.com", None, "+91", "admin")
        )
        conn.execute(
            "INSERT INTO users(username,password,email,phone,country_code,is_verified,role) VALUES(?,?,?,?,?,1,?)",
            ("customer", generate_password_hash("Customer@1234"), "customer@nexacart.com", None, "+91", "customer")
        )
        conn.commit()
    conn.close()

def get_user_id():
    if "user_id" in session: return session["user_id"]
    conn = get_db()
    u = conn.execute("SELECT id FROM users WHERE username=?", (session["user"],)).fetchone()
    conn.close()
    if u:
        session["user_id"] = u["id"]
        return u["id"]
    return None

def calc_totals(subtotal, discount_pct):
    d    = round(subtotal * discount_pct / 100, 2)
    disc = subtotal - d
    gst  = round(disc * GST_RATE, 2)
    return dict(discount_amt=d, discounted=disc, gst_amt=gst, grand_total=round(disc+gst,2))

def track_recently_viewed(user_id, product_id):
    conn = get_db()
    conn.execute("""INSERT INTO recently_viewed(user_id,product_id,viewed_at) VALUES(?,?,NOW())
                    ON CONFLICT (user_id,product_id) DO UPDATE SET viewed_at=NOW()""",
                 (user_id, product_id))
    # Keep only last 12
    conn.execute("""DELETE FROM recently_viewed WHERE user_id=? AND id NOT IN (
        SELECT id FROM recently_viewed WHERE user_id=? ORDER BY viewed_at DESC LIMIT 12)""",
                 (user_id, user_id))
    conn.commit(); conn.close()

def get_cart_items(user_id):
    conn = get_db()
    items = conn.execute("""
        SELECT c.id as cart_id, c.quantity, c.variant,
               p.id, p.name, p.price, p.category, p.icon, p.badge, p.rating
        FROM cart c JOIN products p ON c.product_id=p.id
        WHERE c.user_id=? ORDER BY c.added_at DESC""", (user_id,)).fetchall()
    conn.close()
    return items

def get_cart_count(user_id):
    conn = get_db()
    r = conn.execute("SELECT COALESCE(SUM(quantity),0) FROM cart WHERE user_id=?", (user_id,)).fetchone()
    conn.close()
    return r[0] if r else 0

def get_customization_options(category, name=""):
    """
    Return category-specific customization options.
    Each option is: {"label": str, "key": str, "choices": [str, ...], "required": bool}
    """
    name_lower = name.lower()

    # ── Tech & Electronics ──
    if category == "Smartphones":
        storage = ["128 GB","256 GB","512 GB","1 TB"]
        colors  = ["Midnight Black","Pearl White","Deep Blue","Forest Green","Titanium"]
        return [
            {"label":"Storage","key":"storage","choices":storage,"required":True},
            {"label":"Colour","key":"colour","choices":colors,"required":True},
        ]

    if category == "Laptops & Computers":
        ram  = ["8 GB RAM","16 GB RAM","32 GB RAM","64 GB RAM"]
        stor = ["256 GB SSD","512 GB SSD","1 TB SSD","2 TB SSD"]
        return [
            {"label":"RAM","key":"ram","choices":ram,"required":True},
            {"label":"Storage","key":"storage","choices":stor,"required":True},
        ]

    if category == "Audio":
        colors = ["Black","White","Navy Blue","Silver","Rose Gold"]
        conn   = ["Bluetooth","Wired","Both"]
        return [
            {"label":"Colour","key":"colour","choices":colors,"required":False},
            {"label":"Connectivity","key":"connectivity","choices":conn,"required":False},
        ]

    if category == "Wearables":
        sizes  = ["Small (130–180 mm)","Medium (150–200 mm)","Large (170–220 mm)"]
        colors = ["Black","Silver","Gold","Rose Gold","Midnight"]
        return [
            {"label":"Band Size","key":"size","choices":sizes,"required":True},
            {"label":"Colour","key":"colour","choices":colors,"required":False},
        ]

    if category == "Electronics":
        return [
            {"label":"Colour","key":"colour",
             "choices":["Black","White","Silver","Grey"],"required":False},
        ]

    # ── Clothing ──
    if category == "Clothing — Men":
        return [
            {"label":"Size","key":"size","choices":["XS","S","M","L","XL","XXL","3XL"],"required":True},
            {"label":"Colour","key":"colour",
             "choices":["White","Black","Navy Blue","Grey","Olive","Maroon","Royal Blue"],"required":True},
        ]

    if category == "Clothing — Women":
        return [
            {"label":"Size","key":"size","choices":["XS","S","M","L","XL","XXL"],"required":True},
            {"label":"Colour","key":"colour",
             "choices":["White","Black","Pink","Beige","Red","Teal","Lavender","Mustard"],"required":True},
        ]

    if category == "Clothing — Kids":
        return [
            {"label":"Age / Size","key":"size",
             "choices":["1-2 Y","2-3 Y","3-4 Y","4-5 Y","5-6 Y","6-7 Y","8-9 Y","10-11 Y"],"required":True},
            {"label":"Colour","key":"colour",
             "choices":["White","Blue","Pink","Yellow","Green","Red","Multicolour"],"required":False},
        ]

    # ── Footwear ──
    if category == "Footwear":
        return [
            {"label":"Size (UK)","key":"size",
             "choices":["UK 3","UK 4","UK 5","UK 6","UK 7","UK 8","UK 9","UK 10","UK 11","UK 12"],"required":True},
            {"label":"Colour","key":"colour",
             "choices":["Black","White","Brown","Navy","Grey","Tan"],"required":False},
        ]

    # ── Fashion & Accessories ──
    if category == "Fashion Accessories":
        return [
            {"label":"Colour","key":"colour",
             "choices":["Black","Brown","Tan","Navy","Burgundy","Olive","Nude"],"required":False},
        ]

    if category == "Jewellery":
        return [
            {"label":"Metal","key":"metal",
             "choices":["Gold (22K)","Gold (18K)","Rose Gold","Silver (925)","Platinum"],"required":True},
            {"label":"Size","key":"size",
             "choices":["Free Size","Size 6","Size 8","Size 10","Size 12","Size 14","Size 16"],"required":False},
        ]

    # ── Beauty & Personal Care ──
    if category in ("Beauty & Skincare", "Hair Care"):
        return [
            {"label":"Pack Size","key":"pack",
             "choices":["30 ml / 30 g","50 ml / 50 g","100 ml / 100 g","150 ml / 150 g","200 ml / 200 g"],"required":False},
        ]

    if category == "Fragrances":
        return [
            {"label":"Size","key":"size","choices":["25 ml","50 ml","75 ml","100 ml","150 ml"],"required":True},
        ]

    # ── Home & Kitchen ──
    if category == "Furniture":
        colors = ["Natural Wood","Dark Walnut","White","Grey","Black"]
        return [
            {"label":"Finish / Colour","key":"colour","choices":colors,"required":True},
        ]

    if category == "Appliances":
        capacities = {"washing":["6 kg","7 kg","8 kg","9 kg","10 kg"],
                      "fridge":["180 L","253 L","320 L","450 L","550 L"],
                      "ac":["0.75 Ton","1 Ton","1.5 Ton","2 Ton"],
                      "default":["Standard","Large","XL"]}
        nl = name_lower
        choices = (capacities["washing"] if "wash" in nl else
                   capacities["fridge"]  if "fridge" in nl or "refrigerator" in nl else
                   capacities["ac"]      if " ac" in nl or "conditioner" in nl else
                   capacities["default"])
        return [{"label":"Capacity","key":"capacity","choices":choices,"required":True}]

    # ── Sports ──
    if category == "Sports & Fitness":
        if any(w in name_lower for w in ["mat","rug"]):
            return [{"label":"Thickness","key":"thickness",
                     "choices":["4 mm","6 mm","8 mm","10 mm"],"required":False}]
        if any(w in name_lower for w in ["shoe","boot","sneaker","running"]):
            return [{"label":"Size (UK)","key":"size",
                     "choices":["UK 6","UK 7","UK 8","UK 9","UK 10","UK 11"],"required":True}]
        if "weight" in name_lower or "dumbbell" in name_lower or "kg" in name_lower:
            return [{"label":"Weight","key":"weight",
                     "choices":["1 kg","2 kg","5 kg","10 kg","15 kg","20 kg"],"required":True}]
        return []

    # ── Books & Stationery ──
    if category in ("Books & Stationery","Stationery & Office"):
        return [
            {"label":"Pack of","key":"pack","choices":["1","2","3","5","10"],"required":False},
        ]

    # ── Groceries ──
    if category == "Groceries & Food":
        return [
            {"label":"Pack Size","key":"pack",
             "choices":["250 g","500 g","1 kg","2 kg","5 kg"],"required":False},
        ]

    # ── Pet Supplies ──
    if category == "Pet Supplies":
        return [
            {"label":"Pack Size","key":"pack",
             "choices":["500 g","1 kg","3 kg","7 kg","15 kg"],"required":False},
            {"label":"Flavour","key":"flavour",
             "choices":["Original","Chicken","Beef","Lamb","Salmon","Vegetarian"],"required":False},
        ]

    # ── Travel & Luggage ──
    if category == "Travel & Luggage":
        return [
            {"label":"Colour","key":"colour",
             "choices":["Black","Navy Blue","Red","Grey","Olive Green","Rose Gold"],"required":False},
            {"label":"Size","key":"size",
             "choices":['Cabin (18"–20")', 'Medium (24"–26")', 'Large (28"–32")'],"required":False},
        ]

    # ── No options ──
    return []

# Keep backward compatible
def get_variants(category):
    opts = get_customization_options(category)
    size_opt = next((o for o in opts if o["key"]=="size"), None)
    return size_opt["choices"] if size_opt else []

def _get_product_features(category, name):
    feats = {
        "Electronics":         ["Smart home compatible","Energy Star certified","2-year warranty","Easy setup","Remote & app control"],
        "Laptops & Computers": ["Latest generation processor","Fast SSD storage","Backlit keyboard","Multiple I/O ports","MIL-SPEC durability"],
        "Smartphones":         ["5G connectivity","AMOLED display","Fast charging","Multi-camera system","Expandable storage"],
        "Audio":               ["Active Noise Cancellation","30-hour battery","Bluetooth 5.3","Foldable design","Carrying case included"],
        "Wearables":           ["Health & fitness tracking","GPS tracking","Water resistant (5ATM)","7-day battery","Sleep monitoring"],
        "Clothing — Men":      ["100% premium cotton","Pre-shrunk","Machine washable","Regular fit","Multiple colours"],
        "Clothing — Women":    ["Soft breathable fabric","Wrinkle resistant","Easy care","Contemporary design","True-to-size fit"],
        "Clothing — Kids":     ["Child-safe materials","Easy-on design","Durable stitching","Colourfast dyes","Hypoallergenic"],
        "Fashion Accessories": ["Premium material","Handcrafted finish","Multiple compartments","Adjustable strap","Dust bag included"],
        "Footwear":            ["Cushioned insole","Slip-resistant sole","Breathable upper","True-to-size","1-year warranty"],
        "Beauty & Skincare":   ["Dermatologist tested","Paraben-free","Cruelty-free","SPF protection","All skin types"],
        "Hair Care":           ["Sulphate-free","Strengthens hair","Controls frizz","Colour-safe","Nourishes & hydrates"],
        "Fragrances":          ["Long-lasting 8+ hours","Eau de Parfum","Nature-inspired","Premium glass bottle","Unique notes"],
        "Home & Living":       ["Premium materials","Easy assembly","Stain resistant","Modern design","1-year warranty"],
        "Kitchen & Dining":    ["Food-grade materials","Dishwasher safe","Heat resistant","BPA-free","Easy to clean"],
        "Appliances":          ["5-star energy rating","1-year warranty","Easy installation","Auto shut-off","Low noise"],
        "Groceries & Food":    ["100% natural","No preservatives","Hygienically packed","Source verified","Ready to use"],
        "Health & Wellness":   ["Clinically tested","No side effects","Natural formula","GMP certified","Doctor recommended"],
        "Sports & Fitness":    ["Professional grade","Ergonomic design","Sweat resistant","Durable","All fitness levels"],
        "Books & Stationery":  ["Bestselling","Original edition","Quality paper","Durable binding","Index included"],
        "Toys & Games":        ["Child-safe","Age-appropriate","Educational value","Durable","Guidelines included"],
        "Furniture":           ["Solid wood","Easy assembly","Weight tested","5-year warranty","Scratch-resistant"],
        "Pet Supplies":        ["Vet approved","Natural ingredients","No chemicals","All breeds","Hypoallergenic"],
        "Automotive":          ["OEM compatible","All-weather","Easy installation","Vehicle-specific","1-year warranty"],
        "Outdoor & Garden":    ["Weather resistant","UV protected","Eco-friendly","Easy setup","Indian climate ready"],
        "Baby & Maternity":    ["BPA-free","Dermatologist tested","Gentle on skin","Easy to clean","Certified safe"],
        "Jewellery":           ["BIS hallmarked","Certified gemstones","Ethically sourced","Handcrafted","Certificate of authenticity"],
        "Musical Instruments": ["Professional grade","Standard tuning","Beginner accessories","All levels","Quality resonance"],
        "Stationery & Office": ["Premium quality","Long-lasting","Energy efficient","Office & home use","Compatible accessories"],
        "Travel & Luggage":    ["TSA-approved lock","360° spinner wheels","Expandable","Lightweight","10-year warranty"],
    }
    return feats.get(category, ["Premium quality","1-year warranty","30-day returns","Free delivery","Genuine product"])



def insert_sample_products():
    conn = get_db()
    if conn.execute("SELECT COUNT(*) FROM products").fetchone()[0] > 0:
        conn.close(); return
    products = [
        ("Sony Bravia 55-inch 4K TV",65000,"Electronics","📺","Best Seller",4.7,1820,1),
        ("LG OLED 65-inch TV",155000,"Electronics","📺","Premium",4.9,934,1),
        ("Amazon Echo Dot 5th Gen",4499,"Electronics","🔊",None,4.4,6721,0),
        ("Google Nest Hub Max",19999,"Electronics","📱",None,4.5,2310,0),
        ("Xiaomi Smart TV 43-inch",28000,"Electronics","📺","Budget Pick",4.3,4120,0),
        ("Apple TV 4K",18900,"Electronics","📺",None,4.6,1543,0),
        ("Projector Epson EH-TW750",55000,"Electronics","🎥",None,4.4,320,0),
        ("Ring Video Doorbell Pro",17000,"Electronics","🔔",None,4.3,891,0),
        ("Philips Hue Smart Bulb 4-Pack",3999,"Electronics","💡","New",4.5,2100,1),
        ("Blink Outdoor Camera",8999,"Electronics","📷",None,4.2,1430,0),
        ("Chromecast with Google TV",6499,"Electronics","📺",None,4.4,3200,0),
        ("TP-Link WiFi 6 Router",9999,"Electronics","📡","New",4.6,1890,1),
        ("MacBook Pro 14-inch M3",189000,"Laptops & Computers","💻","Best Seller",4.9,2341,1),
        ("Dell XPS 15",145000,"Laptops & Computers","💻",None,4.7,987,0),
        ("HP Pavilion 15",62000,"Laptops & Computers","💻","Budget Pick",4.3,3420,0),
        ("Lenovo ThinkPad X1 Carbon",138000,"Laptops & Computers","💻",None,4.8,1120,0),
        ("ASUS ROG Strix G15",95000,"Laptops & Computers","🎮","Gaming",4.7,2190,1),
        ("Acer Swift 3",48000,"Laptops & Computers","💻",None,4.3,2870,0),
        ("MSI Creator Z16",175000,"Laptops & Computers","💻","New",4.8,430,1),
        ("Mac Mini M2",69000,"Laptops & Computers","🖥️",None,4.8,1670,0),
        ("Logitech MX Keys Keyboard",9999,"Laptops & Computers","⌨️",None,4.6,5430,0),
        ("Samsung 27-inch 4K Monitor",32000,"Laptops & Computers","🖥️",None,4.5,2100,0),
        ("Raspberry Pi 5",5499,"Laptops & Computers","🖥️","New",4.7,890,1),
        ("WD My Passport 2TB HDD",5500,"Laptops & Computers","💾",None,4.4,6780,0),
        ("iPhone 15 Pro Max",149900,"Smartphones","📱","New",4.9,8730,1),
        ("Samsung Galaxy S24 Ultra",130000,"Smartphones","📱","Best Seller",4.8,6540,1),
        ("OnePlus 12",64999,"Smartphones","📱",None,4.6,4320,0),
        ("Google Pixel 8 Pro",89000,"Smartphones","📱",None,4.7,2310,0),
        ("Realme GT 5 Pro",42000,"Smartphones","📱","Budget Pick",4.4,5670,0),
        ("Xiaomi 14 Pro",79999,"Smartphones","📱",None,4.5,3210,0),
        ("Nothing Phone 2a",24999,"Smartphones","📱","New",4.5,7890,1),
        ("iQOO 12",52999,"Smartphones","📱","Gaming",4.6,2890,0),
        ("Motorola Edge 50 Pro",31999,"Smartphones","📱",None,4.3,3120,0),
        ("Vivo V30 Pro",44999,"Smartphones","📱",None,4.4,2560,0),
        ("Samsung Galaxy A55",38000,"Smartphones","📱",None,4.5,4310,0),
        ("OPPO Reno 11",32999,"Smartphones","📱","New",4.3,1980,1),
        ("Sony WH-1000XM5",29990,"Audio","🎧","Best Seller",4.8,12300,1),
        ("Apple AirPods Pro 2",24900,"Audio","🎧",None,4.7,9870,0),
        ("Bose QuietComfort 45",26000,"Audio","🎧",None,4.7,5430,0),
        ("JBL Flip 6 Speaker",9999,"Audio","🔊",None,4.6,14200,0),
        ("Sennheiser HD 560S",11000,"Audio","🎧","Studio",4.7,2340,0),
        ("Sony WF-1000XM5 Earbuds",19990,"Audio","🎵","New",4.8,4320,1),
        ("Marshall Stanmore III",30000,"Audio","🔊",None,4.6,1230,0),
        ("Boat Rockerz 450 Pro",1999,"Audio","🎧","Budget Pick",4.2,23400,0),
        ("JBL Xtreme 3",19999,"Audio","🔊",None,4.5,3210,0),
        ("Bang & Olufsen Beosound",85000,"Audio","🎵","Premium",4.9,340,0),
        ("Anker Soundcore Q45",3499,"Audio","🎧","Budget Pick",4.3,8900,0),
        ("Sony SRS-XB43",12999,"Audio","🔊",None,4.5,4560,0),
        ("Apple Watch Ultra 2",89900,"Wearables","⌚","Best Seller",4.9,4320,1),
        ("Samsung Galaxy Watch 6 Pro",42000,"Wearables","⌚",None,4.7,2310,0),
        ("Garmin Fenix 7X",75000,"Wearables","⌚","Sports",4.8,1230,0),
        ("Fitbit Charge 6",16000,"Wearables","⌚",None,4.5,6780,0),
        ("Noise ColorFit Pro 5",3499,"Wearables","⌚","Budget Pick",4.2,18900,0),
        ("Mi Smart Band 8",3499,"Wearables","⌚",None,4.3,21000,0),
        ("Garmin Venu 3",55000,"Wearables","⌚",None,4.8,890,1),
        ("Amazfit GTR 4",18999,"Wearables","⌚",None,4.4,5670,0),
        ("Allen Solly Slim Fit Shirt",2499,"Clothing — Men","👔","Best Seller",4.3,8900,1),
        ("Levi's 511 Slim Jeans",3999,"Clothing — Men","👖",None,4.5,12300,0),
        ("Raymond Wool Blazer",12000,"Clothing — Men","🧥","Premium",4.6,2310,0),
        ("Nike Dri-FIT T-Shirt",1799,"Clothing — Men","👕",None,4.4,19800,0),
        ("Peter England Formal Trousers",2199,"Clothing — Men","👖",None,4.2,6780,0),
        ("H&M Relaxed Linen Shirt",1499,"Clothing — Men","👔","New",4.3,5430,1),
        ("Van Heusen Sweater",2799,"Clothing — Men","🧥",None,4.4,4320,0),
        ("Wrangler Cargo Pants",2599,"Clothing — Men","👖",None,4.3,7890,0),
        ("Fabindia Kurta Set",2999,"Clothing — Men","👘",None,4.5,6540,0),
        ("Arrow Formal Suit",15000,"Clothing — Men","🧥","Premium",4.7,1230,0),
        ("Tommy Hilfiger Polo",3499,"Clothing — Men","👕",None,4.5,8760,0),
        ("United Colors of Benetton Chinos",2999,"Clothing — Men","👖",None,4.3,5670,0),
        ("Woodland Denim Jacket",3999,"Clothing — Men","🧥",None,4.4,3210,0),
        ("Puma Tracksuit Set",3499,"Clothing — Men","👕","Sports",4.5,9870,1),
        ("Biba Anarkali Kurta",2799,"Clothing — Women","👗","Best Seller",4.5,14300,1),
        ("Zara Floral Midi Dress",4999,"Clothing — Women","👗","New",4.6,6780,1),
        ("W Salwar Suit Set",3499,"Clothing — Women","👘",None,4.4,9870,0),
        ("H&M High-Waist Jeans",2499,"Clothing — Women","👖",None,4.3,12400,0),
        ("AND Blazer Dress",5999,"Clothing — Women","👗","Premium",4.7,3210,0),
        ("Global Desi Ethnic Top",1799,"Clothing — Women","👚",None,4.2,11200,0),
        ("Fabindia Silk Saree",12000,"Clothing — Women","👘","Premium",4.8,2340,0),
        ("Puma Sports Bra",1499,"Clothing — Women","👙",None,4.4,8900,0),
        ("Marks & Spencer Trench Coat",8999,"Clothing — Women","🧥",None,4.6,2100,0),
        ("Libas Cotton Palazzo Set",2299,"Clothing — Women","👗","Budget Pick",4.3,13400,0),
        ("Anouk Embroidered Kurti",2199,"Clothing — Women","👚",None,4.4,10200,0),
        ("Femella Wrap Dress",3299,"Clothing — Women","👗","New",4.5,4320,1),
        ("Nike Women Training Tights",1999,"Clothing — Women","👖","Sports",4.5,7890,0),
        ("Forever New Maxi Dress",5499,"Clothing — Women","👗",None,4.6,3450,0),
        ("H&M Kids Cotton T-Shirt Set",699,"Clothing — Kids","👕",None,4.4,9870,0),
        ("Mothercare Dungaree Set",1499,"Clothing — Kids","👗","Best Seller",4.6,5430,0),
        ("Gini & Jony Jeans",1199,"Clothing — Kids","👖",None,4.3,4320,0),
        ("Hopscotch Ethnic Kurta",1299,"Clothing — Kids","👘",None,4.4,3210,0),
        ("Chicco Baby Romper Set",1799,"Clothing — Kids","🧸","New",4.7,2340,1),
        ("UCB Kids Hoodie",1999,"Clothing — Kids","🧥",None,4.5,4560,0),
        ("Disney Printed Pyjama Set",899,"Clothing — Kids","👕",None,4.3,6780,0),
        ("Firstcry Thermal Innerwear",1299,"Clothing — Kids","👕","Winter Wear",4.5,3210,0),
        ("Ray-Ban Aviator Sunglasses",9500,"Fashion Accessories","🕶️","Best Seller",4.7,8760,1),
        ("Hidesign Leather Handbag",12000,"Fashion Accessories","👜","Premium",4.6,2310,0),
        ("Titan Edge Watch",8500,"Fashion Accessories","⌚",None,4.5,5670,0),
        ("Fossil Leather Wallet",3499,"Fashion Accessories","👛",None,4.4,9870,0),
        ("Caprese Tote Bag",4999,"Fashion Accessories","👜",None,4.5,4320,0),
        ("Tommy Hilfiger Belt",2799,"Fashion Accessories","🪢",None,4.3,6780,0),
        ("Fastrack Sports Watch",2499,"Fashion Accessories","⌚","Budget Pick",4.2,12300,0),
        ("Baggit Backpack",3999,"Fashion Accessories","🎒",None,4.4,7890,0),
        ("Voyager Travel Trolley",7999,"Fashion Accessories","🧳",None,4.5,3210,0),
        ("Oakley Sports Sunglasses",11000,"Fashion Accessories","🕶️",None,4.6,2340,0),
        ("Michael Kors Wallet",6999,"Fashion Accessories","👛","Premium",4.7,1230,0),
        ("Aldo Sling Bag",4499,"Fashion Accessories","👜","New",4.4,3450,1),
        ("Nike Air Max 270",12999,"Footwear","👟","Best Seller",4.7,14300,1),
        ("Adidas Ultraboost 22",15000,"Footwear","👟",None,4.8,9870,0),
        ("Woodland Trekking Boots",6999,"Footwear","🥾",None,4.6,5430,0),
        ("Bata Formal Leather Shoes",3499,"Footwear","👞","Budget Pick",4.3,12400,0),
        ("Metro Block Heel Sandals",2299,"Footwear","👠",None,4.4,8900,0),
        ("Puma Suede Classic",7999,"Footwear","👟",None,4.5,7890,0),
        ("Khadim's Women Flats",1499,"Footwear","🩴",None,4.2,11200,0),
        ("Red Tape Oxford Shoes",4299,"Footwear","👞",None,4.4,6780,0),
        ("Crocs Classic Clog",3999,"Footwear","🩴","New",4.3,21000,1),
        ("VKC Comfort Slippers",599,"Footwear","🩴","Budget Pick",4.1,34500,0),
        ("New Balance 574",9999,"Footwear","👟",None,4.6,5670,0),
        ("Liberty Women Heels",2799,"Footwear","👠",None,4.3,4320,0),
        ("Sparx Running Shoes",2199,"Footwear","👟","Budget Pick",4.2,9870,0),
        ("Skechers Memory Foam",5999,"Footwear","👟",None,4.5,8760,0),
        ("Lakme Absolute Foundation",899,"Beauty & Skincare","💄","Best Seller",4.4,18900,1),
        ("Mamaearth Vitamin C Serum",1299,"Beauty & Skincare","🧴",None,4.5,23400,0),
        ("Forest Essentials Face Cream",3500,"Beauty & Skincare","🫧","Premium",4.7,4320,0),
        ("Maybelline Fit Me Concealer",699,"Beauty & Skincare","💄",None,4.3,19800,0),
        ("Dot & Key Sunscreen SPF 50",799,"Beauty & Skincare","🧴","New",4.6,21000,1),
        ("Plum Niacinamide Toner",699,"Beauty & Skincare","🧴",None,4.5,17800,0),
        ("Kama Ayurveda Rose Water",595,"Beauty & Skincare","🌹",None,4.6,14300,0),
        ("SUGAR Cosmetics Lip Kit",1299,"Beauty & Skincare","💋",None,4.4,12400,0),
        ("Biotique Bio Honey Gel",350,"Beauty & Skincare","🍯","Budget Pick",4.3,28900,0),
        ("Nykaa Skin Secrets Kit",1999,"Beauty & Skincare","🎁",None,4.5,8760,0),
        ("The Ordinary Hyaluronic Acid",699,"Beauty & Skincare","🧴",None,4.7,21000,1),
        ("Minimalist 10% Niacinamide",649,"Beauty & Skincare","🧴","New",4.6,23400,1),
        ("L'Oreal Revitalift Cream",1299,"Beauty & Skincare","🧴",None,4.5,9870,0),
        ("Neutrogena Moisturizer",799,"Beauty & Skincare","🧴",None,4.4,15600,0),
        ("Dyson Supersonic Hair Dryer",38000,"Hair Care","💨","Premium",4.8,3210,0),
        ("Tresemme Keratin Shampoo",399,"Hair Care","🧴","Best Seller",4.4,34500,0),
        ("Livon Hair Serum 100ml",249,"Hair Care","💧",None,4.3,45600,0),
        ("Wella Professionals Conditioner",749,"Hair Care","🧴",None,4.5,12300,0),
        ("Philips Hair Straightener",2499,"Hair Care","💇",None,4.5,9870,0),
        ("Indulekha Bringha Oil",449,"Hair Care","🌿",None,4.6,21000,0),
        ("L'Oreal Paris Hair Mask",649,"Hair Care","🎭",None,4.4,14300,0),
        ("Streax Hair Colour Dark Brown",299,"Hair Care","🎨","Budget Pick",4.2,19800,0),
        ("Pantene Pro-V Shampoo",449,"Hair Care","🧴",None,4.4,28900,0),
        ("Head & Shoulders Anti-Dandruff",399,"Hair Care","🧴",None,4.3,34500,0),
        ("Chanel No. 5 EDP",15000,"Fragrances","🌸","Premium",4.9,2340,0),
        ("Davidoff Cool Water EDT",2800,"Fragrances","💙",None,4.5,8760,0),
        ("Fogg Black Series Perfume",599,"Fragrances","🖤","Best Seller",4.3,45600,0),
        ("Skinn Titan Nude Perfume",1899,"Fragrances","🌺",None,4.4,6780,0),
        ("Park Avenue Gift Set",1299,"Fragrances","🎁",None,4.3,5670,0),
        ("Body Shop White Musk",1799,"Fragrances","🤍",None,4.5,4320,0),
        ("Denver Caliber Perfume",449,"Fragrances","🔵","Budget Pick",4.2,23400,0),
        ("Armaf Club de Nuit EDP",3999,"Fragrances","🌃",None,4.6,7890,1),
        ("Yardley English Lavender",699,"Fragrances","💜",None,4.4,9870,0),
        ("Engage Spice & Musk",399,"Fragrances","🟤","Budget Pick",4.2,19800,0),
        ("IKEA KALLAX Shelf Unit",8999,"Home & Living","🪣",None,4.5,6780,0),
        ("Sleepwell Ortho Pro Mattress",22000,"Home & Living","🛏️","Best Seller",4.7,4320,1),
        ("Bombay Dyeing Bedsheet",1299,"Home & Living","🛏️",None,4.4,12300,0),
        ("Solimo Curtains Set",799,"Home & Living","🪟","Budget Pick",4.2,9870,0),
        ("Urban Ladder Floor Lamp",4999,"Home & Living","💡",None,4.5,3210,0),
        ("Godrej Interio Bookshelf",12000,"Home & Living","📚",None,4.6,2340,0),
        ("Milton Thermosteel Bottle",899,"Home & Living","🍶","Best Seller",4.5,23400,0),
        ("Pepperfry Bar Stool",5499,"Home & Living","🪑",None,4.4,2100,0),
        ("IKEA Poang Armchair",14999,"Home & Living","🛋️","Premium",4.7,1890,0),
        ("Cello Wall Clock",799,"Home & Living","🕐",None,4.3,8760,0),
        ("Nilkamal Laundry Basket",999,"Home & Living","🧺",None,4.3,11200,0),
        ("Trident Bath Towel Set",1299,"Home & Living","🛁",None,4.4,14300,0),
        ("Borosil Vega Dinner Set",3499,"Home & Living","🍽️",None,4.5,5670,0),
        ("Colorbar Scented Candle Set",1499,"Home & Living","🕯️","New",4.6,4320,1),
        ("Prestige Induction Cooktop",3499,"Kitchen & Dining","🍳","Best Seller",4.5,14300,1),
        ("Hawkins Pressure Cooker 5L",2499,"Kitchen & Dining","🥘",None,4.6,18900,0),
        ("Borosil Glass Casserole Set",1899,"Kitchen & Dining","🫕",None,4.5,8760,0),
        ("Tupperware 4-Piece Set",1499,"Kitchen & Dining","🫙",None,4.5,12400,0),
        ("Pigeon Non-Stick Tawa",899,"Kitchen & Dining","🍳","Budget Pick",4.3,21000,0),
        ("WMF Cutlery Set 30-Piece",8999,"Kitchen & Dining","🍴","Premium",4.7,2340,0),
        ("Cello Mixer Grinder 750W",3299,"Kitchen & Dining","🫙",None,4.4,9870,0),
        ("Cuisinart Coffee Maker",12000,"Kitchen & Dining","☕",None,4.6,3210,0),
        ("Wonderchef Copper Bottle",999,"Kitchen & Dining","🫗",None,4.4,14300,0),
        ("Amazon Basics Knife Set",2499,"Kitchen & Dining","🔪",None,4.3,6780,0),
        ("Morphy Richards OTG 28L",5499,"Kitchen & Dining","🫙",None,4.5,8760,0),
        ("Nespresso Coffee Machine",18000,"Kitchen & Dining","☕","Premium",4.8,2100,0),
        ("LG 7kg Front Load Washer",48000,"Appliances","🫧","Best Seller",4.7,6780,1),
        ("Samsung 253L Double Door Fridge",28000,"Appliances","🧊",None,4.6,4320,0),
        ("Dyson V15 Detect Vacuum",55000,"Appliances","🌀","Premium",4.8,2340,0),
        ("Philips Air Fryer HD9200",6999,"Appliances","🍟","Best Seller",4.6,21000,1),
        ("Havells Juicer Mixer Grinder",2999,"Appliances","🧃",None,4.4,12300,0),
        ("Bajaj Room Heater",2499,"Appliances","🔥",None,4.3,8760,0),
        ("Eureka Forbes RO Purifier",16000,"Appliances","💧",None,4.6,5670,0),
        ("Hitachi 1.5T Split AC",38000,"Appliances","❄️",None,4.7,4320,0),
        ("Morphy Richards Toaster",2199,"Appliances","🍞","Budget Pick",4.3,9870,0),
        ("Whirlpool 5kg Washing Machine",28000,"Appliances","🫧","Budget Pick",4.4,5430,0),
        ("Blue Star Window AC 1.5T",32000,"Appliances","❄️",None,4.5,3210,0),
        ("IFB Microwave 30L",12000,"Appliances","📻",None,4.5,6780,0),
        ("Tata Tea Premium 500g",249,"Groceries & Food","🍵","Best Seller",4.5,45600,0),
        ("Nescafe Classic Coffee 200g",549,"Groceries & Food","☕",None,4.6,34500,0),
        ("Amul Ghee 1kg",699,"Groceries & Food","🫙",None,4.7,28900,0),
        ("Haldiram's Mixture 1kg",399,"Groceries & Food","🍿","Best Seller",4.5,39800,0),
        ("Patanjali Honey 1kg",399,"Groceries & Food","🍯",None,4.5,23400,0),
        ("Fortune Sunflower Oil 5L",1099,"Groceries & Food","🌻",None,4.4,19800,0),
        ("India Gate Basmati Rice 5kg",1199,"Groceries & Food","🍚",None,4.6,34500,0),
        ("MTR Ready to Eat Dal Makhani",149,"Groceries & Food","🫕","New",4.4,18900,1),
        ("Yoga Bar Protein Bar 6-Pack",599,"Groceries & Food","💪",None,4.5,12300,0),
        ("Organic India Tulsi Green Tea",399,"Groceries & Food","🌿",None,4.6,19800,0),
        ("Cadbury Celebrations Gift Box",1299,"Groceries & Food","🍫","Gift",4.7,14300,0),
        ("Nature Valley Granola Bars",499,"Groceries & Food","🌾",None,4.4,9870,0),
        ("Lay's Party Pack",399,"Groceries & Food","🥔",None,4.3,34500,0),
        ("Bourn Vita Health Drink 1kg",549,"Groceries & Food","🥤",None,4.4,23400,0),
        ("Himalaya Ashwagandha Tablets",399,"Health & Wellness","💊","Best Seller",4.6,18900,0),
        ("Omron BP Monitor HEM-7120",2199,"Health & Wellness","🩺",None,4.7,8760,0),
        ("Dr. Morepen Glucometer",1299,"Health & Wellness","🩸",None,4.5,6780,0),
        ("Ensure Nutrition Powder 400g",1499,"Health & Wellness","🥤",None,4.5,9870,0),
        ("Apollo Life Vitamin D3",599,"Health & Wellness","☀️",None,4.5,12300,0),
        ("Wellbeing Nutrition Probiotic",999,"Health & Wellness","🦠","New",4.6,5670,1),
        ("Beurer Heating Pad",2499,"Health & Wellness","🌡️",None,4.4,4320,0),
        ("Chicco Baby Thermometer",1299,"Health & Wellness","🌡️",None,4.6,3210,0),
        ("Patanjali Aloe Vera Juice 1L",299,"Health & Wellness","🌿","Budget Pick",4.4,21000,0),
        ("Medimix Ayurvedic Soap 6-Pack",299,"Health & Wellness","🧼",None,4.4,34500,0),
        ("HealthKart HK Vitals Multivitamin",799,"Health & Wellness","💊",None,4.5,9870,0),
        ("Dr. Vaidya's Immunity Kit",1499,"Health & Wellness","🌿","New",4.6,4320,1),
        ("Boldfit Yoga Mat",999,"Sports & Fitness","🧘","Best Seller",4.5,19800,1),
        ("Cosco Football Size 5",799,"Sports & Fitness","⚽",None,4.4,12300,0),
        ("Vector X Cricket Bat",4999,"Sports & Fitness","🏏",None,4.5,8760,0),
        ("Nivia Badminton Racket Set",1999,"Sports & Fitness","🏸",None,4.4,9870,0),
        ("Yonex VCORE Tennis Racket",14000,"Sports & Fitness","🎾","Premium",4.7,2340,0),
        ("Protoner Adjustable Dumbbell 20kg",3499,"Sports & Fitness","🏋️",None,4.5,6780,0),
        ("Adidas Cycling Gloves",999,"Sports & Fitness","🚴",None,4.3,4320,0),
        ("Swimming Goggles Speedo",1499,"Sports & Fitness","🏊",None,4.5,5670,0),
        ("Decathlon Camping Tent 2P",7999,"Sports & Fitness","⛺",None,4.6,3210,0),
        ("NutriTech Whey Protein 1kg",2999,"Sports & Fitness","💪",None,4.5,12300,0),
        ("Cosco Basketball",1299,"Sports & Fitness","🏀",None,4.4,7890,0),
        ("Nivia Gym Gloves",699,"Sports & Fitness","🥊","Budget Pick",4.3,9870,0),
        ("Fitkit FK500 Cycle",18000,"Sports & Fitness","🚲",None,4.6,2340,1),
        ("Reebok Resistance Bands Set",1499,"Sports & Fitness","🎗️",None,4.4,8760,0),
        ("Atomic Habits — James Clear",499,"Books & Stationery","📖","Best Seller",4.8,45600,0),
        ("Rich Dad Poor Dad",349,"Books & Stationery","📖",None,4.7,39800,0),
        ("NCERT Class 12 Complete Set",1500,"Books & Stationery","📚",None,4.6,12300,0),
        ("Casio Scientific Calculator",1299,"Books & Stationery","🔢","Best Seller",4.7,23400,0),
        ("Camlin Colour Kit 48 Shades",699,"Books & Stationery","🎨",None,4.5,14300,0),
        ("Parker Frontier Ball Pen",450,"Books & Stationery","🖊️",None,4.6,19800,0),
        ("Luxor Whiteboard Marker Set",299,"Books & Stationery","✏️","Budget Pick",4.3,28900,0),
        ("Classmate Spiral Notebook 6-Pack",599,"Books & Stationery","📓",None,4.5,34500,0),
        ("The Alchemist — Paulo Coelho",299,"Books & Stationery","📖",None,4.7,21000,0),
        ("Oxford Dictionary",899,"Books & Stationery","📚",None,4.6,9870,0),
        ("LEGO City Police Station",8999,"Toys & Games","🏗️","Best Seller",4.8,8760,1),
        ("Hot Wheels 20-Car Pack",1999,"Toys & Games","🚗",None,4.6,12300,0),
        ("Hasbro Monopoly Classic",1299,"Toys & Games","🎲",None,4.7,19800,0),
        ("Barbie Dreamhouse",12999,"Toys & Games","🏠",None,4.7,6780,0),
        ("Remote Control Car Maisto",3499,"Toys & Games","🏎️",None,4.5,9870,0),
        ("Funskool Scrabble",1199,"Toys & Games","🔤",None,4.6,14300,0),
        ("Play-Doh Mega Fun Factory",2499,"Toys & Games","🎭","New",4.6,8760,1),
        ("PlayStation DualSense Controller",6999,"Toys & Games","🎮","Gaming",4.8,12300,0),
        ("Nerf Elite Blaster",2299,"Toys & Games","🎯",None,4.5,9870,0),
        ("UNO Card Game",499,"Toys & Games","🃏",None,4.7,28900,0),
        ("IKEA HEMNES Bed Frame",25000,"Furniture","🛏️","Best Seller",4.7,4320,0),
        ("Nilkamal 4-Seater Dining Table",18000,"Furniture","🍽️",None,4.5,3210,0),
        ("Urban Ladder Sofa 3-Seater",45000,"Furniture","🛋️","Premium",4.8,2340,0),
        ("Godrej Interio Wardrobe",32000,"Furniture","🚪",None,4.6,2100,0),
        ("Durian Office Chair",12000,"Furniture","🪑",None,4.6,5670,0),
        ("Pepperfry Study Table",8999,"Furniture","📚",None,4.5,4320,0),
        ("IKEA KALLAX TV Unit",12000,"Furniture","📺",None,4.6,3450,0),
        ("Wooden Street Queen Bed",22000,"Furniture","🛏️",None,4.7,2890,0),
        ("Nilkamal Plastic Chair Set 4",3999,"Furniture","🪑","Budget Pick",4.3,8760,0),
        ("FabIndia Teak Wood Shelf",6999,"Furniture","📚",None,4.5,2340,0),
        ("Pedigree Adult Dry Dog Food 3kg",1299,"Pet Supplies","🐕","Best Seller",4.6,12300,0),
        ("Whiskas Cat Food Variety Pack",999,"Pet Supplies","🐈",None,4.5,9870,0),
        ("Trixie Dog Leash & Collar Set",799,"Pet Supplies","🦮",None,4.4,8760,0),
        ("Furhaven Orthopedic Pet Bed",2999,"Pet Supplies","🛏️",None,4.5,4320,0),
        ("Interactive Cat Feather Toy",449,"Pet Supplies","🐾","Budget Pick",4.3,14300,0),
        ("Royal Canin Cat Food 2kg",2499,"Pet Supplies","🐈",None,4.7,6780,0),
        ("Pet Grooming Brush",699,"Pet Supplies","🐕",None,4.4,9870,0),
        ("Aquarium Starter Kit",3999,"Pet Supplies","🐟","New",4.5,2340,1),
        ("Michelin Car Tyre 185/65 R15",5500,"Automotive","🛞","Best Seller",4.7,3210,0),
        ("Bosch Car Battery 65Ah",7999,"Automotive","🔋",None,4.6,2340,0),
        ("3M Car Polish Kit",999,"Automotive","✨",None,4.4,8760,0),
        ("Vega Helmet ISI Certified",2499,"Automotive","⛑️",None,4.5,12300,0),
        ("Amaron Car Battery 55Ah",5999,"Automotive","🔋",None,4.6,4320,0),
        ("Instaauto Dash Cam Full HD",5999,"Automotive","📷","New",4.5,6780,1),
        ("Meguiar's Car Wax",999,"Automotive","🚘",None,4.4,9870,0),
        ("K&N Air Filter",3500,"Automotive","💨",None,4.5,3210,0),
        ("Garmin GPS Navigator",9999,"Automotive","🗺️",None,4.6,2340,0),
        ("Car Vacuum Cleaner",2499,"Automotive","🌀","Budget Pick",4.3,8760,0),
        ("Garden Hose 15m",1499,"Outdoor & Garden","🌿",None,4.4,6780,0),
        ("BBQ Grill Set Portable",4999,"Outdoor & Garden","🔥","Best Seller",4.6,4320,1),
        ("Camping Sleeping Bag",2999,"Outdoor & Garden","⛺",None,4.5,3210,0),
        ("Gardening Tool Kit 5-Piece",1299,"Outdoor & Garden","🌱",None,4.4,8760,0),
        ("Solar Garden Lights 6-Pack",1999,"Outdoor & Garden","☀️","New",4.5,5670,1),
        ("Outdoor Hammock",3499,"Outdoor & Garden","🌳",None,4.6,2340,0),
        ("Bird Feeder Hanging",899,"Outdoor & Garden","🐦",None,4.5,4320,0),
        ("Potting Mix Soil 10kg",699,"Outdoor & Garden","🪴","Budget Pick",4.3,9870,0),
        ("Pampers Premium Care Diapers L",899,"Baby & Maternity","🍼","Best Seller",4.7,21000,0),
        ("Mee Mee Baby Stroller",7999,"Baby & Maternity","🍼",None,4.6,4320,0),
        ("Fisher-Price Baby Gym",3499,"Baby & Maternity","🧸",None,4.7,5670,0),
        ("Himalaya Baby Lotion 400ml",449,"Baby & Maternity","🍼",None,4.6,14300,0),
        ("Wahl Baby Hair Trimmer",1999,"Baby & Maternity","✂️",None,4.5,8760,0),
        ("NUK Baby Bottle 3-Pack",1299,"Baby & Maternity","🍼",None,4.5,9870,0),
        ("Chicco Baby Monitor",6999,"Baby & Maternity","📡","New",4.7,2340,1),
        ("Summer Infant Baby Swing",8999,"Baby & Maternity","🎡",None,4.6,1890,0),
        ("Tanishq Gold Mangalsutra",28000,"Jewellery","💍","Best Seller",4.9,1230,0),
        ("Voylla Silver Earrings Set",999,"Jewellery","💎","Budget Pick",4.4,12300,0),
        ("Malabar Gold Bangles",45000,"Jewellery","💍","Premium",4.9,890,0),
        ("Zaveri Pearls Necklace Set",1499,"Jewellery","📿",None,4.5,8760,0),
        ("BlueStone Diamond Ring",35000,"Jewellery","💍","Premium",4.8,1560,1),
        ("Pipa Bella Fashion Earrings",799,"Jewellery","💎",None,4.4,9870,0),
        ("Caratlane Gold Chain",15000,"Jewellery","📿",None,4.7,2340,0),
        ("Johareez Kundan Necklace",3499,"Jewellery","📿",None,4.5,4320,0),
        ("Yamaha Acoustic Guitar F310",9999,"Musical Instruments","🎸","Best Seller",4.7,4320,1),
        ("Casio CT-S300 Keyboard",7999,"Musical Instruments","🎹",None,4.6,3210,0),
        ("Pearl Export Drum Kit",45000,"Musical Instruments","🥁","Premium",4.8,890,0),
        ("Harman Kardon Ukulele",3999,"Musical Instruments","🪗",None,4.5,2340,0),
        ("Banjira Tabla Set",4999,"Musical Instruments","🪘","Traditional",4.7,1890,0),
        ("Fender Squier Guitar",25000,"Musical Instruments","🎸",None,4.7,1230,0),
        ("Cajon Percussion Box",5999,"Musical Instruments","🥁",None,4.6,1560,0),
        ("Hohner Harmonica",1499,"Musical Instruments","🎵","Budget Pick",4.4,4320,0),
        ("HP LaserJet Pro Printer",18000,"Stationery & Office","🖨️","Best Seller",4.6,5670,0),
        ("Epson L3252 InkTank Printer",13000,"Stationery & Office","🖨️",None,4.5,8760,0),
        ("Wacom Drawing Tablet",7999,"Stationery & Office","✏️",None,4.6,3210,0),
        ("AmazonBasics Office Chair",6999,"Stationery & Office","🪑","Budget Pick",4.3,9870,0),
        ("Fellowes Shredder",8999,"Stationery & Office","📄",None,4.5,2340,0),
        ("Navneet A4 Ruled Reams",699,"Stationery & Office","📄","Budget Pick",4.4,19800,0),
        ("Stapler Set with Pins",399,"Stationery & Office","📌",None,4.3,23400,0),
        ("Filing Cabinet 3-Drawer",12000,"Stationery & Office","🗄️",None,4.5,1890,0),
        ("American Tourister Trolley 68cm",6999,"Travel & Luggage","🧳","Best Seller",4.6,8760,1),
        ("Safari Polycarbonate Trolley",8999,"Travel & Luggage","🧳",None,4.5,6780,0),
        ("Wildcraft Backpack 45L",3499,"Travel & Luggage","🎒",None,4.5,9870,0),
        ("Samsonite Carry-on Bag",12000,"Travel & Luggage","🧳","Premium",4.7,4320,0),
        ("Travel Organizer Set",1499,"Travel & Luggage","🪣",None,4.4,12300,0),
        ("Neck Pillow Memory Foam",999,"Travel & Luggage","😴","Best Seller",4.5,18900,0),
        ("Passport Holder Leather",799,"Travel & Luggage","📋",None,4.4,14300,0),
        ("Cabin Crew Rolling Bag",5999,"Travel & Luggage","🎒",None,4.5,5670,0),
    ]


    conn.executemany(
        "INSERT INTO products (name,price,category,icon,badge,rating,reviews,trending) VALUES(?,?,?,?,?,?,?,?)",
        products
    )
    conn.commit(); conn.close()

# ═══════════════════════════════════════════════════════════
# AUTH
# ═══════════════════════════════════════════════════════════
@app.route("/", methods=["GET","POST"])
def login():
    if request.method == "POST":
        identifier = request.form.get("username","").strip()
        p = request.form.get("password","")

        # Basic brute-force protection: track failed attempts in session
        fails = session.get("login_fails", 0)
        if fails >= 5:
            return render_template("login.html", error="Too many failed attempts. Please wait a few minutes.")

        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? OR email=? OR phone=?",
            (identifier, identifier.lower(), identifier)
        ).fetchone()
        conn.close()
        if user and check_password_hash(user["password"], p):
            session.clear()
            session["user"]    = user["username"]
            session["user_id"] = user["id"]
            session["role"]    = user["role"] or "customer"
            if (user["role"] or "customer") == "admin":
                session["is_admin"] = True
                return redirect(url_for("admin_dashboard"))
            return redirect(url_for("home"))
        session["login_fails"] = fails + 1
        return render_template("login.html", error="Incorrect credentials. Try username, email, or phone.")
    return render_template("login.html", error=None)

# Admin invite code — set via ADMIN_INVITE_CODE env var
ADMIN_INVITE_CODE = os.environ.get("ADMIN_INVITE_CODE", "NEXACART_ADMIN_2025")

@app.route("/register", methods=["GET","POST"])
def register():
    import re
    error     = None
    form_data = {}
    if request.method == "POST":
        u            = request.form.get("username","").strip()
        pw           = request.form.get("password","").strip()
        pw2          = request.form.get("password2","").strip()
        email        = request.form.get("email","").strip().lower()
        country_code = request.form.get("country_code","+91").strip()
        phone_raw    = request.form.get("phone","").strip()
        phone        = re.sub(r"[^0-9]","", phone_raw)
        account_type = request.form.get("account_type","customer")
        invite_code  = request.form.get("invite_code","").strip()

        form_data = {"username":u,"email":email,"country_code":country_code,
                     "phone":phone_raw,"account_type":account_type}

        # Validate account type
        if account_type not in ("customer","admin"):
            account_type = "customer"

        # Admin signup requires valid invite code
        if account_type == "admin" and invite_code != ADMIN_INVITE_CODE:
            error = "Invalid admin invite code. Contact the system administrator."
        elif not u:
            error = "Username is required."
        elif len(u) < 3:
            error = "Username must be at least 3 characters."
        elif not pw:
            error = "Password is required."
        elif len(pw) < 6:
            error = "Password must be at least 6 characters."
        elif pw != pw2:
            error = "Passwords do not match."
        elif not email and not phone:
            error = "Please provide at least one: email address or mobile number."
        elif email and not re.match(r'^[\w.+\-]+@[\w\-]+\.[\w.]+$', email):
            error = "Please enter a valid email address."
        elif phone and len(phone) < 7:
            error = "Please enter a valid mobile number (min 7 digits)."
        else:
            conn = get_db()
            if conn.execute("SELECT id FROM users WHERE username=?", (u,)).fetchone():
                error = "This username is already taken."
            elif email and conn.execute("SELECT id FROM users WHERE email=?", (email,)).fetchone():
                error = "An account with this email already exists."
            else:
                try:
                    phone_full = (country_code + phone) if phone else None
                    conn.execute(
                        "INSERT INTO users(username,password,email,phone,country_code,is_verified,role) VALUES(?,?,?,?,?,1,?)",
                        (u, generate_password_hash(pw), email or None, phone_full, country_code, account_type)
                    )
                    conn.commit(); conn.close()
                    return redirect(url_for("login"))
                except Exception as ex:
                    error = "Registration failed. Please try again."
            conn.close()

    return render_template("register.html", error=error, form_data=form_data)

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ═══════════════════════════════════════════════════════════
# HOME
# ═══════════════════════════════════════════════════════════
@app.route("/home")
@login_required
def home():
    uid        = get_user_id()
    season     = get_season()
    active_cat = request.args.get("cat","")
    min_price  = request.args.get("min_price","").strip()
    max_price  = request.args.get("max_price","").strip()
    min_rating = request.args.get("min_rating","").strip()
    brands_sel = request.args.getlist("brand")
    sort_f     = request.args.get("sort_f","rating")
    conn = get_db()

    trending = conn.execute("SELECT * FROM products WHERE trending=1 ORDER BY rating DESC,reviews DESC LIMIT 12").fetchall()
    sc = SEASON_PRODUCTS.get(season,[])
    season_picks = conn.execute(f"SELECT * FROM products WHERE category IN ({','.join('?'*len(sc))}) ORDER BY rating DESC LIMIT 8", sc).fetchall() if sc else []
    deals_pool = conn.execute("SELECT * FROM products WHERE badge IS NOT NULL ORDER BY reviews DESC LIMIT 20").fetchall()
    deals = random.sample(list(deals_pool), min(6,len(deals_pool)))
    cat_counts = {r["category"]:r["cnt"] for r in conn.execute("SELECT category,COUNT(*) as cnt FROM products GROUP BY category").fetchall()}

    # Recently viewed
    recently = []
    if uid:
        rv_ids = [r["product_id"] for r in conn.execute("SELECT product_id FROM recently_viewed WHERE user_id=? ORDER BY viewed_at DESC LIMIT 8",(uid,)).fetchall()]
        if rv_ids:
            recently = [conn.execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone() for pid in rv_ids]
            recently = [r for r in recently if r]

    cat_products=[]; all_brands=[]; price_range={}
    if active_cat:
        base = conn.execute("SELECT * FROM products" + (" WHERE category=?" if active_cat!="All" else ""),
                            (active_cat,) if active_cat!="All" else ()).fetchall()
        all_brands = sorted({p["name"].split()[0] for p in base})
        prices = [p["price"] for p in base]
        price_range = {"min":int(min(prices)) if prices else 0,"max":int(max(prices)) if prices else 100000}
        filt = list(base)
        if min_price:
            try: filt=[p for p in filt if p["price"]>=float(min_price)]
            except: pass
        if max_price:
            try: filt=[p for p in filt if p["price"]<=float(max_price)]
            except: pass
        if min_rating:
            try: filt=[p for p in filt if p["rating"]>=float(min_rating)]
            except: pass
        if brands_sel: filt=[p for p in filt if p["name"].split()[0] in brands_sel]
        sk = {"rating":lambda p:(-p["rating"],-p["reviews"]),"popular":lambda p:-p["reviews"],
              "price_asc":lambda p:p["price"],"price_desc":lambda p:-p["price"],"name":lambda p:p["name"]}
        filt.sort(key=sk.get(sort_f,sk["rating"]))
        cat_products = filt[:48]

    cart_count = get_cart_count(uid) if uid else 0
    conn.close()
    return render_template("home.html", username=session["user"], season=season,
        trending=trending, season_picks=season_picks, deals=deals,
        recently=recently, cat_products=cat_products, active_cat=active_cat,
        cat_meta=CATEGORY_META, super_cats=SUPER_CATS, cat_counts=cat_counts,
        all_brands=all_brands, price_range=price_range,
        min_price=min_price, max_price=max_price, min_rating=min_rating,
        brands_sel=brands_sel, sort_f=sort_f,
        cart_count=cart_count)

# ═══════════════════════════════════════════════════════════
# PRODUCTS (with pagination + filters)
# ═══════════════════════════════════════════════════════════
@app.route("/products")
@login_required
def products():
    uid        = get_user_id()
    active_cat = request.args.get("category","All")
    search_q   = request.args.get("q","").strip()
    sort_by    = request.args.get("sort","default")
    page       = max(1, request.args.get("page",1,type=int))
    min_price  = request.args.get("min_price","")
    max_price  = request.args.get("max_price","")
    min_rating = request.args.get("min_rating","")
    brands_sel = request.args.getlist("brand")

    order_map = {"price_asc":"price ASC","price_desc":"price DESC",
                 "rating":"rating DESC","popular":"reviews DESC"}
    order_clause = order_map.get(sort_by, "category,name")

    conn = get_db()
    existing   = {r["category"] for r in conn.execute("SELECT DISTINCT category FROM products").fetchall()}
    categories = [c for c in CATEGORY_META if c in existing]

    # Base query
    where=[]; params=[]
    if search_q:
        where.append("(name ILIKE ? OR category ILIKE ?)")
        params+=[f"%{search_q}%",f"%{search_q}%"]
        active_cat="All"
    elif active_cat!="All":
        where.append("category=?"); params.append(active_cat)
    if min_price:
        try: where.append("price>=?"); params.append(float(min_price))
        except: pass
    if max_price:
        try: where.append("price<=?"); params.append(float(max_price))
        except: pass
    if min_rating:
        try: where.append("rating>=?"); params.append(float(min_rating))
        except: pass
    if brands_sel:
        ph=",".join("?"*len(brands_sel))
        where.append(f"SUBSTR(name,1,STRPOS(name||' ',' ')-1) IN ({ph})")
        params+=brands_sel

    w = "WHERE "+" AND ".join(where) if where else ""
    total_count = conn.execute(f"SELECT COUNT(*) FROM products {w}", params).fetchone()[0]
    total_pages = max(1,(total_count+PER_PAGE-1)//PER_PAGE)
    page = min(page,total_pages)
    offset = (page-1)*PER_PAGE

    product_list = conn.execute(
        f"SELECT * FROM products {w} ORDER BY {order_clause} LIMIT {PER_PAGE} OFFSET {offset}", params
    ).fetchall()

    # Brands for filter sidebar
    brand_rows = conn.execute(
        f"SELECT DISTINCT SUBSTR(name,1,STRPOS(name||' ',' ')-1) as brand FROM products {w} ORDER BY brand", params
    ).fetchall()
    all_brands = [r["brand"] for r in brand_rows]

    # Price range
    pr = conn.execute(f"SELECT MIN(price),MAX(price) FROM products {w}", params).fetchone()
    price_range = {"min":int(pr[0] or 0),"max":int(pr[1] or 100000)}

    # Wishlist set
    wish_ids = set()
    if uid:
        wish_ids = {r["product_id"] for r in conn.execute("SELECT product_id FROM wishlist WHERE user_id=?",(uid,)).fetchall()}

    conn.close()
    return render_template("products.html",
        products=product_list, categories=categories,
        active_cat=active_cat, search_q=search_q, sort_by=sort_by,
        super_cats=SUPER_CATS, cat_meta=CATEGORY_META,
        username=session["user"], cart_count=get_cart_count(uid),
        total_count=total_count, page=page, total_pages=total_pages,
        all_brands=all_brands, price_range=price_range,
        min_price=min_price, max_price=max_price, min_rating=min_rating,
        brands_sel=brands_sel, wish_ids=wish_ids,
        get_img=get_product_image)

# ═══════════════════════════════════════════════════════════
# PRODUCT DETAIL
# ═══════════════════════════════════════════════════════════
@app.route("/product/<int:pid>", methods=["GET","POST"])
@login_required
def product_detail(pid):
    uid  = get_user_id()
    conn = get_db()
    p    = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    if not p: conn.close(); return redirect(url_for("products"))

    track_recently_viewed(uid, pid)

    # Save review
    review_msg = None
    if request.method=="POST" and "rating" in request.form:
        try:
            rv = int(request.form["rating"])
            ti = request.form.get("review_title","").strip()[:120]
            bd = request.form.get("review_body","").strip()[:1000]
            conn.execute("""INSERT INTO reviews(product_id,user_id,rating,title,body) VALUES(?,?,?,?,?)
                         ON CONFLICT (product_id,user_id) DO UPDATE SET
                         rating=EXCLUDED.rating,title=EXCLUDED.title,body=EXCLUDED.body,created_at=NOW()""",
                         (pid,uid,rv,ti,bd))
            # Update product aggregate rating
            agg = conn.execute("SELECT AVG(rating) as avg, COUNT(*) as cnt FROM reviews WHERE product_id=?", (pid,)).fetchone()
            conn.execute("UPDATE products SET rating=?,reviews=? WHERE id=?",
                         (round(agg["avg"],1), agg["cnt"], pid))
            conn.commit()
            review_msg = "✅ Review submitted! Thank you."
        except Exception as e:
            review_msg = f"❌ Could not save review: {e}"

    related   = conn.execute("SELECT * FROM products WHERE category=? AND id!=? ORDER BY rating DESC LIMIT 6",(p["category"],pid)).fetchall()
    user_revs = conn.execute("SELECT r.*,u.username FROM reviews r JOIN users u ON r.user_id=u.id WHERE r.product_id=? ORDER BY r.created_at DESC LIMIT 20",(pid,)).fetchall()
    rating_dist = {i: conn.execute("SELECT COUNT(*) FROM reviews WHERE product_id=? AND rating=?",(pid,i)).fetchone()[0] for i in range(5,0,-1)}
    total_rev_count = sum(rating_dist.values())
    already_reviewed = conn.execute("SELECT id FROM reviews WHERE product_id=? AND user_id=?",(pid,uid)).fetchone() is not None
    in_wishlist = conn.execute("SELECT id FROM wishlist WHERE user_id=? AND product_id=?",(uid,pid)).fetchone() is not None

    discount_pct   = 10 + (pid%4)*10
    original_price = round(p["price"]/(1-discount_pct/100))
    variants       = get_customization_options(p["category"], p["name"])
    features       = _get_product_features(p["category"], p["name"])
    conn.close()
    product_images = get_product_images(pid)
    return render_template("product_detail.html",
        p=p, related=related, user_revs=user_revs, rating_dist=rating_dist,
        total_rev_count=total_rev_count, already_reviewed=already_reviewed,
        discount_pct=discount_pct, original_price=original_price,
        variants=variants, features=features, in_wishlist=in_wishlist,
        review_msg=review_msg, product_images=product_images,
        username=session["user"], cart_count=get_cart_count(uid),
        get_img=get_product_image)

# ═══════════════════════════════════════════════════════════
# CART (database-backed)
# ═══════════════════════════════════════════════════════════
@app.route("/add_to_cart/<int:pid>", methods=["GET","POST"])
@login_required
def add_to_cart(pid):
    uid     = get_user_id()
    variant = request.form.get("variant","") if request.method=="POST" else request.args.get("variant","")
    qty     = int(request.form.get("qty",1))
    conn = get_db()
    existing = conn.execute("SELECT id,quantity FROM cart WHERE user_id=? AND product_id=? AND variant=?",(uid,pid,variant)).fetchone()
    if existing:
        conn.execute("UPDATE cart SET quantity=? WHERE id=?",(min(existing["quantity"]+qty,10),existing["id"]))
    else:
        conn.execute("INSERT INTO cart(user_id,product_id,quantity,variant) VALUES(?,?,?,?)",(uid,pid,qty,variant))
    conn.commit(); conn.close()
    flash("✅ Added to cart!")
    ref = request.referrer or url_for("products")
    return redirect(ref)

@app.route("/remove_from_cart/<int:cart_id>")
@login_required
def remove_from_cart(cart_id):
    uid = get_user_id()
    conn = get_db()
    conn.execute("DELETE FROM cart WHERE id=? AND user_id=?",(cart_id,uid))
    conn.commit(); conn.close()
    return redirect(url_for("cart"))

@app.route("/update_cart/<int:cart_id>", methods=["POST"])
@login_required
def update_cart(cart_id):
    uid = get_user_id()
    qty = int(request.form.get("qty",1))
    conn = get_db()
    if qty<=0: conn.execute("DELETE FROM cart WHERE id=? AND user_id=?",(cart_id,uid))
    else:      conn.execute("UPDATE cart SET quantity=? WHERE id=? AND user_id=?",(min(qty,10),cart_id,uid))
    conn.commit(); conn.close()
    return redirect(url_for("cart"))

@app.route("/cart", methods=["GET","POST"])
@login_required
def cart():
    uid = get_user_id()
    promo_msg=None; promo_error=None
    applied_code = session.get("promo_code",""); discount_pct = session.get("discount_pct",0)
    if request.method=="POST":
        code = request.form.get("promo_code","").strip().upper()
        if code in PROMO_CODES:
            session["promo_code"]=code; session["discount_pct"]=PROMO_CODES[code]
            applied_code=code; discount_pct=PROMO_CODES[code]
            promo_msg=f'"{code}" applied — {PROMO_CODES[code]}% off!'
        else: promo_error="Invalid promo code."
    items = get_cart_items(uid)
    subtotal = sum(i["price"]*i["quantity"] for i in items)
    flash_msgs = session.pop("_flashes",None)
    return render_template("cart.html", items=items, subtotal=subtotal,
        discount_pct=discount_pct, applied_code=applied_code,
        promo_msg=promo_msg, promo_error=promo_error,
        available_promos=PROMO_CODES,
        username=session["user"], cart_count=get_cart_count(uid),
        **calc_totals(subtotal,discount_pct))

@app.route("/remove_promo")
@login_required
def remove_promo():
    session.pop("promo_code",None); session.pop("discount_pct",None)
    return redirect(url_for("cart"))

# ═══════════════════════════════════════════════════════════
# WISHLIST (database-backed)
# ═══════════════════════════════════════════════════════════
@app.route("/wishlist")
@login_required
def wishlist():
    uid = get_user_id()
    conn = get_db()
    items = conn.execute("""SELECT p.* FROM wishlist w JOIN products p ON w.product_id=p.id
        WHERE w.user_id=? ORDER BY w.added_at DESC""", (uid,)).fetchall()
    conn.close()
    return render_template("wishlist.html", items=items,
        username=session["user"], cart_count=get_cart_count(uid),
        wishlist_count=len(items))

@app.route("/toggle_wishlist/<int:pid>")
@login_required
def toggle_wishlist(pid):
    uid = get_user_id()
    conn = get_db()
    exists = conn.execute("SELECT id FROM wishlist WHERE user_id=? AND product_id=?",(uid,pid)).fetchone()
    if exists: conn.execute("DELETE FROM wishlist WHERE user_id=? AND product_id=?",(uid,pid))
    else:      conn.execute("INSERT INTO wishlist(user_id,product_id) VALUES(?,?) ON CONFLICT DO NOTHING",(uid,pid))
    conn.commit(); conn.close()
    return redirect(request.referrer or url_for("wishlist"))

# ═══════════════════════════════════════════════════════════
# CHECKOUT + ORDERS
# ═══════════════════════════════════════════════════════════
@app.route("/checkout", methods=["GET","POST"])
@login_required
def checkout():
    uid = get_user_id()
    items = get_cart_items(uid)
    if not items: return redirect(url_for("cart"))
    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    conn.close()
    subtotal     = sum(i["price"]*i["quantity"] for i in items)
    discount_pct = session.get("discount_pct",0)
    applied_code = session.get("promo_code","")
    t            = calc_totals(subtotal,discount_pct)
    return render_template("checkout.html", items=items, subtotal=subtotal,
        discount_pct=discount_pct, applied_code=applied_code,
        amount_paise=int(t["grand_total"]*100),
        user=user, username=session["user"],
        stripe_pub_key=STRIPE_PUBLISHABLE_KEY,
        cart_count=get_cart_count(uid), **t)

@app.route("/payment_success", methods=["GET","POST"])
@login_required
def payment_success():
    uid   = get_user_id()
    items = get_cart_items(uid)
    conn  = get_db()
    subtotal     = sum(i["price"]*i["quantity"] for i in items)
    discount_pct = session.get("discount_pct",0)
    applied_code = session.get("promo_code","")
    t            = calc_totals(subtotal, discount_pct)
    ref = f"NXC-{random.randint(100000,999999)}"
    user = conn.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    # Save order
    order_id = conn.execute("INSERT INTO orders(user_id,order_ref,total,subtotal,discount_amt,gst_amt,promo_code,address,city,pincode,payment_method) VALUES(?,?,?,?,?,?,?,?,?,?,?) RETURNING id",
        (uid,ref,t["grand_total"],subtotal,t["discount_amt"],t["gst_amt"],applied_code,
         user["address"] or "",user["city"] or "",user["pincode"] or "","Stripe/Card")).fetchone()[0]
    for i in items:
        conn.execute("INSERT INTO order_items(order_id,product_id,name,price,quantity,variant) VALUES(?,?,?,?,?,?)",
            (order_id,i["id"],i["name"],i["price"],i["quantity"],i["variant"]))
    conn.execute("DELETE FROM cart WHERE user_id=?",(uid,))
    conn.commit(); conn.close()
    session.pop("promo_code",None); session.pop("discount_pct",None)
    return render_template("success.html", username=session["user"],
        order_ref=ref, total=t["grand_total"], items=items,
        promo=applied_code, cart_count=0)

# ═══════════════════════════════════════════════════════════
# ORDERS HISTORY
# ═══════════════════════════════════════════════════════════
@app.route("/orders")
@login_required
def orders():
    uid = get_user_id()
    conn = get_db()
    order_list = conn.execute("SELECT * FROM orders WHERE user_id=? ORDER BY created_at DESC",(uid,)).fetchall()
    # Attach items to each order
    orders_with_items = []
    for o in order_list:
        its = conn.execute("SELECT * FROM order_items WHERE order_id=?",(o["id"],)).fetchall()
        orders_with_items.append({"order":o,"items":its})
    conn.close()
    return render_template("orders.html", orders=orders_with_items,
        username=session["user"], cart_count=get_cart_count(uid))

# ═══════════════════════════════════════════════════════════
# PROFILE
# ═══════════════════════════════════════════════════════════
@app.route("/profile", methods=["GET","POST"])
@login_required
def profile():
    uid=get_user_id(); conn=get_db(); msg=None
    if request.method=="POST":
        action=request.form.get("action")
        if action=="update_info":
            conn.execute("UPDATE users SET email=?,phone=?,address=?,city=?,pincode=? WHERE id=?",
                (request.form.get("email",""),request.form.get("phone",""),
                 request.form.get("address",""),request.form.get("city",""),
                 request.form.get("pincode",""),uid))
            conn.commit(); msg="Profile updated!"
        elif action=="change_password":
            user=conn.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
            old,new,conf=request.form.get("old_password",""),request.form.get("new_password",""),request.form.get("confirm_password","")
            if not check_password_hash(user["password"],old): msg="error:Current password incorrect."
            elif new!=conf: msg="error:Passwords do not match."
            elif len(new)<6: msg="error:Min 6 characters."
            else:
                conn.execute("UPDATE users SET password=? WHERE id=?",(generate_password_hash(new),uid))
                conn.commit(); msg="Password changed!"
    user=conn.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    if not user:
        conn.close()
        session.clear()
        return redirect(url_for("login"))
    order_count=conn.execute("SELECT COUNT(*) FROM orders WHERE user_id=?",(uid,)).fetchone()[0]
    wish_count=conn.execute("SELECT COUNT(*) FROM wishlist WHERE user_id=?",(uid,)).fetchone()[0]
    conn.close()
    return render_template("profile.html",user=user,msg=msg,
        username=session["user"],cart_count=get_cart_count(uid),
        order_count=order_count,wish_count=wish_count)

# ═══════════════════════════════════════════════════════════
# REWARDS / GIFTS / NOTIFICATIONS / HELP / STATIC PAGES
# ═══════════════════════════════════════════════════════════
@app.route("/rewards")
@login_required
def rewards():
    uid=get_user_id(); conn=get_db()
    total_spent=conn.execute("SELECT COALESCE(SUM(total),0) FROM orders WHERE user_id=?",(uid,)).fetchone()[0]
    reward_points=int(total_spent/100); conn.close()
    return render_template("rewards.html",username=session["user"],cart_count=get_cart_count(uid),
        reward_points=reward_points,total_spent=total_spent,promo_codes=PROMO_CODES)

@app.route("/gift-cards")
@login_required
def gift_cards():
    uid=get_user_id()
    return render_template("gift_cards.html",username=session["user"],cart_count=get_cart_count(uid))

@app.route("/notifications")
@login_required
def notifications():
    uid=get_user_id()
    notifs=[
        {"icon":"🛍️","title":"New arrivals in Electronics!","time":"2 hours ago","read":False},
        {"icon":"⚡","title":"Flash sale: 30% off Fashion — use FASHION30","time":"5 hours ago","read":False},
        {"icon":"📦","title":"Your order has been confirmed","time":"Yesterday","read":True},
        {"icon":"🎁","title":"New reward unlocked: SAVE10","time":"2 days ago","read":True},
        {"icon":"⭐","title":"Rate your recent purchase","time":"3 days ago","read":True},
    ]
    return render_template("notifications.html",username=session["user"],
        cart_count=get_cart_count(uid),notifications=notifs)

@app.route("/help")
@login_required
def help_page():
    uid=get_user_id()
    faqs=[
        {"q":"How do I track my order?","a":"Go to My Orders from profile. Each order shows status."},
        {"q":"What is the return policy?","a":"30-day hassle-free returns. Items must be unused."},
        {"q":"How do I cancel an order?","a":"Cancel within 24 hours from My Orders page."},
        {"q":"Which payment methods are accepted?","a":"All credit/debit cards, UPI, Net Banking via Stripe."},
        {"q":"How long does delivery take?","a":"3-7 business days. Express (1-2 days) in select cities."},
        {"q":"How do promo codes work?","a":"Enter code in cart. Discount applied before GST."},
        {"q":"Is my payment safe?","a":"Yes! 256-bit SSL encryption via Stripe. We never store card details."},
        {"q":"How to contact support?","a":"support@nexacart.in or 1800-123-4567 (Mon-Sat 9AM-6PM)."},
    ]
    return render_template("help.html",username=session["user"],
        cart_count=get_cart_count(uid),faqs=faqs)

@app.route("/about")
@login_required
def about():
    uid=get_user_id()
    return render_template("static_page.html",username=session["user"],cart_count=get_cart_count(uid),
        page_title="About Us",content="""<h2>About Nexacart</h2>
        <p>Nexacart is a curated e-commerce platform offering 326+ products across 30 categories.</p>
        <h3>Our Mission</h3><p>To deliver the best products at fair prices with outstanding service.</p>
        <h3>Contact</h3><p>📧 support@nexacart.in<br>📞 1800-123-4567 (Toll Free, Mon–Sat 9AM–6PM)</p>""")

@app.route("/careers")
@login_required
def careers():
    uid=get_user_id()
    return render_template("static_page.html",username=session["user"],cart_count=get_cart_count(uid),
        page_title="Careers",content="""<h2>Work With Us</h2>
        <p>Join the Nexacart team! Competitive salaries, remote-first culture.</p>
        <h3>Open Positions</h3><ul><li>Senior Frontend Engineer</li><li>Product Manager</li><li>Data Analyst</li><li>Category Manager</li></ul>
        <p>Send resume to <strong>careers@nexacart.in</strong></p>""")

@app.route("/terms")
@login_required
def terms():
    uid=get_user_id()
    return render_template("static_page.html",username=session["user"],cart_count=get_cart_count(uid),
        page_title="Terms of Use",content="""<h2>Terms of Use</h2>
        <h3>1. Account</h3><p>You are responsible for your account credentials.</p>
        <h3>2. Orders</h3><p>All orders subject to product availability and payment confirmation.</p>
        <h3>3. Returns</h3><p>Products returnable within 30 days in original condition.</p>
        <h3>4. Governing Law</h3><p>Governed by laws of India.</p>""")

@app.route("/privacy")
@login_required
def privacy():
    uid=get_user_id()
    return render_template("static_page.html",username=session["user"],cart_count=get_cart_count(uid),
        page_title="Privacy Policy",content="""<h2>Privacy Policy</h2>
        <h3>Data We Collect</h3><p>Name, email, phone, address, order history.</p>
        <h3>How We Use It</h3><p>To process orders and improve our service.</p>
        <h3>Data Security</h3><p>All data encrypted. We never sell your information.</p>""")

@app.route("/cancellation")
@login_required
def cancellation():
    uid=get_user_id()
    return render_template("static_page.html",username=session["user"],cart_count=get_cart_count(uid),
        page_title="Cancellation & Returns",content="""<h2>Cancellation & Returns</h2>
        <h3>Cancellation</h3><ul><li>Cancel before shipment from My Orders.</li><li>Refunds within 5-7 days.</li></ul>
        <h3>Returns</h3><ul><li>30-day return window from delivery.</li><li>Items must be unused with original packaging.</li></ul>""")

# ═══════════════════════════════════════════════════════════
# ADMIN PANEL
# ═══════════════════════════════════════════════════════════
@app.route("/admin/login", methods=["GET","POST"])
def admin_login():
    if request.method=="POST":
        if request.form.get("secret")==ADMIN_SECRET:
            session["is_admin"]=True
            return redirect(url_for("admin_dashboard"))
        return render_template("admin_login.html",error="Invalid admin password.")
    return render_template("admin_login.html",error=None)

@app.route("/admin/logout")
def admin_logout():
    session.clear()          # clear everything including user session
    return redirect(url_for("login"))   # go to main /login page

@app.route("/admin")
@admin_required
def admin_dashboard():
    conn=get_db()
    stats={
        "users":  conn.execute("SELECT COUNT(*) FROM users").fetchone()[0],
        "products":conn.execute("SELECT COUNT(*) FROM products").fetchone()[0],
        "orders": conn.execute("SELECT COUNT(*) FROM orders").fetchone()[0],
        "revenue":conn.execute("SELECT COALESCE(SUM(total),0) FROM orders").fetchone()[0],
        "cart_items":conn.execute("SELECT COALESCE(SUM(quantity),0) FROM cart").fetchone()[0],
        "reviews":conn.execute("SELECT COUNT(*) FROM reviews").fetchone()[0],
    }
    recent_orders=conn.execute("""SELECT o.*,u.username FROM orders o
        JOIN users u ON o.user_id=u.id ORDER BY o.created_at DESC LIMIT 10""").fetchall()
    top_products=conn.execute("""SELECT p.name,p.category,p.price,p.rating,
        COALESCE(SUM(oi.quantity),0) as sold
        FROM products p LEFT JOIN order_items oi ON p.id=oi.product_id
        GROUP BY p.id ORDER BY sold DESC LIMIT 10""").fetchall()
    cat_revenue=conn.execute("""SELECT p.category, COUNT(oi.id) as items, COALESCE(SUM(oi.price*oi.quantity),0) as rev
        FROM order_items oi JOIN products p ON oi.product_id=p.id
        GROUP BY p.category ORDER BY rev DESC LIMIT 8""").fetchall()
    conn.close()
    return render_template("admin_dashboard.html",stats=stats,
        recent_orders=recent_orders,top_products=top_products,cat_revenue=cat_revenue)

@app.route("/admin/products")
@admin_required
def admin_products():
    q=request.args.get("q",""); page=max(1,request.args.get("page",1,type=int))
    conn=get_db()
    w="WHERE name ILIKE ? OR category ILIKE ?" if q else ""
    params=[f"%{q}%",f"%{q}%"] if q else []
    total=conn.execute(f"SELECT COUNT(*) FROM products {w}",params).fetchone()[0]
    items=conn.execute(f"SELECT * FROM products {w} ORDER BY category,name LIMIT 30 OFFSET ?",[*params,(page-1)*30]).fetchall()
    conn.close()
    total_pages=max(1,(total+29)//30)
    return render_template("admin_products.html",products=items,q=q,
        page=page,total_pages=total_pages,total=total,get_img=get_product_image)

@app.route("/admin/products/edit/<int:pid>", methods=["GET","POST"])
@admin_required
def admin_edit_product(pid):
    from werkzeug.utils import secure_filename
    conn=get_db()
    p=conn.execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone()
    if not p: conn.close(); return redirect(url_for("admin_products"))
    msg=None
    if request.method=="POST":
        # Build variants string from custom option fields
        new_cat   = request.form["category"]
        new_name  = request.form["name"]
        copts     = get_customization_options(new_cat, new_name)
        var_parts = []
        for opt in copts:
            val = request.form.get(f"opt_{opt['key']}", "").strip()
            if val:
                var_parts.append(f"{opt['label']}: {val}")
        variants_str = " | ".join(var_parts)
        conn.execute("""UPDATE products SET name=?,price=?,category=?,badge=?,
            rating=?,stock=?,trending=?,variants=? WHERE id=?""",
            (new_name, float(request.form["price"]), new_cat,
             request.form.get("badge","") or None, float(request.form["rating"]),
             int(request.form.get("stock",100)), int(request.form.get("trending",0)),
             variants_str, pid))
        conn.commit()
        # Handle image uploads
        img_folder = os.path.join(os.path.dirname(__file__), "static", "product_images", str(pid))
        os.makedirs(img_folder, exist_ok=True)
        saved = 0
        for slot in range(1, 7):
            f = request.files.get(f"image_{slot}")
            if f and f.filename:
                ext = f.filename.rsplit(".",1)[-1].lower()
                if ext in ("jpg","jpeg","png","webp","gif"):
                    # Remove old images for this slot
                    for old_ext in ("jpg","jpeg","png","webp","gif"):
                        old_p = os.path.join(img_folder, f"{slot}.{old_ext}")
                        if os.path.exists(old_p): os.remove(old_p)
                    save_ext = "jpg" if ext in ("jpg","jpeg") else ext
                    f.save(os.path.join(img_folder, f"{slot}.{save_ext}"))
                    saved += 1
        msg = f"✅ Product updated!{f' {saved} image(s) saved.' if saved else ''}"
        p=conn.execute("SELECT * FROM products WHERE id=?",(pid,)).fetchone()
    conn.close()
    existing_imgs   = get_product_images(pid)
    custom_opts     = get_customization_options(p["category"], p["name"])
    # Parse saved variants string back into a dict  e.g. "Storage: 256 GB | Colour: Black"
    saved_variants  = {}
    if p["variants"]:
        for part in str(p["variants"]).split(" | "):
            if ":" in part:
                k, v = part.split(":", 1)
                saved_variants[k.strip().lower()] = v.strip()
    return render_template("admin_edit_product.html", p=p, msg=msg,
        categories=list(CATEGORY_META.keys()),
        existing_imgs=existing_imgs,
        custom_opts=custom_opts,
        saved_variants=saved_variants,
        get_img=get_product_image)

@app.route("/admin/products/add", methods=["GET","POST"])
@admin_required
def admin_add_product():
    from werkzeug.utils import secure_filename
    msg=None
    new_pid=None
    if request.method=="POST":
        conn=get_db()
        new_pid = conn.execute("""INSERT INTO products(name,price,category,icon,badge,rating,reviews,trending,stock)
            VALUES(?,?,?,?,?,?,0,?,?) RETURNING id""",
            (request.form["name"],float(request.form["price"]),request.form["category"],
             request.form.get("icon","📦"),request.form.get("badge","") or None,
             float(request.form.get("rating",4.0)),int(request.form.get("trending",0)),
             int(request.form.get("stock",100)))).fetchone()[0]
        conn.commit()
        conn.close()
        # Handle image uploads for new product
        img_folder = os.path.join(os.path.dirname(__file__), "static", "product_images", str(new_pid))
        os.makedirs(img_folder, exist_ok=True)
        saved = 0
        for slot in range(1, 7):
            f = request.files.get(f"image_{slot}")
            if f and f.filename:
                ext = f.filename.rsplit(".",1)[-1].lower()
                if ext in ("jpg","jpeg","png","webp","gif"):
                    save_ext = "jpg" if ext in ("jpg","jpeg") else ext
                    f.save(os.path.join(img_folder, f"{slot}.{save_ext}"))
                    saved += 1
        msg = f"✅ Product added!{f' {saved} image(s) saved.' if saved else ''}"
    return render_template("admin_add_product.html",msg=msg,new_pid=new_pid,
        categories=list(CATEGORY_META.keys()))

@app.route("/admin/products/delete/<int:pid>", methods=["POST"])
@admin_required
def admin_delete_product(pid):
    conn=get_db()
    conn.execute("DELETE FROM products WHERE id=?",(pid,))
    conn.commit(); conn.close()
    return redirect(url_for("admin_products"))

@app.route("/admin/orders")
@admin_required
def admin_orders():
    status=request.args.get("status","")
    conn=get_db()
    w="WHERE o.status=?" if status else ""
    params=[status] if status else []
    orders=conn.execute(f"""SELECT o.*,u.username FROM orders o
        JOIN users u ON o.user_id=u.id {w}
        ORDER BY o.created_at DESC LIMIT 50""",params).fetchall()
    conn.close()
    return render_template("admin_orders.html",orders=orders,status=status)

@app.route("/admin/orders/update/<int:oid>", methods=["POST"])
@admin_required
def admin_update_order(oid):
    new_status=request.form.get("status","Confirmed")
    conn=get_db()
    conn.execute("UPDATE orders SET status=? WHERE id=?",(new_status,oid))
    conn.commit(); conn.close()
    return redirect(url_for("admin_orders"))

@app.route("/admin/users")
@admin_required
def admin_users():
    conn=get_db()
    users=conn.execute("""SELECT u.*,
        COUNT(DISTINCT o.id) as order_count,
        COALESCE(SUM(o.total),0) as total_spent
        FROM users u LEFT JOIN orders o ON u.id=o.user_id
        GROUP BY u.id ORDER BY total_spent DESC""").fetchall()
    conn.close()
    return render_template("admin_users.html",users=users)

# ═══════════════════════════════════════════════════════════
# SEARCH API (for live search suggestions)
# ═══════════════════════════════════════════════════════════
@app.route("/api/search")
def api_search():
    q=request.args.get("q","").strip()
    if len(q)<2: return jsonify([])
    conn=get_db()
    rows=conn.execute("SELECT id,name,category,price FROM products WHERE name ILIKE ? LIMIT 8",(f"%{q}%",)).fetchall()
    conn.close()
    return jsonify([{"id":r["id"],"name":r["name"],"category":r["category"],"price":r["price"]} for r in rows])


# ═══════════════════════════════════════════════════════════
# PRODUCT SHARE / QUICK LINK
# ═══════════════════════════════════════════════════════════
@app.route("/share/<int:pid>")
def share_product(pid):
    """Public shareable product page — no login required."""
    conn = get_db()
    p    = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not p:
        return redirect(url_for("login"))
    # Build full product URL
    product_url = url_for("product_detail", pid=pid, _external=True)
    # Redirect to product detail if user is logged in, else show public preview
    if "user" in session:
        return redirect(product_url)
    discount_pct   = 10 + (pid % 4) * 10
    original_price = round(p["price"] / (1 - discount_pct / 100))
    return render_template("share_preview.html",
        p=p, discount_pct=discount_pct,
        original_price=original_price,
        product_url=product_url,
        get_img=get_product_image)

@app.route("/api/short-link/<int:pid>")
@login_required
def get_short_link(pid):
    """Return the shareable URL for a product."""
    share_url  = url_for("share_product", pid=pid, _external=True)
    direct_url = url_for("product_detail", pid=pid, _external=True)
    conn = get_db()
    p = conn.execute("SELECT name, price, category FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not p:
        return jsonify({"error": "Product not found"}), 404
    return jsonify({
        "share_url":  share_url,
        "direct_url": direct_url,
        "product_id": pid,
        "name": p["name"],
        "price": p["price"],
        "category": p["category"],
    })


# ═══════════════════════════════════════════════════════════
# UPI PAYMENT
# ═══════════════════════════════════════════════════════════
@app.route("/upi-payment", methods=["GET","POST"])
@login_required
def upi_payment():
    uid = get_user_id()
    items = get_cart_items(uid)
    if not items: return redirect(url_for("cart"))
    subtotal     = sum(i["price"]*i["quantity"] for i in items)
    discount_pct = session.get("discount_pct",0)
    applied_code = session.get("promo_code","")
    t            = calc_totals(subtotal, discount_pct)
    # UPI ID of the merchant — set via env var
    merchant_upi = os.environ.get("MERCHANT_UPI_ID","nexacart@upi")
    merchant_name= os.environ.get("MERCHANT_NAME","Nexacart")
    return render_template("upi_payment.html",
        items=items, subtotal=subtotal,
        discount_pct=discount_pct, applied_code=applied_code,
        merchant_upi=merchant_upi, merchant_name=merchant_name,
        username=session["user"], cart_count=get_cart_count(uid),
        **t)

@app.route("/upi-verify", methods=["POST"])
@login_required
def upi_verify():
    """User confirms payment after completing on their UPI app."""
    uid       = get_user_id()
    upi_txn   = request.form.get("upi_txn_id","").strip()
    upi_app   = request.form.get("upi_app","UPI")
    items     = get_cart_items(uid)
    if not items: return redirect(url_for("cart"))

    subtotal     = sum(i["price"]*i["quantity"] for i in items)
    discount_pct = session.get("discount_pct",0)
    applied_code = session.get("promo_code","")
    t            = calc_totals(subtotal, discount_pct)
    ref = f"NXC-{random.randint(100000,999999)}"

    conn = get_db()
    user = conn.execute("SELECT * FROM users WHERE id=?",(uid,)).fetchone()
    order_id = conn.execute("""INSERT INTO orders
        (user_id,order_ref,total,subtotal,discount_amt,gst_amt,promo_code,
         address,city,pincode,payment_method,payment_txn_id,status)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?,'Confirmed') RETURNING id""",
        (uid,ref,t["grand_total"],subtotal,t["discount_amt"],t["gst_amt"],applied_code,
         user["address"] or "",user["city"] or "",user["pincode"] or "",
         upi_app, upi_txn)).fetchone()[0]
    for i in items:
        conn.execute("INSERT INTO order_items(order_id,product_id,name,price,quantity,variant) VALUES(?,?,?,?,?,?)",
            (order_id,i["id"],i["name"],i["price"],i["quantity"],i["variant"]))
    conn.execute("DELETE FROM cart WHERE user_id=?",(uid,))
    conn.commit(); conn.close()
    session.pop("promo_code",None); session.pop("discount_pct",None)
    return render_template("success.html", username=session["user"],
        order_ref=ref, total=t["grand_total"], items=items,
        promo=applied_code, payment_method=upi_app, cart_count=0)

# ═══════════════════════════════════════════════════════════
# FORGOT PASSWORD / RESET PASSWORD
# ═══════════════════════════════════════════════════════════
@app.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():
    msg = None
    error = None
    reset_url = None
    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip()
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM users WHERE username=? OR email=? OR phone=?",
            (identifier, identifier.lower(), identifier)
        ).fetchone()
        if user:
            import secrets, datetime as _dt
            token   = secrets.token_urlsafe(32)
            expires = (_dt.datetime.now() + _dt.timedelta(hours=2)).strftime("%Y-%m-%d %H:%M:%S")
            conn.execute("DELETE FROM password_resets WHERE user_id=?", (user["id"],))
            conn.execute(
                "INSERT INTO password_resets(user_id,token,expires_at) VALUES(?,?,?)",
                (user["id"], token, expires)
            )
            conn.commit()
            conn.close()
            reset_url = url_for("reset_password", token=token, _external=True)
            msg = "Reset link generated! In a live app this would be emailed/SMSed to you."
        else:
            conn.close()
            error = "No account found with that username, email, or phone number."
    return render_template("forgot_password.html", msg=msg, error=error, reset_url=reset_url)


@app.route("/reset-password/<token>", methods=["GET", "POST"])
def reset_password(token):
    import datetime as _dt
    conn  = get_db()
    reset = conn.execute(
        "SELECT * FROM password_resets WHERE token=? AND used=0", (token,)
    ).fetchone()

    if not reset:
        conn.close()
        return render_template("reset_password.html",
                               error="Invalid or expired reset link.",
                               token=token, valid=False)

    expires = _dt.datetime.strptime(reset["expires_at"], "%Y-%m-%d %H:%M:%S")
    if _dt.datetime.now() > expires:
        conn.close()
        return render_template("reset_password.html",
                               error="This reset link has expired. Please request a new one.",
                               token=token, valid=False)

    error = None
    if request.method == "POST":
        new_pw  = request.form.get("new_password", "")
        conf_pw = request.form.get("confirm_password", "")
        if len(new_pw) < 6:
            error = "Password must be at least 6 characters."
        elif new_pw != conf_pw:
            error = "Passwords do not match."
        else:
            conn.execute("UPDATE users SET password=? WHERE id=?",
                         (generate_password_hash(new_pw), reset["user_id"]))
            conn.execute("UPDATE password_resets SET used=1 WHERE token=?", (token,))
            conn.commit()
            conn.close()
            return redirect(url_for("login"))

    conn.close()
    return render_template("reset_password.html", token=token, valid=True, error=error)



# ═══════════════════════════════════════════════════════════
# ADDITIONAL UTILITY ROUTES
# ═══════════════════════════════════════════════════════════

@app.route("/api/pincode/<pin>")
@login_required
def pincode_lookup(pin):
    """Return city/state for Indian PIN codes (offline lookup for common codes)."""
    # Extended PIN code map for major Indian cities
    PIN_MAP = {
        "110001":"New Delhi","110002":"New Delhi","110011":"New Delhi",
        "400001":"Mumbai","400050":"Mumbai","400070":"Mumbai",
        "560001":"Bengaluru","560002":"Bengaluru","560034":"Bengaluru",
        "600001":"Chennai","600004":"Chennai","600020":"Chennai",
        "700001":"Kolkata","700012":"Kolkata","700019":"Kolkata",
        "500001":"Hyderabad","500003":"Hyderabad","500034":"Hyderabad",
        "411001":"Pune","411002":"Pune","411014":"Pune",
        "380001":"Ahmedabad","380006":"Ahmedabad","380013":"Ahmedabad",
        "226001":"Lucknow","226010":"Lucknow","226020":"Lucknow",
        "302001":"Jaipur","302004":"Jaipur","302017":"Jaipur",
        "800001":"Patna","800020":"Patna",
        "682001":"Kochi","682011":"Kochi",
        "641001":"Coimbatore","641005":"Coimbatore",
        "530001":"Visakhapatnam","530002":"Visakhapatnam",
        "533101":"Rajahmundry","533103":"Rajahmundry",
        "533201":"Razole","533212":"Razole",
        "533001":"Eluru","533002":"Eluru",
        "533003":"Kakinada","533004":"Kakinada",
        "521001":"Vijayawada","521002":"Vijayawada",
        "110092":"Delhi","110085":"Delhi","110007":"Delhi",
        "201301":"Noida","201304":"Noida",
        "122001":"Gurugram","122002":"Gurugram",
        "600028":"Chennai","600029":"Chennai",
    }
    city = PIN_MAP.get(pin, "")
    return jsonify({"city": city, "found": bool(city)})

@app.route("/api/categories")
@login_required
def api_categories():
    """Return all categories with product counts."""
    conn = get_db()
    rows = conn.execute(
        "SELECT category, COUNT(*) as cnt, AVG(rating) as avg_rating "
        "FROM products GROUP BY category ORDER BY category"
    ).fetchall()
    conn.close()
    return jsonify([{"category":r["category"],"count":r["cnt"],
                     "avg_rating":round(r["avg_rating"],1)} for r in rows])

@app.route("/api/product/<int:pid>")
@login_required
def api_product(pid):
    """Return product JSON for quick preview."""
    conn = get_db()
    p = conn.execute("SELECT * FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not p: return jsonify({"error":"Not found"}), 404
    discount_pct = 10 + (pid % 4) * 10
    original_price = round(p["price"] / (1 - discount_pct/100))
    return jsonify({
        "id":p["id"],"name":p["name"],"price":p["price"],
        "original_price":original_price,"discount_pct":discount_pct,
        "category":p["category"],"rating":p["rating"],"reviews":p["reviews"],
        "badge":p["badge"],"stock":p["stock"],
        "image": get_product_image(p["name"],p["category"])
    })


# =============================================================
# AI CHATBOT + RECOMMENDATIONS
# =============================================================

@app.route("/api/chat", methods=["POST"])
@login_required
def api_chat():
    import urllib.request, json as _json
    data     = request.get_json(silent=True) or {}
    user_msg = (data.get("message","")).strip()[:500]
    history  = data.get("history", [])[-10:]
    if not user_msg:
        return jsonify({"reply":"Please type a message."}), 400

    conn = get_db()
    cat_rows = conn.execute("SELECT DISTINCT category FROM products").fetchall()
    conn.close()
    cats     = [r[0] for r in cat_rows]
    cats_str = ", ".join(cats)

    system_prompt = (
        "You are Nexa, a friendly AI shopping assistant for Nexacart, an Indian e-commerce site. "
        "Help customers find products and answer questions about orders, delivery, returns, payments. "
        "Store details: 326 products across categories: " + cats_str + ". "
        "Free delivery on all orders. 30-day returns. "
        "Payments: UPI (GPay PhonePe Paytm BHIM) and Stripe cards. GST 9%. Delivery 3-5 days. "
        "Promo codes: SAVE10 MARKET20 FIRST50. Be concise, warm and helpful in 1-3 sentences."
    )

    messages = []
    for h in history:
        if h.get("role") in ("user","assistant") and h.get("content"):
            messages.append({"role": h["role"], "content": str(h["content"])[:400]})
    messages.append({"role":"user","content":user_msg})

    api_key = os.environ.get("ANTHROPIC_API_KEY","")

    if not api_key:
        ml = user_msg.lower()
        if any(w in ml for w in ["return","refund","exchange"]):
            reply = "30-day easy returns on all products! Visit your Orders page to request a return. Refunds within 3-5 business days."
        elif any(w in ml for w in ["deliver","ship","when will","arrive","track"]):
            reply = "Free delivery on all orders, arriving in 3-5 business days. Track your order status in the Orders section."
        elif any(w in ml for w in ["promo","code","discount","offer","coupon","save"]):
            reply = "Use SAVE10 for 10% off, MARKET20 for 20% off, or FIRST50 for 50% off your first order at checkout!"
        elif any(w in ml for w in ["pay","payment","upi","gpay","phonepe","paytm","bhim","card","stripe"]):
            reply = "We accept all UPI apps (GPay, PhonePe, Paytm, BHIM) and Credit/Debit Cards. 100% secure payments!"
        elif any(w in ml for w in ["hello","hi","hey","help","start"]):
            reply = "Hello! I am Nexa, your Nexacart shopping assistant. I can help find products, answer questions about orders, delivery and more!"
        elif any(w in ml for w in ["phone","smartphone","mobile","iphone","samsung","oneplus"]):
            reply = "We have a great Smartphones section with iPhone, Samsung Galaxy, OnePlus, Pixel, Xiaomi and more. Browse Products to explore!"
        elif any(w in ml for w in ["laptop","computer","macbook","dell","hp","lenovo"]):
            reply = "Check our Laptops section featuring MacBook, Dell XPS, HP Pavilion, Lenovo ThinkPad, ASUS ROG and more!"
        elif any(w in ml for w in ["thank","thanks","great","awesome","perfect"]):
            reply = "Happy to help! Enjoy your shopping at Nexacart!"
        elif any(w in ml for w in ["price","cost","cheap","expensive","budget"]):
            reply = "We have products for every budget! Use filters on the Products page to sort by price. Promo code SAVE10 gives 10% off."
        elif any(w in ml for w in ["cancel","cancell"]):
            reply = "Orders can be cancelled before shipping. Go to your Orders page and select Cancel. For queries contact support via Help page."
        else:
            reply = ("I can help with product recommendations, delivery, returns, payments and more! "
                     "We have " + str(len(cats)) + " product categories. What are you looking for?")
        return jsonify({"reply": reply})

    try:
        payload = _json.dumps({
            "model": "claude-haiku-4-5-20251001",
            "max_tokens": 200,
            "system": system_prompt,
            "messages": messages
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages",
            data=payload,
            headers={
                "Content-Type": "application/json",
                "x-api-key": api_key,
                "anthropic-version": "2023-06-01"
            },
            method="POST"
        )
        with urllib.request.urlopen(req, timeout=12) as resp:
            result = _json.loads(resp.read())
        reply = result["content"][0]["text"]
    except Exception:
        reply = "Sorry, having a brief issue! Browse products directly or try again in a moment."

    return jsonify({"reply": reply})


@app.route("/api/stock/<int:pid>")
@login_required
def api_stock(pid):
    """Return current stock level for a product."""
    conn = get_db()
    p = conn.execute("SELECT stock, name FROM products WHERE id=?", (pid,)).fetchone()
    conn.close()
    if not p: return jsonify({"error":"Not found"}), 404
    return jsonify({"id":pid,"stock":p["stock"],"low": p["stock"] < 10, "name":p["name"]})


@app.route("/api/recommendations")
@login_required
def api_recommendations():
    uid  = get_user_id()
    conn = get_db()
    orders   = conn.execute(
        "SELECT DISTINCT p.category FROM order_items oi "
        "JOIN products p ON oi.product_id=p.id "
        "JOIN orders o ON oi.order_id=o.id WHERE o.user_id=? LIMIT 10", (uid,)
    ).fetchall()
    wishlist = conn.execute(
        "SELECT DISTINCT p.category FROM wishlist w "
        "JOIN products p ON w.product_id=p.id WHERE w.user_id=? LIMIT 10", (uid,)
    ).fetchall()
    viewed   = conn.execute(
        "SELECT DISTINCT p.category FROM recently_viewed rv "
        "JOIN products p ON rv.product_id=p.id WHERE rv.user_id=? LIMIT 10", (uid,)
    ).fetchall()
    fav_cats = list({r[0] for r in (orders + wishlist + viewed)})
    if fav_cats:
        bought = {r[0] for r in conn.execute(
            "SELECT oi.product_id FROM order_items oi "
            "JOIN orders o ON oi.order_id=o.id WHERE o.user_id=?", (uid,)
        ).fetchall()}
        ph   = ",".join("?" * len(fav_cats))
        # Score: (trending*2 + rating + log(reviews)/3) weighted
        rows = conn.execute(
            "SELECT *, (trending*2.5 + rating + MIN(reviews,10000)/3333.0) AS score "
            "FROM products WHERE category IN (" + ph + ") AND stock>0 "
            "ORDER BY score DESC, reviews DESC LIMIT 20", fav_cats
        ).fetchall()
        rows = [p for p in rows if p["id"] not in bought][:8]
        # If not enough, fill from popular products
        if len(rows) < 4:
            existing_ids = {p["id"] for p in rows} | bought
            extra = conn.execute(
                "SELECT * FROM products WHERE stock>0 "
                "ORDER BY trending DESC, rating DESC, reviews DESC LIMIT 12"
            ).fetchall()
            for p in extra:
                if p["id"] not in existing_ids and len(rows) < 8:
                    rows = list(rows) + [p]
    else:
        # Cold start: show mix of trending + top-rated across different categories
        rows = conn.execute(
            "SELECT *, (trending*2.5 + rating + MIN(reviews,10000)/3333.0) AS score "
            "FROM products WHERE stock>0 "
            "ORDER BY score DESC, reviews DESC LIMIT 8"
        ).fetchall()
    conn.close()
    return jsonify([{
        "id":      p["id"],
        "name":    p["name"],
        "price":   p["price"],
        "category":p["category"],
        "rating":  p["rating"],
        "reviews": p["reviews"],
        "badge":   p["badge"] or "",
        "image":   get_product_image(p["id"])
    } for p in rows])


@app.route("/request-admin-access", methods=["GET","POST"])
def request_admin_access():
    """Allow users to request admin invite code from the admin."""
    msg = None
    if request.method == "POST":
        username = request.form.get("username","").strip()
        email    = request.form.get("email","").strip().lower()
        phone    = request.form.get("phone","").strip()
        reason   = request.form.get("reason","").strip()[:300]
        if not username or not reason:
            msg = "error:Username and reason are required."
        else:
            conn = get_db()
            conn.execute(
                "INSERT INTO admin_requests(username,email,phone,reason) VALUES(?,?,?,?)",
                (username, email, phone, reason)
            )
            conn.commit(); conn.close()
            msg = "success:Request submitted! The system administrator will review it and send your invite code."
    return render_template("request_admin.html", msg=msg)

@app.route("/admin/requests/approve/<int:req_id>", methods=["POST"])
@admin_required
def admin_approve_request(req_id):
    conn = get_db()
    conn.execute("UPDATE admin_requests SET status='approved' WHERE id=?", (req_id,))
    conn.commit(); conn.close()
    return redirect(url_for("admin_users"))

@app.route("/admin/requests/reject/<int:req_id>", methods=["POST"])
@admin_required
def admin_reject_request(req_id):
    conn = get_db()
    conn.execute("UPDATE admin_requests SET status='rejected' WHERE id=?", (req_id,))
    conn.commit(); conn.close()
    return redirect(url_for("admin_users"))


# Initialize database on module load (required for Vercel serverless and gunicorn)
with app.app_context():
    try:
        init_db()
        insert_sample_products()
        seed_default_users()
    except Exception as e:
        print(f"DB initialization error: {e}")

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    debug = os.environ.get("FLASK_DEBUG", "false").lower() == "true"
    app.run(host="0.0.0.0", port=port, debug=debug)
