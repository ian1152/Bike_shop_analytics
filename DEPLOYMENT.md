# Deployment

This Streamlit app can run in two database modes:

- Local development: uses `invoice_app.db` next to `invoice_app.py`.
- Hosted production: uses Supabase Postgres when `DATABASE_URL` is set.

## Supabase

1. Open the Supabase project dashboard.
2. Go to **Project Settings > Database**.
3. Copy the **Session pooler** connection string for a long-running Streamlit host, or the **Transaction pooler** string if your host only supports short-lived/serverless-style connections.
4. Replace `[YOUR-PASSWORD]` with the database password.
5. Make sure the final URL includes SSL. If Supabase gives you `?pgbouncer=true`, replace it with `?sslmode=require` for this Python app, or append `&sslmode=require`.

```text
?sslmode=require
```

Example shape:

```text
postgresql://postgres.PROJECT_REF:PASSWORD@aws-1-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require
```

Do not commit the real password to the repo.

## Local Test Against Supabase

For local development, put your real Supabase password in:

```text
.streamlit/secrets.toml
```

Use this shape:

```toml
DATABASE_URL = "postgresql://postgres.hzpigukyqbijuzpvprrj:YOUR_PASSWORD@aws-1-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require"
APP_PASSWORD = "choose-a-strong-app-password"
```

The real `secrets.toml` file is ignored by git. Keep `.streamlit/secrets.example.toml` as the shareable template.

You can also test by exporting the environment variable manually:

```bash
export DATABASE_URL='postgresql://postgres.PROJECT_REF:PASSWORD@aws-1-us-east-1.pooler.supabase.com:5432/postgres?sslmode=require'
streamlit run invoice_app.py
```

On first startup, the app creates the needed tables and seeds default job templates.

## Host Configuration

Set this environment variable in the hosting provider:

```text
DATABASE_URL
APP_PASSWORD
```

Use this start command:

```bash
streamlit run invoice_app.py --server.address 0.0.0.0 --server.port $PORT
```

If the host does not provide `$PORT`, use `8501`.
