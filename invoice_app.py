"""
Precision-style Bike Mechanic Job Order + Invoice Prep App
==========================================================

A phone-first Streamlit MVP for a solo bike mechanic who wants to:
- Use quick job templates
- Link jobs to customers and bikes
- Create reusable job orders
- Generate customer-facing invoice/email text
- Produce a Zettle/PayPal entry summary to avoid retyping notes
- Track paid/unpaid status and Zettle receipt details

Run locally:
    pip install streamlit pandas
    streamlit run invoice_app.py

Data storage:
    This app stores data in a local SQLite file named invoice_app.db in the
    same folder as this script. For Streamlit Cloud or production hosting,
    use an external persistent database instead of relying on local files.
"""

from __future__ import annotations

import os
import sqlite3
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any
from urllib.parse import quote

import pandas as pd
import streamlit as st


# -----------------------------------------------------------------------------
# Configuration
# -----------------------------------------------------------------------------

APP_TITLE = "Precision Bicycle Services - Work order and invoicing system"
DB_PATH = Path(__file__).with_name("invoice_app.db")
DEFAULT_TAX_RATE = 0.06

STATUS_OPTIONS = [
    "Estimate",
    "Waiting approval",
    "In progress",
    "Ready",
    "Picked up",
    "Closed",
]

PAYMENT_STATUS_OPTIONS = ["Unpaid", "Paid", "Partial", "Comped", "Canceled"]

LINE_ITEM_COLUMNS = ["category", "description", "quantity", "unit_price", "taxable"]


# -----------------------------------------------------------------------------
# Database helpers
# -----------------------------------------------------------------------------


def get_database_url() -> str | None:
    if os.environ.get("DATABASE_URL"):
        return os.environ["DATABASE_URL"]
    try:
        return st.secrets.get("DATABASE_URL")
    except Exception:
        return None


def get_secret(name: str) -> str | None:
    if os.environ.get(name):
        return os.environ[name]
    try:
        value = st.secrets.get(name)
    except Exception:
        return None
    return str(value) if value else None


DATABASE_URL = get_database_url()
APP_PASSWORD = get_secret("APP_PASSWORD")


@dataclass
class DbResult:
    lastrowid: int | None = None


def using_postgres() -> bool:
    return bool(DATABASE_URL)


def pg_sql(sql: str) -> str:
    return sql.replace("INTEGER PRIMARY KEY AUTOINCREMENT", "BIGSERIAL PRIMARY KEY").replace("?", "%s")


def connect() -> Any:
    if using_postgres():
        import psycopg
        from psycopg.rows import dict_row

        return psycopg.connect(DATABASE_URL, row_factory=dict_row, prepare_threshold=None)

    conn = sqlite3.connect(DB_PATH, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def execute(sql: str, params: tuple[Any, ...] = (), returning: str | None = None) -> DbResult:
    with connect() as conn:
        if using_postgres():
            statement = pg_sql(sql)
            if returning:
                statement = f"{statement.rstrip()} RETURNING {returning}"
            cur = conn.execute(statement, params)
            row = cur.fetchone() if returning else None
            conn.commit()
            return DbResult(lastrowid=int(row[returning]) if row else None)

        cur = conn.execute(sql, params)
        conn.commit()
        return DbResult(lastrowid=cur.lastrowid)


def query_df(sql: str, params: tuple[Any, ...] = ()) -> pd.DataFrame:
    with connect() as conn:
        if using_postgres():
            cur = conn.execute(pg_sql(sql), params)
            rows = cur.fetchall()
            columns = [column.name for column in cur.description or []]
            return pd.DataFrame(rows, columns=columns)

        return pd.read_sql_query(pg_sql(sql) if using_postgres() else sql, conn, params=params)


def query_one(sql: str, params: tuple[Any, ...] = ()) -> Any | None:
    with connect() as conn:
        cur = conn.execute(pg_sql(sql) if using_postgres() else sql, params)
        return cur.fetchone()


def is_unique_violation(error: Exception) -> bool:
    if isinstance(error, sqlite3.IntegrityError):
        return True
    if using_postgres():
        try:
            import psycopg

            return isinstance(error, psycopg.errors.UniqueViolation)
        except Exception:
            return False
    return False


def require_password() -> bool:
    if not APP_PASSWORD:
        return True

    if st.session_state.get("authenticated"):
        return True

    st.title("Precision Bicycle Services")
    st.caption("Enter the app password to continue.")

    with st.form("password_form"):
        password = st.text_input("Password", type="password")
        submitted = st.form_submit_button("Unlock")

    if submitted:
        if password == APP_PASSWORD:
            st.session_state["authenticated"] = True
            st.rerun()
        else:
            st.error("Incorrect password.")

    return False


def clean_text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, (list, tuple, set)):
        return ", ".join(clean_text(item) for item in value if clean_text(item))
    return str(value).strip()


