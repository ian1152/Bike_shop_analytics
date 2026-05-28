import streamlit as st
import pandas as pd
import numpy as np
import altair as alt
from datetime import timedelta

st.set_page_config(
    page_title="Bike Repair Revenue Dashboard",
    page_icon="🚲",
    layout="wide",
)


# -----------------------------
# Fake demo data
# -----------------------------
@st.cache_data
def generate_fake_data(seed: int = 42) -> pd.DataFrame:
    """Generate fake repair/payment data for a small bike mechanic demo."""
    rng = np.random.default_rng(seed)

    start = pd.Timestamp.today().normalize() - pd.DateOffset(months=18)
    end = pd.Timestamp.today().normalize()
    days = pd.date_range(start, end, freq="D")

    customers = [
        "Alex M.", "Jordan P.", "Taylor R.", "Morgan S.", "Casey L.", "Riley T.",
        "Jamie K.", "Sam D.", "Chris W.", "Avery B.", "Cameron H.", "Drew N.",
        "Pat G.", "Quinn F.", "Robin C.", "Elliot V.", "Skyler J.", "Reese A.",
        "Devin O.", "Hayden Z.",
    ]

    repair_types = {
        "Basic tune-up": {"labor": (70, 120), "parts": (0, 35), "weight": 0.22},
        "Full tune-up": {"labor": (140, 240), "parts": (10, 80), "weight": 0.16},
        "Brake adjustment": {"labor": (35, 75), "parts": (0, 35), "weight": 0.13},
        "Brake pad replacement": {"labor": (45, 90), "parts": (18, 55), "weight": 0.10},
        "Flat repair": {"labor": (15, 35), "parts": (8, 20), "weight": 0.13},
        "Drivetrain clean/adjust": {"labor": (55, 110), "parts": (0, 45), "weight": 0.09},
        "Cable/housing replacement": {"labor": (50, 105), "parts": (18, 65), "weight": 0.07},
        "Wheel true": {"labor": (35, 85), "parts": (0, 20), "weight": 0.06},
        "Bottom bracket/headset": {"labor": (75, 160), "parts": (25, 95), "weight": 0.04},
    }

    payment_methods = ["Card", "Cash", "Venmo", "Zelle"]
    payment_probs = [0.68, 0.14, 0.13, 0.05]

    rows = []
    job_id = 1001

    for d in days:
        # More jobs in spring/summer, fewer in winter. Closed/slow most Sundays.
        month_factor = {
            1: 0.55, 2: 0.65, 3: 0.95, 4: 1.35, 5: 1.55, 6: 1.45,
            7: 1.25, 8: 1.15, 9: 1.25, 10: 1.05, 11: 0.75, 12: 0.55,
        }[d.month]
        dow_factor = 0.25 if d.dayofweek == 6 else (1.15 if d.dayofweek in [4, 5] else 1.0)
        expected_jobs = 2.2 * month_factor * dow_factor
        jobs_today = rng.poisson(expected_jobs)

        for _ in range(jobs_today):
            repair = rng.choice(list(repair_types.keys()), p=[v["weight"] for v in repair_types.values()])
            spec = repair_types[repair]

            labor = round(rng.uniform(*spec["labor"]), 2)
            parts = round(max(0, rng.uniform(*spec["parts"])), 2)

            # Occasional larger repair ticket.
            if rng.random() < 0.06:
                labor *= rng.uniform(1.4, 2.4)
                parts *= rng.uniform(1.3, 2.8)

            discount = 0
            if rng.random() < 0.07:
                discount = round(rng.uniform(5, 25), 2)

            tax = round(parts * 0.06, 2)
            total = round(labor + parts + tax - discount, 2)

            # About 18% of jobs are one-time/new customers.
            customer = rng.choice(customers)
            if rng.random() < 0.18:
                customer = f"New Customer {job_id}"

            rows.append({
                "job_id": job_id,
                "date": d,
                "customer": customer,
                "repair_type": repair,
                "labor_revenue": round(labor, 2),
                "parts_revenue": round(parts, 2),
                "sales_tax": tax,
                "discount": discount,
                "total_revenue": total,
                "payment_method": rng.choice(payment_methods, p=payment_probs),
            })
            job_id += 1

    df = pd.DataFrame(rows)
    df["date"] = pd.to_datetime(df["date"])
    df["month"] = df["date"].dt.to_period("M").dt.to_timestamp()
    df["week"] = df["date"].dt.to_period("W").apply(lambda r: r.start_time)
    df["day_name"] = df["date"].dt.day_name()
    return df


def money(x: float) -> str:
    return f"${x:,.0f}"


