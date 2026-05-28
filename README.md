# Bike Repair Revenue Dashboard

A Streamlit MVP demo for a small bike repair mechanic. The app uses fake data to show revenue trends, job volume, repair mix, average ticket size, customer value, repeat customers, payment methods, and raw transaction/job data.

## Files

- `app.py` — main Streamlit app
- `requirements.txt` — Python dependencies for local use and Streamlit Community Cloud
- `.streamlit/config.toml` — optional app theme/config
- `.gitignore` — basic Python/Streamlit ignores

## Run locally

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\Scripts\activate
pip install -r requirements.txt
streamlit run app.py
```

## Deploy on Streamlit Community Cloud

1. Create a new GitHub repository.
2. Add these files to the repository root.
3. Push to GitHub.
4. Go to `share.streamlit.io`.
5. Create/deploy a new app from the GitHub repository.
6. Use `app.py` as the main file path.

## Notes for adapting to a real mechanic

The current app generates fake data in `generate_fake_data()`. For a real client, replace that function with a CSV upload, Google Sheets connection, or exports from the shop's card/payment system.

A minimum real CSV would need columns like:

```text
date, customer, repair_type, labor_revenue, parts_revenue, sales_tax, discount, total_revenue, payment_method
```

Good next upgrades:

- CSV upload button
- Mapping tool for different payment export column names
- Saved client data file or lightweight database
- Monthly PDF/exportable report
- Benchmarks for average ticket and revenue by repair category
- Basic customer lookup