def init_db() -> None:
    execute(
        """
        CREATE TABLE IF NOT EXISTS customers (
            customer_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL,
            email TEXT,
            phone TEXT,
            notes TEXT,
            created_at TEXT NOT NULL
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS bikes (
            bike_id INTEGER PRIMARY KEY AUTOINCREMENT,
            customer_id INTEGER NOT NULL,
            nickname TEXT,
            brand_model TEXT,
            color TEXT,
            bike_type TEXT,
            notes TEXT,
            created_at TEXT NOT NULL,
            FOREIGN KEY(customer_id) REFERENCES customers(customer_id)
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS templates (
            template_id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            default_customer_notes TEXT,
            default_internal_notes TEXT,
            default_tax_rate REAL NOT NULL,
            created_at TEXT NOT NULL
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS template_line_items (
            template_line_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            template_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit_price REAL NOT NULL,
            taxable INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(template_id) REFERENCES templates(template_id)
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS job_orders (
            job_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_number TEXT,
            customer_id INTEGER NOT NULL,
            bike_id INTEGER,
            template_id INTEGER,
            date_created TEXT NOT NULL,
            status TEXT NOT NULL,
            intake_notes TEXT,
            diagnosis_notes TEXT,
            internal_notes TEXT,
            customer_notes TEXT,
            tax_rate REAL NOT NULL,
            payment_status TEXT NOT NULL,
            zettle_receipt_number TEXT,
            zettle_receipt_url TEXT,
            paypal_invoice_id TEXT,
            paypal_invoice_url TEXT,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            FOREIGN KEY(customer_id) REFERENCES customers(customer_id),
            FOREIGN KEY(bike_id) REFERENCES bikes(bike_id),
            FOREIGN KEY(template_id) REFERENCES templates(template_id)
        )
        """
    )
    execute(
        """
        CREATE TABLE IF NOT EXISTS job_line_items (
            line_item_id INTEGER PRIMARY KEY AUTOINCREMENT,
            job_id INTEGER NOT NULL,
            category TEXT NOT NULL,
            description TEXT NOT NULL,
            quantity REAL NOT NULL,
            unit_price REAL NOT NULL,
            taxable INTEGER NOT NULL DEFAULT 1,
            FOREIGN KEY(job_id) REFERENCES job_orders(job_id)
        )
        """
    )
    seed_templates()


def seed_templates() -> None:
    existing = query_one("SELECT COUNT(*) AS n FROM templates")
    if existing and existing["n"] > 0:
        return

    defaults = [
        {
            "name": "General Bicycle Service",
            "customer_notes": "General bicycle service. Final work details may be adjusted after inspection.",
            "internal_notes": "Use for broad Zettle categories like Bicycle Service Labor + Misc parts.",
            "items": [
                ("Labor", "Bicycle Service Labor", 1, 120.00, 1),
                ("Part", "Misc parts", 1, 0.00, 1),
            ],
        },
        {
            "name": "Flat Repair",
            "customer_notes": "Flat repair: replace tube, inspect tire/rim strip, inflate to recommended pressure.",
            "internal_notes": "Check tire for glass/debris and note if tire replacement is recommended.",
            "items": [
                ("Labor", "Flat repair labor", 1, 25.00, 1),
                ("Part", "Tube", 1, 10.00, 1),
            ],
        },
        {
            "name": "Basic Tune-Up",
            "customer_notes": "Basic tune-up: brake/shift adjustment, bolt check, tire inflation, drivetrain inspection, and test ride.",
            "internal_notes": "Record any recommended follow-up work separately.",
            "items": [
                ("Labor", "Basic tune-up labor", 1, 95.00, 1),
            ],
        },
        {
            "name": "Brake Adjustment",
            "customer_notes": "Brake service: inspect pads/cables/housing, adjust calipers and levers, test braking performance.",
            "internal_notes": "Confirm whether pads are rim/disc and whether parts were installed.",
            "items": [
                ("Labor", "Brake adjustment labor", 1, 40.00, 1),
                ("Part", "Brake pads", 1, 25.00, 1),
            ],
        },
        {
            "name": "Drivetrain Noise / Service",
            "customer_notes": "Drivetrain service: diagnose noise, inspect chain/cassette/chainrings, adjust shifting, clean/lubricate as needed.",
            "internal_notes": "Measure chain wear and note cassette/chainring condition.",
            "items": [
                ("Labor", "Drivetrain diagnostic/service labor", 1, 65.00, 1),
                ("Part", "Chain", 1, 35.00, 1),
            ],
        },
        {
            "name": "Wheel True",
            "customer_notes": "Wheel truing: inspect rim/spokes and true wheel as safely as possible.",
            "internal_notes": "Note if rim damage prevents a perfect true.",
            "items": [
                ("Labor", "Wheel truing labor", 1, 45.00, 1),
            ],
        },
        {
            "name": "Bike Assembly",
            "customer_notes": "Bike assembly: assemble, adjust, safety check, and test ride.",
            "internal_notes": "Document missing parts, damage, or manufacturer issues.",
            "items": [
                ("Labor", "Bike assembly labor", 1, 300.00, 1),
            ],
        },
    ]

    now = datetime.now().isoformat(timespec="seconds")
    for template in defaults:
        cur = execute(
            """
            INSERT INTO templates (name, default_customer_notes, default_internal_notes, default_tax_rate, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                template["name"],
                template["customer_notes"],
                template["internal_notes"],
                DEFAULT_TAX_RATE,
                now,
            ),
            returning="template_id",
        )
        template_id = cur.lastrowid
        for category, description, qty, unit_price, taxable in template["items"]:
            execute(
                """
                INSERT INTO template_line_items (template_id, category, description, quantity, unit_price, taxable)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (template_id, category, description, qty, unit_price, taxable),
            )


# -----------------------------------------------------------------------------
# Business logic helpers
# -----------------------------------------------------------------------------


@dataclass
class Totals:
    subtotal: float
    taxable_subtotal: float
    tax: float
    total: float


def money(value: float | int | None) -> str:
    return f"${float(value or 0):,.2f}"


def now_iso() -> str:
    return datetime.now().isoformat(timespec="seconds")