def pct(x: float) -> str:
    return f"{x:.1f}%"


def metric_delta(current, previous):
    if previous == 0 or pd.isna(previous):
        return None
    change = (current - previous) / previous * 100
    return f"{change:+.1f}% vs previous period"


def aggregate_by_period(df: pd.DataFrame, period: str) -> pd.DataFrame:
    if period == "Daily":
        key = "date"
    elif period == "Weekly":
        key = "week"
    else:
        key = "month"

    out = (
        df.groupby(key, as_index=False)
        .agg(
            revenue=("total_revenue", "sum"),
            labor_revenue=("labor_revenue", "sum"),
            parts_revenue=("parts_revenue", "sum"),
            jobs=("job_id", "nunique"),
            customers=("customer", "nunique"),
            avg_ticket=("total_revenue", "mean"),
        )
        .rename(columns={key: "period"})
        .sort_values("period")
    )
    return out


def bar_chart(df, x, y, tooltip, title=None):
    return (
        alt.Chart(df)
        .mark_bar()
        .encode(
            x=alt.X(x, sort="-y"),
            y=alt.Y(y),
            tooltip=tooltip,
        )
        .properties(height=340, title=title)
    )


def line_chart(df, x, y, tooltip, title=None):
    return (
        alt.Chart(df)
        .mark_line(point=True)
        .encode(
            x=alt.X(x),
            y=alt.Y(y),
            tooltip=tooltip,
        )
        .properties(height=340, title=title)
    )


# -----------------------------
# App
# -----------------------------
st.title("🚲 Bike Repair Revenue Dashboard")
st.caption("MVP demo using fake payment and repair-job data. Designed for a small repair-only bike mechanic.")

raw = generate_fake_data()

with st.sidebar:
    st.header("Filters")

    min_date = raw["date"].min().date()
    max_date = raw["date"].max().date()
    default_start = max_date - timedelta(days=180)

    date_range = st.date_input(
        "Date range",
        value=(default_start, max_date),
        min_value=min_date,
        max_value=max_date,
    )

    if len(date_range) == 2:
        start_date, end_date = date_range
    else:
        start_date, end_date = default_start, max_date

    period = st.selectbox("Chart period", ["Daily", "Weekly", "Monthly"], index=1)

    repair_filter = st.multiselect(
        "Repair types",
        sorted(raw["repair_type"].unique()),
        default=sorted(raw["repair_type"].unique()),
    )

    payment_filter = st.multiselect(
        "Payment methods",
        sorted(raw["payment_method"].unique()),
        default=sorted(raw["payment_method"].unique()),
    )

    st.divider()
    st.caption("Replace the fake data generator with a CSV upload or payment export later.")

mask = (
    (raw["date"].dt.date >= start_date)
    & (raw["date"].dt.date <= end_date)
    & (raw["repair_type"].isin(repair_filter))
    & (raw["payment_method"].isin(payment_filter))
)

df = raw.loc[mask].copy()

if df.empty:
    st.warning("No data matches the current filters.")
    st.stop()

# Previous equivalent period for deltas
selected_days = (pd.Timestamp(end_date) - pd.Timestamp(start_date)).days + 1
prev_start = pd.Timestamp(start_date) - pd.Timedelta(days=selected_days)
prev_end = pd.Timestamp(start_date) - pd.Timedelta(days=1)
prev = raw[
    (raw["date"] >= prev_start)
    & (raw["date"] <= prev_end)
    & (raw["repair_type"].isin(repair_filter))
    & (raw["payment_method"].isin(payment_filter))
]

# KPI calculations
revenue = df["total_revenue"].sum()
prev_revenue = prev["total_revenue"].sum()

jobs = df["job_id"].nunique()
prev_jobs = prev["job_id"].nunique()

avg_ticket = df["total_revenue"].mean()
prev_avg_ticket = prev["total_revenue"].mean() if not prev.empty else np.nan

customers = df["customer"].nunique()
prev_customers = prev["customer"].nunique()

labor_share = df["labor_revenue"].sum() / revenue * 100 if revenue else 0
parts_share = df["parts_revenue"].sum() / revenue * 100 if revenue else 0

c1, c2, c3, c4, c5 = st.columns(5)
c1.metric("Revenue", money(revenue), metric_delta(revenue, prev_revenue))
c2.metric("Jobs", f"{jobs:,}", metric_delta(jobs, prev_jobs))
c3.metric("Avg ticket", money(avg_ticket), metric_delta(avg_ticket, prev_avg_ticket))
c4.metric("Customers", f"{customers:,}", metric_delta(customers, prev_customers))
c5.metric("Labor share", pct(labor_share), f"Parts: {pct(parts_share)}")

