"""CampusFind: a small Flask lost-and-found project."""

import csv
import base64
import json
import os
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

from flask import Flask, Response, flash, jsonify, redirect, render_template, request, url_for

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "nsut-lost-found-class-project")
app.config["MAX_CONTENT_LENGTH"] = 1_500_000

# Set DATABASE_URL on Vercel to use shared Postgres storage. Without it,
# local development continues to save listings in items.json.
DATABASE_URL = (
    os.environ.get("DATABASE_POSTGRES_URL")
    or os.environ.get("DATABASE_POSTGRES_PRISMA_URL")
    or os.environ.get("DATABASE_URL")
    or os.environ.get("POSTGRES_URL")
)
if os.environ.get("DATA_FILE"):
    DATA_FILE = Path(os.environ["DATA_FILE"])
elif os.environ.get("VERCEL"):
    DATA_FILE = Path("/tmp/lost_found_items.json")
else:
    DATA_FILE = Path(__file__).parent / "items.json"

CATEGORIES = [
    "Electronics",
    "ID / Documents",
    "Clothing",
    "Books / Stationery",
    "Accessories",
    "Other",
]
ITEM_FIELDS = [
    "kind",
    "title",
    "description",
    "category",
    "location",
    "item_date",
    "contact",
]
MAX_PHOTO_BYTES = 1_000_000


def _database_connection():
    """Open a short-lived Postgres connection for the current request."""
    if not DATABASE_URL:
        raise RuntimeError("DATABASE_URL is not configured.")

    try:
        import psycopg
        from psycopg.rows import dict_row
    except ImportError as error:
        raise RuntimeError("Install the psycopg package to use Postgres.") from error

    # Parse the connection URL into standard PostgreSQL fields. Marketplace
    # URLs can contain provider-specific query parameters (for example `supa`)
    # that Psycopg does not recognize, so only pass standard options through.
    parts = urlsplit(DATABASE_URL)
    if parts.scheme not in ("postgres", "postgresql") or not parts.hostname:
        raise RuntimeError("The database connection URL is not a valid PostgreSQL URL.")

    query = parse_qs(parts.query)
    options = {
        "host": parts.hostname,
        "port": parts.port or 5432,
        "dbname": unquote(parts.path.lstrip("/").split("/", 1)[0]),
        "user": unquote(parts.username or ""),
        "password": unquote(parts.password or ""),
        "sslmode": query.get("sslmode", ["require"])[0],
        "connect_timeout": 10,
    }
    return psycopg.connect(**options, row_factory=dict_row)


def _prepare_database(connection):
    """Create the listings table if this is the first database request."""
    connection.execute(
        """
        CREATE TABLE IF NOT EXISTS campusfind_items (
            id BIGSERIAL PRIMARY KEY,
            kind TEXT NOT NULL,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            category TEXT NOT NULL,
            location TEXT NOT NULL,
            item_date TEXT NOT NULL,
            contact TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'Open',
            photo_data TEXT
        )
        """
    )
    connection.execute(
        "ALTER TABLE campusfind_items ADD COLUMN IF NOT EXISTS photo_data TEXT"
    )


def read_uploaded_photo(upload):
    """Validate and encode an optional JPEG, PNG, or WebP upload."""
    if not upload or not upload.filename:
        return None

    image_bytes = upload.stream.read(MAX_PHOTO_BYTES + 1)
    if len(image_bytes) > MAX_PHOTO_BYTES:
        raise ValueError("Photo must be 1 MB or smaller.")

    if image_bytes.startswith(b"\xff\xd8\xff"):
        image_type = "image/jpeg"
    elif image_bytes.startswith(b"\x89PNG\r\n\x1a\n"):
        image_type = "image/png"
    elif image_bytes.startswith(b"RIFF") and image_bytes[8:12] == b"WEBP":
        image_type = "image/webp"
    else:
        raise ValueError("Choose a valid JPEG, PNG, or WebP image.")

    encoded = base64.b64encode(image_bytes).decode("ascii")
    return f"data:{image_type};base64,{encoded}"