def normalize_line_items(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return pd.DataFrame(columns=LINE_ITEM_COLUMNS)

    out = df.copy()
    for col in LINE_ITEM_COLUMNS:
        if col not in out.columns:
            out[col] = None

    out = out[LINE_ITEM_COLUMNS]
    out["category"] = out["category"].fillna("Labor").astype(str)
    out["description"] = out["description"].fillna("").astype(str)
    out["quantity"] = pd.to_numeric(out["quantity"], errors="coerce").fillna(1.0)
    out["unit_price"] = pd.to_numeric(out["unit_price"], errors="coerce").fillna(0.0)
    out["taxable"] = out["taxable"].fillna(True).astype(bool)
    out = out[out["description"].str.strip() != ""]
    return out


def calculate_totals(line_items: pd.DataFrame, tax_rate: float) -> Totals:
    df = normalize_line_items(line_items)
    if df.empty:
        return Totals(0.0, 0.0, 0.0, 0.0)

    line_totals = df["quantity"] * df["unit_price"]
    subtotal = float(line_totals.sum())
    taxable_subtotal = float(line_totals[df["taxable"]].sum())
    tax = round(taxable_subtotal * float(tax_rate), 2)
    return Totals(
        subtotal=round(subtotal, 2),
        taxable_subtotal=round(taxable_subtotal, 2),
        tax=tax,
        total=round(subtotal + tax, 2),
    )


def get_customers() -> pd.DataFrame:
    return query_df("SELECT * FROM customers ORDER BY name")


def get_bikes_for_customer(customer_id: int) -> pd.DataFrame:
    return query_df(
        "SELECT * FROM bikes WHERE customer_id = ? ORDER BY nickname, brand_model",
        (customer_id,),
    )


def get_templates() -> pd.DataFrame:
    return query_df("SELECT * FROM templates ORDER BY name")


def get_template_line_items(template_id: int) -> pd.DataFrame:
    return query_df(
        """
        SELECT category, description, quantity, unit_price, taxable
        FROM template_line_items
        WHERE template_id = ?
        ORDER BY template_line_item_id
        """,
        (template_id,),
    )


def template_summary_df(templates: pd.DataFrame) -> pd.DataFrame:
    rows = []
    for _, template in templates.iterrows():
        items = get_template_line_items(int(template["template_id"]))
        totals = calculate_totals(items, DEFAULT_TAX_RATE)
        rows.append(
            {
                "name": template["name"],
                "total_price": totals.total,
            }
        )
    return pd.DataFrame(rows)


def get_job_line_items(job_id: int) -> pd.DataFrame:
    return query_df(
        """
        SELECT category, description, quantity, unit_price, taxable
        FROM job_line_items
        WHERE job_id = ?
        ORDER BY line_item_id
        """,
        (job_id,),
    )


def create_customer(name: str, email: str, phone: str, notes: str) -> int:
    cur = execute(
        """
        INSERT INTO customers (name, email, phone, notes, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (name.strip(), email.strip(), phone.strip(), notes.strip(), now_iso()),
        returning="customer_id",
    )
    return int(cur.lastrowid)


def update_customer(customer_id: int, name: str, email: str, phone: str, notes: str) -> None:
    execute(
        """
        UPDATE customers
        SET name = ?, email = ?, phone = ?, notes = ?
        WHERE customer_id = ?
        """,
        (name.strip(), email.strip(), phone.strip(), notes.strip(), customer_id),
    )


def create_bike(
    customer_id: int,
    nickname: str,
    brand_model: str,
    color: str,
    bike_type: Any,
    notes: str,
) -> int:
    cur = execute(
        """
        INSERT INTO bikes (customer_id, nickname, brand_model, color, bike_type, notes, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            customer_id,
            clean_text(nickname),
            clean_text(brand_model),
            clean_text(color),
            clean_text(bike_type),
            clean_text(notes),
            now_iso(),
        ),
        returning="bike_id",
    )
    return int(cur.lastrowid)


def create_job_order(
    customer_id: int,
    bike_id: int | None,
    template_id: int | None,
    status: str,
    intake_notes: str,
    diagnosis_notes: str,
    internal_notes: str,
    customer_notes: str,
    tax_rate: float,
    payment_status: str,
    line_items: pd.DataFrame,
) -> int:
    timestamp = now_iso()
    cur = execute(
        """
        INSERT INTO job_orders (
            job_number, customer_id, bike_id, template_id, date_created, status,
            intake_notes, diagnosis_notes, internal_notes, customer_notes,
            tax_rate, payment_status, created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            None,
            customer_id,
            bike_id,
            template_id,
            date.today().isoformat(),
            status,
            intake_notes.strip(),
            diagnosis_notes.strip(),
            internal_notes.strip(),
            customer_notes.strip(),
            tax_rate,
            payment_status,
            timestamp,
            timestamp,
        ),
        returning="job_id",
    )
    job_id = int(cur.lastrowid)
    job_number = f"JO-{date.today().strftime('%Y%m%d')}-{job_id:04d}"
    execute("UPDATE job_orders SET job_number = ? WHERE job_id = ?", (job_number, job_id))

    df = normalize_line_items(line_items)
    for _, row in df.iterrows():
        execute(
            """
            INSERT INTO job_line_items (job_id, category, description, quantity, unit_price, taxable)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                job_id,
                str(row["category"]),
                str(row["description"]),
                float(row["quantity"]),
                float(row["unit_price"]),
                int(bool(row["taxable"])),
            ),
        )
    return job_id


def get_job_detail(job_id: int) -> dict[str, Any] | None:
    row = query_one(
        """
        SELECT
            j.*,
            c.name AS customer_name,
            c.email AS customer_email,
            c.phone AS customer_phone,
            b.nickname AS bike_nickname,
            b.brand_model AS bike_brand_model,
            b.color AS bike_color,
            b.bike_type AS bike_type,
            t.name AS template_name
        FROM job_orders j
        JOIN customers c ON c.customer_id = j.customer_id
        LEFT JOIN bikes b ON b.bike_id = j.bike_id
        LEFT JOIN templates t ON t.template_id = j.template_id
        WHERE j.job_id = ?
        """,
        (job_id,),
    )
    if not row:
        return None
    return dict(row)