st.divider()

tab1, tab2, tab3, tab4, tab5 = st.tabs([
    "Revenue trends",
    "Repair mix",
    "Customers",
    "Payments",
    "Raw data",
])

with tab1:
    st.subheader("Revenue and job volume over time")
    by_period = aggregate_by_period(df, period)

    col_a, col_b = st.columns(2)
    with col_a:
        st.altair_chart(
            line_chart(
                by_period,
                "period:T",
                "revenue:Q",
                ["period:T", alt.Tooltip("revenue:Q", format="$,.0f"), "jobs:Q", alt.Tooltip("avg_ticket:Q", format="$,.0f")],
                title=f"Revenue by {period.lower()} period",
            ),
            use_container_width=True,
        )
    with col_b:
        st.altair_chart(
            line_chart(
                by_period,
                "period:T",
                "jobs:Q",
                ["period:T", "jobs:Q", alt.Tooltip("revenue:Q", format="$,.0f"), alt.Tooltip("avg_ticket:Q", format="$,.0f")],
                title=f"Jobs by {period.lower()} period",
            ),
            use_container_width=True,
        )

    col_c, col_d = st.columns(2)
    with col_c:
        st.altair_chart(
            line_chart(
                by_period,
                "period:T",
                "avg_ticket:Q",
                ["period:T", alt.Tooltip("avg_ticket:Q", format="$,.0f"), "jobs:Q"],
                title="Average ticket over time",
            ),
            use_container_width=True,
        )
    with col_d:
        revenue_split = by_period[["period", "labor_revenue", "parts_revenue"]].melt(
            "period", var_name="revenue_type", value_name="amount"
        )
        st.altair_chart(
            alt.Chart(revenue_split)
            .mark_area()
            .encode(
                x="period:T",
                y=alt.Y("amount:Q", stack="zero"),
                color="revenue_type:N",
                tooltip=["period:T", "revenue_type:N", alt.Tooltip("amount:Q", format="$,.0f")],
            )
            .properties(height=340, title="Labor vs parts revenue"),
            use_container_width=True,
        )

    st.markdown("### Period summary")
    summary = by_period.copy()
    summary["revenue"] = summary["revenue"].map(lambda x: f"${x:,.0f}")
    summary["avg_ticket"] = summary["avg_ticket"].map(lambda x: f"${x:,.0f}")
    st.dataframe(summary, use_container_width=True, hide_index=True)

with tab2:
    st.subheader("Which repair categories drive revenue?")
    repair_summary = (
        df.groupby("repair_type", as_index=False)
        .agg(
            revenue=("total_revenue", "sum"),
            jobs=("job_id", "nunique"),
            avg_ticket=("total_revenue", "mean"),
            labor_revenue=("labor_revenue", "sum"),
            parts_revenue=("parts_revenue", "sum"),
        )
        .sort_values("revenue", ascending=False)
    )
    repair_summary["revenue_per_job"] = repair_summary["revenue"] / repair_summary["jobs"]

    col_a, col_b = st.columns(2)
    with col_a:
        st.altair_chart(
            bar_chart(
                repair_summary,
                "repair_type:N",
                "revenue:Q",
                ["repair_type:N", alt.Tooltip("revenue:Q", format="$,.0f"), "jobs:Q", alt.Tooltip("avg_ticket:Q", format="$,.0f")],
                title="Revenue by repair type",
            ),
            use_container_width=True,
        )
    with col_b:
        st.altair_chart(
            bar_chart(
                repair_summary.sort_values("jobs", ascending=False),
                "repair_type:N",
                "jobs:Q",
                ["repair_type:N", "jobs:Q", alt.Tooltip("revenue:Q", format="$,.0f"), alt.Tooltip("avg_ticket:Q", format="$,.0f")],
                title="Job count by repair type",
            ),
            use_container_width=True,
        )

    st.markdown("### Repair category table")
    display = repair_summary.copy()
    for col in ["revenue", "avg_ticket", "labor_revenue", "parts_revenue", "revenue_per_job"]:
        display[col] = display[col].map(lambda x: f"${x:,.0f}")
    st.dataframe(display, use_container_width=True, hide_index=True)