def load_items():
    """Read listings from Postgres, or from the local JSON file."""
    if DATABASE_URL:
        try:
            with _database_connection() as connection:
                _prepare_database(connection)
                rows = connection.execute(
                    """
                    SELECT id, kind, title, description, category, location,
                           item_date, contact, status, photo_data
                    FROM campusfind_items
                    ORDER BY id
                    """
                ).fetchall()
            return [dict(row) for row in rows]
        except Exception as error:
            raise RuntimeError("Could not read listings from the database.") from error

    try:
        with DATA_FILE.open("r", encoding="utf-8") as file:
            return json.load(file)
    except FileNotFoundError:
        return []
    except json.JSONDecodeError:
        return []


def save_items(items):
    """Save listings to the local JSON file (used in local development)."""
    DATA_FILE.parent.mkdir(parents=True, exist_ok=True)
    with DATA_FILE.open("w", encoding="utf-8") as file:
        json.dump(items, file, indent=4, ensure_ascii=False)


def add_item(item):
    """Add one listing and return it with its ID and Open status."""
    if DATABASE_URL:
        try:
            with _database_connection() as connection:
                _prepare_database(connection)
                row = connection.execute(
                    """
                    INSERT INTO campusfind_items
                        (kind, title, description, category, location, item_date, contact, photo_data)
                    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING id
                    """,
                    [item[field] for field in ITEM_FIELDS] + [item.get("photo_data")],
                ).fetchone()
            return {**item, "id": row["id"], "status": "Open"}
        except Exception as error:
            raise RuntimeError("Could not save the listing to the database.") from error

    items = load_items()
    item["id"] = max([entry["id"] for entry in items], default=0) + 1
    item["status"] = "Open"
    items.append(item)
    save_items(items)
    return item


def set_item_resolved(item_id):
    """Mark one listing resolved and report whether it existed."""
    if DATABASE_URL:
        try:
            with _database_connection() as connection:
                _prepare_database(connection)
                result = connection.execute(
                    "UPDATE campusfind_items SET status = 'Resolved' WHERE id = %s",
                    [item_id],
                )
            return result.rowcount > 0
        except Exception as error:
            raise RuntimeError("Could not update the listing in the database.") from error

    items = load_items()
    for item in items:
        if item["id"] == item_id:
            item["status"] = "Resolved"
            save_items(items)
            return True
    return False


def delete_item(item_id):
    """Delete one listing and report whether it existed."""
    if DATABASE_URL:
        try:
            with _database_connection() as connection:
                _prepare_database(connection)
                result = connection.execute(
                    "DELETE FROM campusfind_items WHERE id = %s",
                    [item_id],
                )
            return result.rowcount > 0
        except Exception as error:
            raise RuntimeError("Could not delete the listing from the database.") from error

    items = load_items()
    remaining = [item for item in items if item["id"] != item_id]
    if len(remaining) == len(items):
        return False
    save_items(remaining)
    return True


def get_item(item_id):
    """Find one listing by its numeric ID."""
    for item in load_items():
        if item["id"] == item_id:
            return item
    return None


@app.route("/")
def home():
    """Show listings and allow simple keyword/type/category filtering."""
    items = load_items()
    keyword = request.args.get("q", "").strip().lower()
    kind = request.args.get("kind", "")
    category = request.args.get("category", "")

    if keyword:
        items = [
            item for item in items
            if keyword in item["title"].lower()
            or keyword in item["description"].lower()
            or keyword in item["location"].lower()
        ]
    if kind in ("Lost", "Found"):
        items = [item for item in items if item["kind"] == kind]
    if category in CATEGORIES:
        items = [item for item in items if item["category"] == category]

    items.reverse()
    return render_template("index.html", items=items, categories=CATEGORIES)


