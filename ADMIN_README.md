# Nexacart Admin Panel

## How to Access Admin

1. Run the app: `python app.py`
2. Open browser: http://127.0.0.1:5000/admin/login
3. Enter admin password: `nexacart_admin_2025`

## Admin Sections

| Section       | URL                    | What you can do                          |
|---------------|------------------------|------------------------------------------|
| Dashboard     | /admin                 | Revenue, orders, users stats overview    |
| Products      | /admin/products        | Search, edit, delete all 326+ products   |
| Add Product   | /admin/products/add    | Add new products                         |
| Orders        | /admin/orders          | View all orders, update status           |
| Users         | /admin/users           | View all registered users & spending     |

## Changing Admin Password
Edit line 9 in `app.py`:
```python
ADMIN_SECRET = "nexacart_admin_2025"   # ← change this
```

## Order Status Flow
Confirmed → Processing → Shipped → Delivered

## New User Fields (Register)
- Username (required, min 3 chars)
- Gmail/Email (required if no phone)
- Mobile + Country code (required if no email)
- Password (required, min 6 chars)

## Login Options
Users can login with:
- Username
- Email address
- Mobile number (with country code, e.g. +91 98765 43210)

## Forgot Password Flow
1. User goes to /forgot-password
2. Enters username/email/phone
3. System generates a reset token (in production: sends email/SMS)
4. Demo mode: shows the reset link directly on screen
5. Link valid for 2 hours