with tab3:
    st.subheader("Customer value and repeat work")
    customer_summary = (
        df.groupby("customer", as_index=False)
        .agg(
            revenue=("total_revenue", "sum"),
            jobs=("job_id", "nunique"),
            avg_ticket=("total_revenue", "mean"),
            first_visit=("date", "min"),
            last_visit=("date", "max"),
        )
        .sort_values("revenue", ascending=False)
    )
    customer_summary["repeat_customer"] = np.where(customer_summary["jobs"] > 1, "Repeat", "One-time")

    repeat_revenue = customer_summary.loc[customer_summary["jobs"] > 1, "revenue"].sum()
    repeat_share = repeat_revenue / customer_summary["revenue"].sum() * 100

    col_a, col_b, col_c = st.columns(3)
    col_a.metric("Top customer revenue", money(customer_summary["revenue"].max()))
    col_b.metric("Repeat customers", f"{(customer_summary['jobs'] > 1).sum():,}")
    col_c.metric("Revenue from repeat customers", pct(repeat_share))

    top_n = st.slider("Number of customers to show", 5, 25, 10)
    st.altair_chart(
        bar_chart(
            customer_summary.head(top_n),
            "customer:N",
            "revenue:Q",
            ["customer:N", alt.Tooltip("revenue:Q", format="$,.0f"), "jobs:Q", alt.Tooltip("avg_ticket:Q", format="$,.0f"), "last_visit:T"],
            title="Top customers by revenue",
        ),
        use_container_width=True,
    )

    display = customer_summary.copy()
    for col in ["revenue", "avg_ticket"]:
        display[col] = display[col].map(lambda x: f"${x:,.0f}")
    display["first_visit"] = display["first_visit"].dt.date
    display["last_visit"] = display["last_visit"].dt.date
    st.dataframe(display, use_container_width=True, hide_index=True)

with tab4:
    st.subheader("Payment method and transaction mix")
    payment_summary = (
        df.groupby("payment_method", as_index=False)
        .agg(
            revenue=("total_revenue", "sum"),
            jobs=("job_id", "nunique"),
            avg_ticket=("total_revenue", "mean"),
        )
        .sort_values("revenue", ascending=False)
    )
    payment_summary["revenue_share"] = payment_summary["revenue"] / payment_summary["revenue"].sum() * 100

    col_a, col_b = st.columns(2)
    with col_a:
        st.altair_chart(
            bar_chart(
                payment_summary,
                "payment_method:N",
                "revenue:Q",
                ["payment_method:N", alt.Tooltip("revenue:Q", format="$,.0f"), "jobs:Q", alt.Tooltip("avg_ticket:Q", format="$,.0f"), alt.Tooltip("revenue_share:Q", format=".1f")],
                title="Revenue by payment method",
            ),
            use_container_width=True,
        )
    with col_b:
        day_summary = (
            df.groupby("day_name", as_index=False)
            .agg(revenue=("total_revenue", "sum"), jobs=("job_id", "nunique"), avg_ticket=("total_revenue", "mean"))
        )
        day_order = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday", "Saturday", "Sunday"]
        day_summary["day_name"] = pd.Categorical(day_summary["day_name"], categories=day_order, ordered=True)
        day_summary = day_summary.sort_values("day_name")

        st.altair_chart(
            alt.Chart(day_summary)
            .mark_bar()
            .encode(
                x=alt.X("day_name:N", sort=day_order),
                y="revenue:Q",
                tooltip=["day_name:N", alt.Tooltip("revenue:Q", format="$,.0f"), "jobs:Q", alt.Tooltip("avg_ticket:Q", format="$,.0f")],
            )
            .properties(height=340, title="Revenue by day of week"),
            use_container_width=True,
        )

    st.markdown("### Payment method table")
    display = payment_summary.copy()
    display["revenue"] = display["revenue"].map(lambda x: f"${x:,.0f}")
    display["avg_ticket"] = display["avg_ticket"].map(lambda x: f"${x:,.0f}")
    display["revenue_share"] = display["revenue_share"].map(lambda x: f"{x:.1f}%")
    st.dataframe(display, use_container_width=True, hide_index=True)

with tab5:
    st.subheader("Underlying fake transaction/job data")
    st.caption("For a real first version, this could come from CSV exports from Square, Stripe, QuickBooks, Venmo, or a spreadsheet.")

    display_df = df.sort_values("date", ascending=False).copy()
    display_df["date"] = display_df["date"].dt.date
    st.dataframe(display_df, use_container_width=True, hide_index=True)

    csv = display_df.to_csv(index=False).encode("utf-8")
    st.download_button(
        "Download filtered data as CSV",
        data=csv,
        file_name="bike_repair_demo_data.csv",
        mime="text/csv",
    )

st.divider()
st.caption("MVP note: this demo intentionally avoids scheduling/workflow features. It focuses on payment data, repair categories, revenue trends, customer value, and job volume.")
