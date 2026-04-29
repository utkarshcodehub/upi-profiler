# UPI Spending Personality Profiler

**Day 02 of the 21-Day Build Challenge**

🔗 **Live:** [upi-profiler.streamlit.app](https://upi-profiler.streamlit.app)

---

## What It Does

Upload your PhonePe or Google Pay transaction statement and get a spending personality — not just categories and totals, but a behavioural profile. Are you an impulse buyer? A late-night spender? Does your spending spike at month-end?

Designed specifically around how Indians actually spend via UPI — merchants, peer transfers, recharges, subscriptions.

---

## Features

- **Spending personality archetype** — assigned based on patterns (e.g. Night Owl Spender, Subscription Hoarder, Social Payer)
- **Merchant category breakdown** — food, transport, entertainment, utilities, transfers
- **Time-of-day and day-of-week analysis** — when you actually spend
- **Month-end vs month-start behaviour** — do you spend more when you just got paid?
- **Peer vs merchant split** — how much goes to people vs apps/shops

---

## Stack

| Tool | Use |
|------|-----|
| Python | Core logic |
| Streamlit | UI and deployment |
| Plotly | Charts |
| Pandas | PDF/CSV parsing and analysis |

---

## How to Run Locally

```bash
git clone https://github.com/yourusername/21-day-build-challenge
cd day-02-upi-profiler
pip install -r requirements.txt
streamlit run app.py
```

### Getting Your UPI Statement

- **PhonePe:** Profile → Transaction History → Download Statement (PDF)
- **Google Pay:** Activity → Download statement

> **Note:** PhonePe PDFs are sometimes image-based or password-protected. The app handles text-extractable PDFs. CSV exports from bank apps tend to be more reliable.

---

## What I Learned

- PDF parsing for Indian payment apps is unreliable — PhonePe in particular exports image-based PDFs frequently, which defeats text extraction
- Streamlit Cloud requires an explicit `requirements.txt` — learned this the hard way on deployment
- Spending personality assignment is more interesting when it combines time + category + frequency signals rather than just totals