def job_summary_df() -> pd.DataFrame:
    jobs = query_df(
        """
        SELECT
            j.job_id,
            j.job_number,
            j.date_created,
            j.status,
            j.payment_status,
            c.name AS customer,
            c.email AS email,
            COALESCE(b.nickname, b.brand_model, '') AS bike,
            COALESCE(t.name, '') AS template,
            j.tax_rate,
            j.zettle_receipt_number,
            j.zettle_receipt_url
        FROM job_orders j
        JOIN customers c ON c.customer_id = j.customer_id
        LEFT JOIN bikes b ON b.bike_id = j.bike_id
        LEFT JOIN templates t ON t.template_id = j.template_id
        ORDER BY j.job_id DESC
        """
    )
    if jobs.empty:
        return jobs

    totals = []
    for job_id in jobs["job_id"]:
        detail = get_job_detail(int(job_id))
        items = get_job_line_items(int(job_id))
        tax_rate = float(detail["tax_rate"] if detail else DEFAULT_TAX_RATE)
        t = calculate_totals(items, tax_rate)
        totals.append(
            {
                "job_id": job_id,
                "subtotal": t.subtotal,
                "tax": t.tax,
                "total": t.total,
            }
        )
    total_df = pd.DataFrame(totals)
    return jobs.merge(total_df, on="job_id", how="left")


def update_payment_status(
    job_id: int,
    payment_status: str,
    zettle_receipt_number: str,
    zettle_receipt_url: str,
    paypal_invoice_id: str,
    paypal_invoice_url: str,
) -> None:
    execute(
        """
        UPDATE job_orders
        SET payment_status = ?,
            zettle_receipt_number = ?,
            zettle_receipt_url = ?,
            paypal_invoice_id = ?,
            paypal_invoice_url = ?,
            updated_at = ?
        WHERE job_id = ?
        """,
        (
            payment_status,
            zettle_receipt_number.strip(),
            zettle_receipt_url.strip(),
            paypal_invoice_id.strip(),
            paypal_invoice_url.strip(),
            now_iso(),
            job_id,
        ),
    )


def format_bike(detail: dict[str, Any]) -> str:
    pieces = []
    if detail.get("bike_nickname"):
        pieces.append(str(detail["bike_nickname"]))
    if detail.get("bike_brand_model"):
        pieces.append(str(detail["bike_brand_model"]))
    if detail.get("bike_color"):
        pieces.append(str(detail["bike_color"]))
    if detail.get("bike_type"):
        pieces.append(str(detail["bike_type"]))
    return " — ".join(pieces) if pieces else "Bike not specified"


def line_items_to_text(items: pd.DataFrame) -> str:
    df = normalize_line_items(items)
    if df.empty:
        return "No line items entered."
    lines = []
    for _, row in df.iterrows():
        qty = float(row["quantity"])
        unit = float(row["unit_price"])
        total = qty * unit
        qty_label = f"{qty:g} × " if qty != 1 else ""
        lines.append(f"- {row['description']} — {qty_label}{money(unit)} = {money(total)}")
    return "\n".join(lines)


def generate_customer_invoice_text(job_id: int) -> str:
    detail = get_job_detail(job_id)
    if not detail:
        return "Job not found."
    items = get_job_line_items(job_id)
    totals = calculate_totals(items, float(detail["tax_rate"]))
    bike = format_bike(detail)

    notes = detail.get("customer_notes") or ""
    note_block = f"\nService notes:\n{notes.strip()}\n" if notes.strip() else ""

    return f"""Invoice / Service Summary
{detail['job_number']}
{detail['date_created']}

Customer: {detail['customer_name']}
Bike: {bike}

Line items:
{line_items_to_text(items)}

Subtotal: {money(totals.subtotal)}
Sales tax ({float(detail['tax_rate']) * 100:.2f}%): {money(totals.tax)}
Total: {money(totals.total)}
{note_block}
Payment status: {detail['payment_status']}
""".strip()


def generate_email_text(job_id: int) -> tuple[str, str, str]:
    detail = get_job_detail(job_id)
    if not detail:
        return "", "", ""
    items = get_job_line_items(job_id)
    totals = calculate_totals(items, float(detail["tax_rate"]))
    bike = format_bike(detail)
    first_name = str(detail["customer_name"]).split()[0] if detail.get("customer_name") else "there"
    subject = f"Bike service invoice - {bike}"

    notes = detail.get("customer_notes") or ""
    notes_block = f"\nService notes:\n{notes.strip()}\n" if notes.strip() else ""

    body = f"""Hi {first_name},

Your bike service summary is below.

Job: {detail['job_number']}
Bike: {bike}

{line_items_to_text(items)}

Subtotal: {money(totals.subtotal)}
Sales tax ({float(detail['tax_rate']) * 100:.2f}%): {money(totals.tax)}
Total: {money(totals.total)}
{notes_block}
Thanks,
Precision Bicycle Services
""".strip()
    to = detail.get("customer_email") or ""
    return to, subject, body


def generate_zettle_entry_summary(job_id: int) -> str:
    detail = get_job_detail(job_id)
    if not detail:
        return "Job not found."
    items = get_job_line_items(job_id)
    totals = calculate_totals(items, float(detail["tax_rate"]))

    return f"""Zettle / PayPal POS entry summary
{detail['job_number']}
Customer: {detail['customer_name']}
Bike: {format_bike(detail)}

Enter line items:
{line_items_to_text(items)}

Expected subtotal: {money(totals.subtotal)}
Taxable amount: {money(totals.taxable_subtotal)}
Sales tax ({float(detail['tax_rate']) * 100:.2f}%): {money(totals.tax)}
Expected total: {money(totals.total)}

After payment, record the Zettle receipt number/link on this job.
""".strip()