@app.route("/report", methods=["GET", "POST"])
def report():
    """Display the report form (GET) and save a listing (POST)."""
    if request.method == "POST":
        item = {field: request.form.get(field, "").strip() for field in ITEM_FIELDS}
        try:
            item["photo_data"] = read_uploaded_photo(request.files.get("photo"))
        except ValueError as error:
            flash(str(error), "error")
            return render_template(
                "item_form.html",
                categories=CATEGORIES,
                temporary_storage=bool(os.environ.get("VERCEL") and not DATABASE_URL),
                shared_storage=bool(DATABASE_URL),
            ), 400

        if not all(item[field] for field in ITEM_FIELDS):
            flash("Please fill in every field.", "error")
            return render_template(
                "item_form.html",
                categories=CATEGORIES,
                temporary_storage=bool(os.environ.get("VERCEL") and not DATABASE_URL),
                shared_storage=bool(DATABASE_URL),
            ), 400
        elif item["kind"] not in ("Lost", "Found") or item["category"] not in CATEGORIES:
            flash("Please choose a valid item type and category.", "error")
        else:
            try:
                add_item(item)
                flash("Your listing has been added.", "success")
                return redirect(url_for("home"))
            except (OSError, RuntimeError):
                flash("Could not save the listing. Check the database connection or local folder.", "error")

    return render_template(
        "item_form.html",
        categories=CATEGORIES,
        temporary_storage=bool(os.environ.get("VERCEL") and not DATABASE_URL),
        shared_storage=bool(DATABASE_URL),
    )


@app.route("/item/<int:item_id>")
def detail(item_id):
    item = get_item(item_id)
    if item is None:
        return render_template(
            "message.html", title="Not found", message="This listing does not exist."
        ), 404
    return render_template("detail.html", item=item)


@app.route("/item/<int:item_id>/resolve", methods=["POST"])
def resolve(item_id):
    try:
        updated = set_item_resolved(item_id)
    except (OSError, RuntimeError):
        flash("Could not update the listing. Check the database connection.", "error")
        return redirect(url_for("detail", item_id=item_id))

    if not updated:
        return render_template(
            "message.html", title="Not found", message="This listing does not exist."
        ), 404
    flash("Listing marked as resolved.", "success")
    return redirect(url_for("detail", item_id=item_id))


@app.route("/item/<int:item_id>/delete", methods=["POST"])
def delete(item_id):
    """Remove a listing from the project data."""
    try:
        deleted = delete_item(item_id)
    except (OSError, RuntimeError):
        flash("Could not delete the listing. Check the database connection.", "error")
        return redirect(url_for("home"))

    if not deleted:
        return render_template(
            "message.html", title="Not found", message="This listing does not exist."
        ), 404
    flash("Listing deleted.", "success")
    return redirect(url_for("home"))


@app.route("/api/items", methods=["GET", "POST"])
def api_items():
    """Small JSON API: GET lists items and POST adds an item."""
    if request.method == "GET":
        return jsonify(load_items())

    data = request.get_json(silent=True) or {}
    item = {field: str(data.get(field, "")).strip() for field in ITEM_FIELDS}
    if not all(item.values()):
        return jsonify({"error": "All item fields are required."}), 400
    if item["kind"] not in ("Lost", "Found") or item["category"] not in CATEGORIES:
        return jsonify({"error": "Invalid type or category."}), 400

    try:
        item = add_item(item)
    except (OSError, RuntimeError):
        return jsonify({"error": "Could not save item data."}), 500
    return jsonify(item), 201


@app.route("/export.csv")
def export_csv():
    """Create a CSV download using Python's built-in csv module."""
    from io import StringIO

    output = StringIO()
    fields = [
        "id", "kind", "title", "description", "category", "location",
        "item_date", "contact", "status",
    ]
    writer = csv.DictWriter(output, fieldnames=fields)
    writer.writeheader()
    writer.writerows(load_items())
    return Response(
        output.getvalue(),
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=lost_found_items.csv"},
    )


if __name__ == "__main__":
    app.run(debug=True)

