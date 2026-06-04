# Zettle Integration Plan

Status: planning only. Not implemented yet.

## Overview

This document captures potential PayPal Zettle integration work for the mechanic job order and invoicing app. The current app is a Streamlit web app hosted through Render, using Supabase Postgres for production data and a basic `APP_PASSWORD` gate for access control.

The first useful integration should reduce manual payment reconciliation, not replace Zettle as the point-of-sale app.

## Current App State

- `invoice_app.py` manages customers, bikes, job orders, templates, line items, invoice text, and payment status.
- Supabase stores app data when `DATABASE_URL` is configured.
- Render hosts the app for phone access.
- The app currently allows manual entry of Zettle receipt number, Zettle receipt URL, PayPal invoice ID, and PayPal invoice URL.

## Zettle API Capabilities

Useful Zettle capabilities to explore:

- Purchase API: read-only receipt/purchase data, including receipt number, timestamp, amount, products, and payment methods.
- Product Library API: create, retrieve, update, and delete products and variants in the Zettle product library.
- Inventory API: read and update stock balances for tracked product variants.
- Finance API: retrieve transaction, balance, payout, and fee-related information.
- Payment SDKs / Reader Connect: deeper payment-taking integrations, likely more involved than the current Streamlit app needs.

## Recommended Roadmap

### Phase 1: Purchase Sync + Job Matching

Add a Zettle sync page that fetches recent purchases and lets the mechanic link a purchase to an existing job order.

Expected behavior:

- Fetch recent Zettle purchases from the merchant account.
- Display unmatched purchases with date, amount, receipt number, and payment method.
- Suggest likely matching jobs by total amount and date.
- Allow the mechanic to manually link a purchase to a job.
- When linked, update the job payment status to `Paid` and store the Zettle receipt metadata.

### Phase 2: Product / Template Sync

Use the Product Library API to push common job templates and line items into Zettle.

Potential items:

- Basic tune-up labor
- Flat repair labor
- Wheel true labor
- Tube
- Chain
- Brake pads
- Cables and housing

The goal is to reduce duplicate typing between this app and Zettle.

### Phase 3: Parts Inventory

If the mechanic wants inventory tracking, sync common parts with Zettle inventory.

Potential behavior:

- Track stock levels for common parts.
- Show low-stock warnings in the app.
- Reconcile Zettle sales with parts used on jobs.

### Phase 4: Finance Dashboard

Use Zettle Finance API data to improve dashboard/reporting.

Potential metrics:

- Revenue by week/month.
- Paid vs unpaid jobs.
- Zettle fees.
- Payout history.
- Card vs PayPal/Venmo/cash mix.
- Average repair ticket.

### Later: Direct Payment Flow

Directly initiating in-person payments from this Streamlit app is not the recommended first step. Zettle payment-taking integrations generally require native iOS/Android SDKs or Reader Connect, which would be a larger product decision.

## Security And Credentials

- Do not commit Zettle client IDs, client secrets, access tokens, refresh tokens, or merchant credentials.
- Store secrets in Render environment variables and local `.streamlit/secrets.toml`.
- Store long-lived OAuth tokens server-side only.
- Never expose Zettle credentials in browser-visible code.
- Keep the existing `APP_PASSWORD` gate or replace it with a stronger login system before broad customer-data usage.

## Open Decisions

- Which Zettle developer app type is best for this single-merchant workflow?
- Does the mechanic want automatic matching only, manual matching only, or suggested matches with confirmation?
- How far back should purchase sync look by default?
- Should linked Zettle payments be editable/unlinkable?
- Should product/template sync be one-way from this app to Zettle, one-way from Zettle to this app, or bidirectional?
- Is parts inventory important enough for an early release?

## First Implementation Target

Build Phase 1 only:

- Add Zettle OAuth credential configuration.
- Add tables/columns needed to store Zettle purchase metadata and sync state.
- Add a Zettle sync page.
- Fetch recent purchases.
- Link selected purchases to job orders.
- Update payment status and receipt fields after linking.

Do not implement direct card charging in the first Zettle integration pass.