def create_template(
    name: str,
    default_customer_notes: str,
    default_internal_notes: str,
    default_tax_rate: float,
    line_items: pd.DataFrame,
) -> int:
    cur = execute(
        """
        INSERT INTO templates (name, default_customer_notes, default_internal_notes, default_tax_rate, created_at)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            name.strip(),
            default_customer_notes.strip(),
            default_internal_notes.strip(),
            default_tax_rate,
            now_iso(),
        ),
        returning="template_id",
    )
    template_id = int(cur.lastrowid)
    df = normalize_line_items(line_items)
    for _, row in df.iterrows():
        execute(
            """
            INSERT INTO template_line_items (template_id, category, description, quantity, unit_price, taxable)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                template_id,
                str(row["category"]),
                str(row["description"]),
                float(row["quantity"]),
                float(row["unit_price"]),
                int(bool(row["taxable"])),
            ),
        )
    return template_id


def update_template(
    template_id: int,
    name: str,
    default_customer_notes: str,
    default_internal_notes: str,
    default_tax_rate: float,
    line_items: pd.DataFrame,
) -> None:
    execute(
        """
        UPDATE templates
        SET name = ?,
            default_customer_notes = ?,
            default_internal_notes = ?,
            default_tax_rate = ?
        WHERE template_id = ?
        """,
        (
            name.strip(),
            default_customer_notes.strip(),
            default_internal_notes.strip(),
            default_tax_rate,
            template_id,
        ),
    )
    execute("DELETE FROM template_line_items WHERE template_id = ?", (template_id,))

    df = normalize_line_items(line_items)
    for _, row in df.iterrows():
        execute(
            """
            INSERT INTO template_line_items (template_id, category, description, quantity, unit_price, taxable)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                template_id,
                str(row["category"]),
                str(row["description"]),
                float(row["quantity"]),
                float(row["unit_price"]),
                int(bool(row["taxable"])),
            ),
        )


# -----------------------------------------------------------------------------
# Streamlit UI helpers
# -----------------------------------------------------------------------------


def line_item_editor(default_df: pd.DataFrame, key: str) -> pd.DataFrame:
    df = normalize_line_items(default_df)
    if df.empty:
        df = pd.DataFrame(
            [
                {
                    "category": "Labor",
                    "description": "Bicycle Service Labor",
                    "quantity": 1.0,
                    "unit_price": 0.0,
                    "taxable": True,
                }
            ]
        )

    return st.data_editor(
        df,
        key=key,
        num_rows="dynamic",
        use_container_width=True,
        hide_index=True,
        column_config={
            "category": st.column_config.SelectboxColumn(
                "Type",
                options=["Labor", "Part", "Fee", "Discount", "Other"],
                required=True,
            ),
            "description": st.column_config.TextColumn("Description", required=True),
            "quantity": st.column_config.NumberColumn("Qty", min_value=0.0, step=1.0),
            "unit_price": st.column_config.NumberColumn("Unit price", min_value=-10000.0, step=1.0, format="$%.2f"),
            "taxable": st.column_config.CheckboxColumn("Taxable"),
        },
    )


def customer_selector() -> tuple[str, int | None]:
    customers = get_customers()
    options = ["+ New customer"]
    id_lookup: dict[str, int] = {}
    for _, row in customers.iterrows():
        label = f"{row['name']}"
        if row.get("email"):
            label += f" — {row['email']}"
        options.append(label)
        id_lookup[label] = int(row["customer_id"])

    choice = st.selectbox("Customer", options, key="customer_choice")
    if choice == "+ New customer":
        return choice, None
    return choice, id_lookup[choice]


def bike_selector(customer_id: int | None) -> tuple[str, int | None]:
    if customer_id is None:
        st.info("Create/select a customer first. You can still save a new bike with the new customer below.")
        return "+ New bike", None

    bikes = get_bikes_for_customer(customer_id)
    options = ["+ New bike", "No bike / unknown"]
    id_lookup: dict[str, int] = {}
    for _, row in bikes.iterrows():
        label = row["nickname"] or row["brand_model"] or f"Bike #{row['bike_id']}"
        extra = " / ".join(str(x) for x in [row["brand_model"], row["color"], row["bike_type"]] if x)
        if extra:
            label += f" — {extra}"
        options.append(label)
        id_lookup[label] = int(row["bike_id"])

    choice = st.selectbox("Bike", options, key="bike_choice")
    if choice in ["+ New bike", "No bike / unknown"]:
        return choice, None
    return choice, id_lookup[choice]


# -----------------------------------------------------------------------------
# Pages
# -----------------------------------------------------------------------------


def page_new_job() -> None:
    st.header("New Job Order")
    st.caption("Fast workflow: customer → bike → template → line items → invoice text.")

    st.subheader("1. Customer")
    customer_choice, existing_customer_id = customer_selector()

    if existing_customer_id is None:
        col1, col2 = st.columns(2)
        with col1:
            new_customer_name = st.text_input("New customer name *", key="new_customer_name")
            new_customer_email = st.text_input("Email", key="new_customer_email")
        with col2:
            new_customer_phone = st.text_input("Phone", key="new_customer_phone")
            new_customer_notes = st.text_area("Customer notes", height=80, key="new_customer_notes")
    else:
        c = query_one("SELECT * FROM customers WHERE customer_id = ?", (existing_customer_id,))
        new_customer_name = c["name"] if c else ""
        new_customer_email = c["email"] if c else ""
        new_customer_phone = c["phone"] if c else ""
        new_customer_notes = c["notes"] if c else ""
        st.success(f"Selected customer: {new_customer_name}")

    st.subheader("2. Bike")
    bike_choice, existing_bike_id = bike_selector(existing_customer_id)

    if existing_bike_id is None and bike_choice != "No bike / unknown":
        col1, col2 = st.columns(2)
        with col1:
            new_bike_nickname = st.text_input("Bike nickname", key="new_bike_nickname")
            new_bike_brand_model = st.text_input("Brand/model",  key="new_bike_brand_model")
        with col2:
            new_bike_color = st.text_input("Color", key="new_bike_color")
            new_bike_type = st.multiselect("Bike type", options=["Road", "Mountain","Hybrid", "Gravel", "E-Bike"], key="new_bike_type")
        new_bike_notes = st.text_area("Bike notes", height=80, key="new_bike_notes")
    else:
        new_bike_nickname = ""
        new_bike_brand_model = ""
        new_bike_color = ""
        new_bike_type = ""
        new_bike_notes = ""
        if existing_bike_id is not None:
            st.success("Selected saved bike.")

    st.subheader("3. Template + job details")
    templates = get_templates()
    template_by_id = {
        int(row["template_id"]): row
        for _, row in templates.iterrows()
        if str(row.get("template_id", "")).isdigit()
    }
    template_options = [None] + list(template_by_id.keys())
    template_choice = st.selectbox(
        "Job template",
        template_options,
        format_func=lambda template_id: "No template"
        if template_id is None
        else str(template_by_id[template_id]["name"]),
        key="template_choice",
    )

    selected_template_id = None
    default_customer_notes = ""
    default_internal_notes = ""
    tax_rate = DEFAULT_TAX_RATE
    default_items = pd.DataFrame(columns=LINE_ITEM_COLUMNS)

    if template_choice is not None:
        template_row = template_by_id[int(template_choice)]
        selected_template_id = int(template_choice)
        default_customer_notes = str(template_row["default_customer_notes"] or "")
        default_internal_notes = str(template_row["default_internal_notes"] or "")
        default_items = get_template_line_items(selected_template_id)

    col1, col2 = st.columns(2)
    with col1:
        status = st.selectbox("Job status", STATUS_OPTIONS, index=0)
    with col2:
        payment_status = st.selectbox("Payment status", PAYMENT_STATUS_OPTIONS, index=0)

    intake_notes = st.text_area("Intake notes / customer request", placeholder="What did the customer ask for?", height=100)
    diagnosis_notes = st.text_area("Diagnosis notes", placeholder="What did you find?", height=100)
    internal_notes = st.text_area("Internal mechanic notes", value=default_internal_notes, height=100)
    customer_notes = st.text_area("Customer-facing service notes", value=default_customer_notes, height=120)

    st.subheader("4. Line items")
    edited_items = line_item_editor(default_items, key=f"line_items_{template_choice or 'none'}")
    totals = calculate_totals(edited_items, tax_rate)

    c1, c2, c3 = st.columns(3)
    c1.metric("Subtotal", money(totals.subtotal))
    c2.metric(f"Tax ({tax_rate * 100:.2f}%)", money(totals.tax))
    c3.metric("Total", money(totals.total))

    st.divider()
    save = st.button("Save job order and generate invoice text", type="primary", use_container_width=True)

    if save:
        if existing_customer_id is None and not new_customer_name.strip():
            st.error("Customer name is required.")
            return

        # Create customer if needed.
        customer_id = existing_customer_id
        if customer_id is None:
            customer_id = create_customer(
                new_customer_name,
                new_customer_email,
                new_customer_phone,
                new_customer_notes,
            )

        # Create bike if requested.
        bike_id = existing_bike_id
        if bike_id is None and bike_choice != "No bike / unknown":
            has_bike_info = any(
                clean_text(x)
                for x in [new_bike_nickname, new_bike_brand_model, new_bike_color, new_bike_type, new_bike_notes]
            )
            if has_bike_info:
                bike_id = create_bike(
                    customer_id,
                    new_bike_nickname,
                    new_bike_brand_model,
                    new_bike_color,
                    new_bike_type,
                    new_bike_notes,
                )

        cleaned_items = normalize_line_items(edited_items)
        if cleaned_items.empty:
            st.error("Add at least one line item before saving.")
            return

        job_id = create_job_order(
            customer_id=customer_id,
            bike_id=bike_id,
            template_id=selected_template_id,
            status=status,
            intake_notes=intake_notes,
            diagnosis_notes=diagnosis_notes,
            internal_notes=internal_notes,
            customer_notes=customer_notes,
            tax_rate=tax_rate,
            payment_status=payment_status,
            line_items=cleaned_items,
        )
        st.success(f"Saved job order JO #{job_id}.")
        st.session_state["last_job_id"] = job_id

    if "last_job_id" in st.session_state:
        st.subheader("Invoice / email output")
        job_id = int(st.session_state["last_job_id"])
        render_invoice_outputs(job_id)


def render_invoice_outputs(job_id: int) -> None:
    invoice_text = generate_customer_invoice_text(job_id)
    to, subject, email_body = generate_email_text(job_id)
    zettle_summary = generate_zettle_entry_summary(job_id)

    tab1, tab2, tab3 = st.tabs(["Customer invoice text", "Email draft", "Zettle entry summary"])
    with tab1:
        st.text_area("Copy/paste invoice text", invoice_text, height=360)
    with tab2:
        st.text_input("To", value=to, disabled=True)
        st.text_input("Subject", value=subject, disabled=True)
        st.text_area("Email body", email_body, height=360)
        mailto = f"mailto:{quote(to)}?subject={quote(subject)}&body={quote(email_body)}"
        st.markdown(f"[Open email draft]({mailto})")
    with tab3:
        st.text_area("Copy/paste into Zettle/PayPal workflow", zettle_summary, height=360)


def page_customers_bikes() -> None:
    st.header("Customers + Bikes")

    tab1, tab2 = st.tabs(["Customer list", "Add customer/bike"])

    with tab1:
        customers = get_customers()
        if customers.empty:
            st.info("No customers yet.")
        else:
            st.dataframe(customers, use_container_width=True, hide_index=True)
            selected_id = st.selectbox(
                "View customer history",
                customers["customer_id"].tolist(),
                format_func=lambda cid: customers.loc[customers["customer_id"] == cid, "name"].iloc[0],
            )
            bikes = get_bikes_for_customer(int(selected_id))
            jobs = query_df(
                """
                SELECT j.job_number, j.date_created, j.status, j.payment_status,
                       COALESCE(b.nickname, b.brand_model, '') AS bike,
                       COALESCE(t.name, '') AS template
                FROM job_orders j
                LEFT JOIN bikes b ON b.bike_id = j.bike_id
                LEFT JOIN templates t ON t.template_id = j.template_id
                WHERE j.customer_id = ?
                ORDER BY j.job_id DESC
                """,
                (int(selected_id),),
            )
            st.subheader("Bikes")
            st.dataframe(bikes, use_container_width=True, hide_index=True)
            st.subheader("Job history")
            st.dataframe(jobs, use_container_width=True, hide_index=True)

    with tab2:
        with st.form("add_customer_form"):
            st.subheader("Add customer")
            name = st.text_input("Name *")
            email = st.text_input("Email")
            phone = st.text_input("Phone")
            notes = st.text_area("Customer notes")
            add_bike_now = st.checkbox("Add a bike for this customer now", value=True)

            if add_bike_now:
                st.subheader("Bike")
                bike_nickname = st.text_input("Bike nickname")
                brand_model = st.text_input("Brand/model")
                color = st.text_input("Color")
                bike_type = st.text_input("Bike type")
                bike_notes = st.text_area("Bike notes")
            else:
                bike_nickname = brand_model = color = bike_type = bike_notes = ""

            submitted = st.form_submit_button("Save customer")
            if submitted:
                if not name.strip():
                    st.error("Name is required.")
                else:
                    customer_id = create_customer(name, email, phone, notes)
                    if add_bike_now:
                        create_bike(customer_id, bike_nickname, brand_model, color, bike_type, bike_notes)
                    st.success("Customer saved.")


def page_jobs_invoices() -> None:
    st.header("Jobs + Invoices")
    jobs = job_summary_df()
    if jobs.empty:
        st.info("No job orders yet.")
        return

    search = st.text_input("Search customer, bike, job number, template")
    filtered = jobs.copy()
    if search.strip():
        q = search.strip().lower()
        mask = pd.Series(False, index=filtered.index)
        for col in ["job_number", "customer", "email", "bike", "template", "status", "payment_status"]:
            mask = mask | filtered[col].fillna("").astype(str).str.lower().str.contains(q)
        filtered = filtered[mask]

    st.dataframe(
        filtered[
            [
                "job_number",
                "date_created",
                "customer",
                "bike",
                "template",
                "status",
                "payment_status",
                "subtotal",
                "tax",
                "total",
                "zettle_receipt_number",
            ]
        ],
        use_container_width=True,
        hide_index=True,
    )

    selected_job_id = st.selectbox(
        "Select job to view/generate invoice",
        filtered["job_id"].tolist(),
        format_func=lambda jid: filtered.loc[filtered["job_id"] == jid, "job_number"].iloc[0],
    )

    detail = get_job_detail(int(selected_job_id))
    if detail:
        st.subheader(f"{detail['job_number']} — {detail['customer_name']}")
        render_invoice_outputs(int(selected_job_id))

        st.subheader("Payment / receipt tracking")
        with st.form("payment_update_form"):
            payment_status = st.selectbox(
                "Payment status",
                PAYMENT_STATUS_OPTIONS,
                index=PAYMENT_STATUS_OPTIONS.index(detail["payment_status"])
                if detail["payment_status"] in PAYMENT_STATUS_OPTIONS
                else 0,
            )
            zettle_receipt_number = st.text_input("Zettle receipt number", value=detail.get("zettle_receipt_number") or "")
            zettle_receipt_url = st.text_input("Zettle receipt URL", value=detail.get("zettle_receipt_url") or "")
            paypal_invoice_id = st.text_input("PayPal invoice ID", value=detail.get("paypal_invoice_id") or "")
            paypal_invoice_url = st.text_input("PayPal invoice URL", value=detail.get("paypal_invoice_url") or "")
            if st.form_submit_button("Update payment details"):
                update_payment_status(
                    int(selected_job_id),
                    payment_status,
                    zettle_receipt_number,
                    zettle_receipt_url,
                    paypal_invoice_id,
                    paypal_invoice_url,
                )
                st.success("Payment details updated.")
                st.rerun()


def page_templates() -> None:
    st.header("Templates")
    st.caption("Templates make job orders faster and more consistent.")

    templates = get_templates()
    st.subheader("Existing templates")
    if templates.empty:
        st.info("No templates yet. Create one below.")
    else:
        st.dataframe(
            template_summary_df(templates),
            use_container_width=True,
            hide_index=True,
            column_config={
                "name": st.column_config.TextColumn("Template"),
                "total_price": st.column_config.NumberColumn("Total price", format="$%.2f"),
            },
        )

        with st.container(border=True):
            st.subheader("Select a template to edit")
            st.caption("Changes here affect future job orders that use this template. Existing jobs stay unchanged.")
            selected_template_id = st.selectbox(
                "Template",
                templates["template_id"].tolist(),
                format_func=lambda tid: templates.loc[templates["template_id"] == tid, "name"].iloc[0],
                key="edit_template_selector",
            )

            template_row = templates.loc[templates["template_id"] == selected_template_id].iloc[0]
            existing_items = get_template_line_items(int(selected_template_id))

            with st.form(f"edit_template_form_{selected_template_id}"):
                edit_name = st.text_input("Template name *", value=str(template_row["name"]))
                edit_customer_notes = st.text_area(
                    "Default customer-facing notes",
                    value=str(template_row["default_customer_notes"] or ""),
                )
                edit_internal_notes = st.text_area(
                    "Default internal notes",
                    value=str(template_row["default_internal_notes"] or ""),
                )
                edited_template_items = line_item_editor(
                    existing_items,
                    key=f"edit_template_items_{selected_template_id}",
                )

                edit_submitted = st.form_submit_button("Save template changes")
                if edit_submitted:
                    if not edit_name.strip():
                        st.error("Template name is required.")
                    else:
                        try:
                            update_template(
                                int(selected_template_id),
                                edit_name,
                                edit_customer_notes,
                                edit_internal_notes,
                                DEFAULT_TAX_RATE,
                                edited_template_items,
                            )
                            st.success("Template updated.")
                            st.rerun()
                        except Exception as error:
                            if is_unique_violation(error):
                                st.error("A template with that name already exists.")
                            else:
                                raise

    st.divider()
    st.subheader("Create new template")
    with st.form("new_template_form"):
        name = st.text_input("Template name *")
        default_customer_notes = st.text_area("Default customer-facing notes")
        default_internal_notes = st.text_area("Default internal notes")
        template_items = st.data_editor(
            pd.DataFrame(
                [
                    {
                        "category": "Labor",
                        "description": "Bicycle Service Labor",
                        "quantity": 1.0,
                        "unit_price": 0.0,
                        "taxable": True,
                    }
                ]
            ),
            num_rows="dynamic",
            use_container_width=True,
            hide_index=True,
            column_config={
                "category": st.column_config.SelectboxColumn(
                    "Type",
                    options=["Labor", "Part", "Fee", "Discount", "Other"],
                    required=True,
                ),
                "unit_price": st.column_config.NumberColumn("Unit price", format="$%.2f"),
                "taxable": st.column_config.CheckboxColumn("Taxable"),
            },
        )
        submitted = st.form_submit_button("Save template")
        if submitted:
            if not name.strip():
                st.error("Template name is required.")
            else:
                try:
                    create_template(
                        name,
                        default_customer_notes,
                        default_internal_notes,
                        DEFAULT_TAX_RATE,
                        template_items,
                    )
                    st.success("Template saved.")
                    st.rerun()
                except Exception as error:
                    if is_unique_violation(error):
                        st.error("A template with that name already exists.")
                    else:
                        raise


def page_dashboard_exports() -> None:
    st.header("Dashboard + Exports")
    jobs = job_summary_df()
    if jobs.empty:
        st.info("No data yet.")
        return

    total_revenue = jobs["total"].fillna(0).sum()
    unpaid = jobs.loc[jobs["payment_status"] == "Unpaid", "total"].fillna(0).sum()
    paid = jobs.loc[jobs["payment_status"] == "Paid", "total"].fillna(0).sum()

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("Jobs", len(jobs))
    c2.metric("Total value", money(total_revenue))
    c3.metric("Paid", money(paid))
    c4.metric("Unpaid", money(unpaid))

    by_template = jobs.groupby("template", dropna=False)["total"].sum().reset_index().sort_values("total", ascending=False)
    st.subheader("Value by template")
    st.bar_chart(by_template.set_index("template"))

    st.subheader("Export data")
    st.download_button(
        "Download jobs CSV",
        data=jobs.to_csv(index=False),
        file_name="job_orders_export.csv",
        mime="text/csv",
        use_container_width=True,
    )

    customers = get_customers()
    st.download_button(
        "Download customers CSV",
        data=customers.to_csv(index=False),
        file_name="customers_export.csv",
        mime="text/csv",
        use_container_width=True,
    )

    all_line_items = query_df(
        """
        SELECT j.job_number, c.name AS customer, li.*
        FROM job_line_items li
        JOIN job_orders j ON j.job_id = li.job_id
        JOIN customers c ON c.customer_id = j.customer_id
        ORDER BY li.line_item_id DESC
        """
    )
    st.download_button(
        "Download line items CSV",
        data=all_line_items.to_csv(index=False),
        file_name="job_line_items_export.csv",
        mime="text/csv",
        use_container_width=True,
    )


# -----------------------------------------------------------------------------
# App entry point
# -----------------------------------------------------------------------------


def main() -> None:
    st.set_page_config(page_title=APP_TITLE, page_icon="🚲", layout="wide")
    if not require_password():
        return

    init_db()

    st.title("Precison Bicycle Services: Order and Invoicing System")
    st.caption("Templates, customer/bike history, invoice text, and Zettle/PayPal entry summaries.")

    page = st.sidebar.radio(
        "Go to",
        [
            "New Job Order",
            "Jobs + Invoices",
            "Customers + Bikes",
            "Templates",
            "Dashboard + Exports",
        ],
    )

    if page == "New Job Order":
        page_new_job()
    elif page == "Jobs + Invoices":
        page_jobs_invoices()
    elif page == "Customers + Bikes":
        page_customers_bikes()
    elif page == "Templates":
        page_templates()
    elif page == "Dashboard + Exports":
        page_dashboard_exports()


if __name__ == "__main__":
    main()
