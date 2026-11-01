# NSUT Lost & Found Portal

A Flask mini-project for reporting and browsing lost and found items. Local development uses a JSON file. When `DATABASE_URL` is configured, the app uses a shared PostgreSQL database so listings are available to all devices using the deployed site.

Reports can include an optional JPEG, PNG, or WebP photo up to 1 MB. The photo is stored with the listing in shared PostgreSQL on Vercel, so every device using the same deployed site can view it. On supported phones, the file picker can open the camera.

## Run locally

1. Install Python 3 and open a terminal in this project folder.
2. Run:

```powershell
py -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

3. Visit http://127.0.0.1:5000.

Without `DATABASE_URL`, the app saves data to `items.json` beside `app.py`.

## Configure shared storage on Vercel

1. In the Vercel dashboard, open the project and add a PostgreSQL database through the Vercel Marketplace (for example, Neon or Supabase).
2. Connect the Supabase integration to this Vercel project. The app reads `DATABASE_POSTGRES_URL`, `DATABASE_POSTGRES_PRISMA_URL`, `DATABASE_URL`, or `POSTGRES_URL`.
3. Make sure the database variables are available in the Production environment, then redeploy the Vercel project.
4. Open the same deployed URL on both devices. New listings will be stored in the shared database. The app creates its `campusfind_items` table automatically on first use.

Keep the database connection string secret. Never paste it into Python source code or commit it to GitHub. The database will start empty; temporary listings previously saved in Vercel `/tmp` may not be recoverable.

If `DATABASE_URL` is not set on Vercel, the app falls back to `/tmp/lost_found_items.json`. That storage is temporary and not suitable for sharing or permanent records.

## Features

- Browse, search, and filter lost and found listings.
- Submit a listing and view its details.
- Mark a listing as resolved or delete it.
- Download listings as CSV.
- JSON API: `GET /api/items` lists items; `POST /api/items` adds one.

## Project files

- `app.py`: Flask routes, validation, and JSON/Postgres storage.
- `templates/`: HTML pages rendered by Flask and Jinja.
- `static/style.css`: page appearance.
- `static/script.js`: live search behavior in the browser.
- `requirements.txt`: Flask and the PostgreSQL driver.

This is a classroom demonstration. It has no login system, so anyone who can access it may be able to mark or delete listings. Avoid posting sensitive contact details publicly.
