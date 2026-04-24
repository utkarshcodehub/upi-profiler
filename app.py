import streamlit as st
import pandas as pd
import plotly.graph_objects as go
import pdfplumber
import re
from io import BytesIO
from datetime import datetime
import random

st.set_page_config(page_title="UPI Spending Profiler", page_icon="💸", layout="wide")

st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;600;700;800&display=swap');
html, body, [class*="css"] { font-family: 'Inter', sans-serif; }
.block-container { padding: 2rem 3rem; max-width: 1100px; }
.hero { background: linear-gradient(135deg,#1a0533,#0d1b2a); border:1px solid rgba(139,92,246,.3);
    border-radius:20px; padding:2.5rem; text-align:center; margin-bottom:2rem; }
.hero h1 { font-size:2.5rem; font-weight:800; color:#fff; margin:0; }
.hero p  { color:#94a3b8; font-size:1rem; margin-top:.4rem; }
.pcard { background:linear-gradient(135deg,#2d1b69,#1e3a5f); border:1px solid rgba(139,92,246,.5);
    border-radius:16px; padding:2rem; text-align:center; margin:1.5rem 0; }
.pname { font-size:1.8rem; font-weight:800; color:#a78bfa; margin:.4rem 0; }
.pdesc { color:#cbd5e1; font-size:.95rem; line-height:1.6; }
.mcard { background:#111827; border:1px solid #1f2937; border-radius:12px; padding:1.2rem 1.5rem; }
.mlabel { color:#6b7280; font-size:.75rem; font-weight:700; text-transform:uppercase; letter-spacing:.05em; }
.mval { color:#f9fafb; font-size:1.5rem; font-weight:700; margin-top:.2rem; }
.msub { color:#9ca3af; font-size:.8rem; }
.ibox { background:#111827; border-left:3px solid #8b5cf6; border-radius:0 8px 8px 0;
    padding:1rem 1.2rem; margin:.5rem 0; color:#e2e8f0; font-size:.9rem; }
.stitle { font-size:1.1rem; font-weight:700; color:#f1f5f9; margin:1.5rem 0 .8rem; }
.good { color:#10b981; } .warn { color:#f59e0b; } .bad { color:#ef4444; }
</style>
""", unsafe_allow_html=True)

# ── CATEGORIZER ─────────────────────────────────────────────────────────────

CATS = {
    'Food & Drinks':  ['swiggy','zomato','food','restaurant','cafe','pizza','burger','dhaba',
                       'biryani','chai','bake','eat','domino','kfc','mcdonalds','blinkit','zepto'],
    'Transport':      ['ola','uber','rapido','metro','irctc','train','bus','cab','petrol',
                       'fuel','auto','rickshaw','flight','indigo','spice','redbus'],
    'Shopping':       ['amazon','flipkart','myntra','ajio','meesho','nykaa','store','mart',
                       'bazar','reliance','dmart','bigbasket','jiomart'],
    'Entertainment':  ['netflix','hotstar','spotify','youtube','prime','zee','sonyliv',
                       'movie','pvr','inox','bookmyshow','game'],
    'Subscriptions':  ['recharge','jio','airtel','vodafone',' vi ','bsnl','broadband','tataplay'],
    'Rent & Housing': ['rent','pg','hostel','society','maintenance','housing','flat'],
    'Education':      ['college','university','fees','tuition','course','udemy','coaching','byju'],
    'Health':         ['pharmacy','medical','hospital','doctor','apollo','1mg','netmeds','medplus'],
    'Utilities':      ['electricity','water','gas','lpg','cylinder','bill','bescom'],
}

def categorize(desc):
    d = desc.lower()
    for cat, kws in CATS.items():
        if any(k in d for k in kws):
            return cat
    return 'Transfers / Other'

# ── PDF PARSER ───────────────────────────────────────────────────────────────

AMOUNT_RE = re.compile(r'INR\s*([\d,]+\.?\d*)')
DATE_RE   = re.compile(
    r'(\d{1,2}[\/\-]\d{1,2}[\/\-]\d{2,4}'
    r'|(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}'
    r'|\d{4}[\/\-]\d{2}[\/\-]\d{2})',
    re.IGNORECASE
)
TIME_RE   = re.compile(r'\d{1,2}:\d{2}\s*(?:AM|PM|am|pm)?')
TYPE_RE   = re.compile(r'\b(Credit|Debit)\b', re.IGNORECASE)

DATE_FMTS = [
    "%b %d, %Y %I:%M %p", "%b %d, %Y %I:%M%p", "%b %d, %Y",
    "%d/%m/%Y %H:%M",     "%d/%m/%Y",
    "%d-%m-%Y %H:%M",     "%d-%m-%Y",
    "%Y-%m-%d %H:%M:%S",  "%Y-%m-%d",
    "%d %b %Y",
]

def try_date(s):
    s = re.sub(r'\s+', ' ', s.strip())
    for f in DATE_FMTS:
        try: return datetime.strptime(s, f)
        except: pass
    return None

def parse_pdf(pdf_bytes, password=None):
    """
    Extract transactions from any bank / UPI statement PDF.
    Uses word-level bbox reconstruction so column layout doesn't matter.
    """
    open_kw = {'password': password} if password else {}
    rows = []

    try:
        with pdfplumber.open(BytesIO(pdf_bytes), **open_kw) as pdf:
            for page in pdf.pages:
                # Reconstruct rows by grouping words at same vertical position
                words = page.extract_words(x_tolerance=5, y_tolerance=5)
                buckets = {}
                for w in words:
                    y = round(w['top'] / 6) * 6
                    buckets.setdefault(y, []).append(w)
                for y in sorted(buckets):
                    line = ' '.join(w['text'] for w in sorted(buckets[y], key=lambda w: w['x0']))
                    rows.append(line)
    except Exception as e:
        msg = str(e).lower()
        if 'password' in msg or 'encrypt' in msg:
            raise ValueError("WRONG_PASSWORD")
        raise

    transactions = []
    skip = {'transaction','id','utr','no','ref','credited','debited','narration',
            'date','type','amount','balance','sl','page','statement','particulars'}

    for row in rows:
        row = row.strip()
        if len(row) < 8: continue

        # Need at least a date and an amount
        dm = DATE_RE.search(row)
        am = AMOUNT_RE.search(row)
        if not dm or not am: continue

        date_str = dm.group(0)
        tm       = TIME_RE.search(row[dm.end():dm.end()+20])
        dt_str   = f"{date_str} {tm.group(0)}" if tm else date_str
        dt       = try_date(dt_str.strip())

        amount   = float(am.group(1).replace(',', ''))
        if amount <= 0: continue

        typ_m    = TYPE_RE.search(row)
        txn_type = typ_m.group(1).capitalize() if typ_m else ''

        # Build description
        desc = row
        desc = desc.replace(date_str, '')
        if tm: desc = desc.replace(tm.group(0), '')
        desc = re.sub(r'INR\s*[\d,]+\.?\d*', '', desc)
        desc = re.sub(r'\bT\d{10,}\b', '', desc)   # Transaction IDs
        desc = re.sub(r'\b\d{8,}\b', '', desc)      # UTR / long numbers
        desc = re.sub(r'\bXX\w+\b', '', desc)       # masked account
        if typ_m: desc = desc[:typ_m.start()] + desc[typ_m.end():]
        words = [w for w in desc.split() if w.lower() not in skip and len(w) > 1]
        desc  = ' '.join(words).strip(' .,:-')[:70]
        if not desc: desc = "Payment"

        if not txn_type:
            dl = desc.lower()
            txn_type = 'Credit' if any(w in dl for w in ['received','refund','cashback','salary']) else 'Debit'

        transactions.append({'date': dt, 'description': desc, 'type': txn_type, 'amount': amount})

    # Deduplicate
    seen, unique = set(), []
    for t in transactions:
        key = (str(t['date'])[:16], round(t['amount'],2), t['type'])
        if key not in seen:
            seen.add(key)
            unique.append(t)

    return pd.DataFrame(unique) if unique else pd.DataFrame(columns=['date','description','type','amount'])

# ── GPAY CSV PARSER ──────────────────────────────────────────────────────────

def parse_csv(csv_bytes):
    df = pd.read_csv(BytesIO(csv_bytes))
    df.columns = [c.strip().lower().replace(' ','_') for c in df.columns]

    def find_col(*keys):
        return next((c for c in df.columns if any(k in c for k in keys)), None)

    date_c = find_col('date','time','timestamp')
    desc_c = find_col('description','narration','merchant','details','note','name')
    amt_c  = find_col('amount','inr','value','debit','credit')
    type_c = find_col('type','transaction_type','cr_dr')

    out = pd.DataFrame()
    out['date']        = pd.to_datetime(df[date_c], errors='coerce') if date_c else pd.NaT
    out['description'] = df[desc_c].astype(str) if desc_c else 'Transaction'
    raw_amt            = df[amt_c].astype(str).str.replace('[₹,INRRs. ]','',regex=True) if amt_c else '0'
    out['amount']      = pd.to_numeric(raw_amt, errors='coerce').abs().fillna(0)
    if type_c:
        out['type'] = df[type_c].astype(str).apply(
            lambda x: 'Credit' if any(w in x.lower() for w in ['cr','credit','received']) else 'Debit')
    else:
        out['type'] = 'Debit'

    return out[out['amount'] > 0]

# ── DEMO DATA ────────────────────────────────────────────────────────────────

def demo():
    random.seed(42)
    items = [
        ('Swiggy Order','Debit',150,600), ('Zomato Food','Debit',180,750),
        ('Ola Cab','Debit',70,280),       ('Uber Ride','Debit',90,350),
        ('Amazon Order','Debit',250,1800),('Netflix Sub','Debit',649,649),
        ('Jio Recharge','Debit',299,299), ('Paid to Friend','Debit',200,2000),
        ('Received','Credit',500,5000),   ('Rent','Debit',8000,8000),
        ('Apollo Pharmacy','Debit',120,700),('BookMyShow','Debit',300,600),
        ('Salary Credit','Credit',15000,20000),('Flipkart Order','Debit',400,2500),
        ('Rapido Bike','Debit',40,120),   ('Hotstar','Debit',299,299),
    ]
    base = datetime(2025, 1, 1)
    rows = []
    for _ in range(85):
        m = random.choice(items)
        rows.append({
            'date': base + pd.Timedelta(days=random.randint(0,115), hours=random.randint(8,23)),
            'description': m[0], 'type': m[1],
            'amount': round(random.uniform(m[2], m[3]), 2)
        })
    df = pd.DataFrame(rows)
    df['category'] = df['description'].apply(categorize)
    return df

# ── CHARTS ───────────────────────────────────────────────────────────────────

C = ['#8b5cf6','#3b82f6','#10b981','#f59e0b','#ef4444','#ec4899','#14b8a6','#f97316']

def donut(labels, vals, title):
    fig = go.Figure(go.Pie(labels=labels, values=vals, hole=0.55,
        marker_colors=C, textinfo='percent',
        hovertemplate='%{label}<br>₹%{value:,.0f}<extra></extra>'))
    fig.update_layout(title=dict(text=title, font_color='#f1f5f9', font_size=13),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font_color='#94a3b8', margin=dict(t=35,b=5,l=5,r=5), height=300)
    return fig

def hbar(labels, vals, title, color='#8b5cf6'):
    fig = go.Figure(go.Bar(x=vals, y=labels, orientation='h', marker_color=color,
        hovertemplate='%{y}<br>₹%{x:,.0f}<extra></extra>'))
    fig.update_layout(title=dict(text=title, font_color='#f1f5f9', font_size=13),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font_color='#94a3b8', xaxis=dict(gridcolor='#1f2937'),
        yaxis=dict(gridcolor='#1f2937'), margin=dict(t=35,b=5,l=5,r=5), height=300)
    return fig

def linechart(x, y, title):
    fig = go.Figure(go.Scatter(x=x, y=y, mode='lines+markers',
        line=dict(color='#8b5cf6', width=2), marker=dict(color='#a78bfa', size=7),
        fill='tozeroy', fillcolor='rgba(139,92,246,0.1)',
        hovertemplate='%{x}<br>₹%{y:,.0f}<extra></extra>'))
    fig.update_layout(title=dict(text=title, font_color='#f1f5f9', font_size=13),
        paper_bgcolor='rgba(0,0,0,0)', plot_bgcolor='rgba(0,0,0,0)',
        font_color='#94a3b8', xaxis=dict(gridcolor='#1f2937'),
        yaxis=dict(gridcolor='#1f2937'), margin=dict(t=35,b=5,l=5,r=5), height=300)
    return fig

# ── PERSONALITY ──────────────────────────────────────────────────────────────

PERSONALITIES = [
    ('🍕','The Foodie','warn',
     lambda c,d: c.get('Food & Drinks',0)>30,
     "Food isn't fuel — it's your hobby. Your UPI reads like a restaurant column. You probably tell yourself you'll cook \"next week.\"",
     "7-day home-cooking streak. See what you actually save."),
    ('🚗','The Nomad','warn',
     lambda c,d: c.get('Transport',0)>25,
     "Always moving. Ola, Uber, Metro — your wallet knows your routes better than Maps. Delhi traffic may have won.",
     "Calculate monthly transport spend. A metro pass might cut it 40%."),
    ('📱','The Subscriber','bad',
     lambda c,d: c.get('Subscriptions',0)+c.get('Entertainment',0)>20,
     "Netflix. Spotify. Hotstar. Probably one OTT you forgot you pay for. More streaming bought than hours available.",
     "Audit subscriptions now. Kill anything unopened in 2 weeks."),
    ('🛍️','The Shopaholic','bad',
     lambda c,d: c.get('Shopping',0)>30,
     "Amazon and Flipkart are your stress response. The doorstep package is your serotonin hit.",
     "48-hour rule: add to cart, wait. If you still want it, buy it."),
    ('⚖️','The Balanced One','good',
     lambda c,d: max(c.values(),default=0)<35 and len(c)>=3,
     "Spending spread across categories, nothing dominating. Either genuinely disciplined, or diversifying your chaos. Data says disciplined.",
     "Good. Next: track your savings rate, not just spending."),
    ('💸','The Big Mover','warn',
     lambda c,d: (d['amount'].mean()>5000 if not d.empty else False),
     "Large, infrequent payments. You move money in chunks — rent, bulk purchases, transfers. UPI is a fire hose, not a drip.",
     "Break down large transfers. Know exactly where each chunk landed."),
    ('🎲','The Scatter','warn',
     lambda c,d: True,
     "Small transactions across many merchants with no clear pattern. Reactive spending — whatever the moment needs, you pay.",
     "Pick 3 categories to actively track this month. Awareness alone reduces spend."),
]

def get_personality(cat_pct, debits):
    for emoji, name, verdict, cond, desc, tip in PERSONALITIES:
        if cond(cat_pct, debits):
            return emoji, name, verdict, desc, tip
    return PERSONALITIES[-1]

# ── RENDER ───────────────────────────────────────────────────────────────────

def render(df):
    debits  = df[df['type']=='Debit'].copy()
    credits = df[df['type']=='Credit'].copy()

    total_spent    = debits['amount'].sum()
    total_received = credits['amount'].sum()
    n_debits       = len(debits)
    avg            = total_spent / n_debits if n_debits else 0

    cat_spend = debits.groupby('category')['amount'].sum().sort_values(ascending=False)
    cat_pct   = (cat_spend/total_spent*100).to_dict() if total_spent else {}

    emoji, name, verdict, desc, tip = get_personality(cat_pct, debits)

    st.markdown(f"""<div class="pcard">
        <div style="font-size:3.5rem">{emoji}</div>
        <div class="pname">{name}</div>
        <div class="pdesc">{desc}</div>
        <br><div class="{verdict}" style="font-weight:600;font-size:.9rem;">💡 {tip}</div>
    </div>""", unsafe_allow_html=True)

    # Metrics
    st.markdown('<div class="stitle">📊 Your Numbers</div>', unsafe_allow_html=True)
    c1,c2,c3,c4 = st.columns(4)
    top_cat = cat_spend.index[0] if len(cat_spend) else '—'
    with c1: st.markdown(f'<div class="mcard"><div class="mlabel">Total Spent</div><div class="mval">₹{total_spent:,.0f}</div><div class="msub">{n_debits} transactions</div></div>', unsafe_allow_html=True)
    with c2: st.markdown(f'<div class="mcard"><div class="mlabel">Total Received</div><div class="mval">₹{total_received:,.0f}</div><div class="msub">{len(credits)} transactions</div></div>', unsafe_allow_html=True)
    with c3: st.markdown(f'<div class="mcard"><div class="mlabel">Avg Transaction</div><div class="mval">₹{avg:,.0f}</div><div class="msub">per debit</div></div>', unsafe_allow_html=True)
    with c4: st.markdown(f'<div class="mcard"><div class="mlabel">Top Category</div><div class="mval">{top_cat.split("/")[0].strip()}</div><div class="msub">{cat_pct.get(top_cat,0):.1f}% of spend</div></div>', unsafe_allow_html=True)

    # Charts row 1
    st.markdown('<div class="stitle">🗂️ Where Your Money Goes</div>', unsafe_allow_html=True)
    ch1, ch2 = st.columns(2)
    with ch1:
        if len(cat_spend):
            st.plotly_chart(donut(cat_spend.index.tolist(), cat_spend.values.tolist(), "By Category"), use_container_width=True)
    with ch2:
        dm = debits.dropna(subset=['date']).copy()
        if not dm.empty:
            dm['month'] = dm['date'].dt.to_period('M')
            mo = dm.groupby('month')['amount'].sum()
            st.plotly_chart(linechart(mo.index.astype(str).tolist(), mo.values.tolist(), "Monthly Trend"), use_container_width=True)

    # Charts row 2
    st.markdown('<div class="stitle">🔍 Deeper Patterns</div>', unsafe_allow_html=True)
    ch3, ch4 = st.columns(2)
    with ch3:
        dd = debits.dropna(subset=['date']).copy()
        if not dd.empty:
            dd['day'] = dd['date'].dt.day_name()
            day_order = ['Monday','Tuesday','Wednesday','Thursday','Friday','Saturday','Sunday']
            ds = dd.groupby('day')['amount'].sum().reindex(day_order, fill_value=0)
            st.plotly_chart(hbar(ds.index.tolist(), ds.values.tolist(), f"Spend by Day (worst: {ds.idxmax()})", '#ef4444'), use_container_width=True)
    with ch4:
        mc = debits['description'].value_counts()
        repeat_rate = round(len(mc[mc>1])/len(mc)*100) if len(mc) else 0
        top6 = mc.head(6)
        st.plotly_chart(hbar(top6.index.tolist()[::-1], top6.values.tolist()[::-1], f"Top Merchants (repeat rate {repeat_rate}%)", '#3b82f6'), use_container_width=True)

    # Insights
    st.markdown('<div class="stitle">🧠 Honest Insights</div>', unsafe_allow_html=True)
    insights = []
    if not debits.empty:
        big = debits.loc[debits['amount'].idxmax()]
        insights.append(f"💣 Biggest payment: <b>₹{big['amount']:,.0f}</b> to <b>{big['description']}</b> — {big['amount']/total_spent*100:.1f}% of all spending in one shot.")
    fp = cat_pct.get('Food & Drinks',0)
    if fp > 20:
        insights.append(f"🍔 <b>{fp:.1f}%</b> on food (₹{cat_spend.get('Food & Drinks',0):,.0f}). Cooking 3x/week could save ~₹{cat_spend.get('Food & Drinks',0)*0.4:,.0f}.")
    st_ent = cat_spend.get('Subscriptions',0) + cat_spend.get('Entertainment',0)
    if st_ent > 300:
        insights.append(f"📺 Subscriptions + Entertainment: <b>₹{st_ent:,.0f}</b> leaving automatically. When did you last audit these?")
    net = total_received - total_spent
    if net < 0:
        insights.append(f"⚠️ Spent <b>₹{abs(net):,.0f} more than received</b>. That gap came from savings or another account.")
    else:
        insights.append(f"✅ Positive flow — received <b>₹{net:,.0f} more than spent</b>.")
    for ins in insights:
        st.markdown(f'<div class="ibox">{ins}</div>', unsafe_allow_html=True)

    with st.expander(f"📋 All {len(df)} transactions"):
        disp = df.copy()
        if disp['date'].notna().any():
            disp['date'] = disp['date'].dt.strftime('%d %b %Y %H:%M').fillna('—')
        disp['amount'] = disp['amount'].apply(lambda x: f"₹{x:,.2f}")
        cols = [c for c in ['date','description','category','type','amount'] if c in disp.columns]
        st.dataframe(disp[cols], use_container_width=True, height=320)

# ── MAIN ─────────────────────────────────────────────────────────────────────

st.markdown("""<div class="hero">
    <h1>💸 UPI Spending Profiler</h1>
    <p>PhonePe · Paytm · GPay · HDFC · ICICI · SBI · Axis — any Indian bank statement</p>
</div>""", unsafe_allow_html=True)

tab_pdf, tab_csv, tab_demo = st.tabs(["📄 PDF Statement", "📊 GPay CSV", "▶ Demo"])
df = None

with tab_pdf:
    up  = st.file_uploader("Upload your statement PDF", type=['pdf'])
    pwd = st.text_input("PDF password (if protected)",type="password",
                        placeholder="PhonePe → mobile number | Paytm → DOB DDMMYYYY | Leave blank if none")
    if up:
        with st.spinner("Reading PDF..."):
            try:
                df = parse_pdf(up.read(), password=pwd or None)
                if df.empty:
                    st.error("No transactions found. This usually means the PDF is image-based (scanned) rather than text-based — those can't be parsed without OCR. Try downloading a fresh statement from the app.")
                else:
                    df['category'] = df['description'].apply(categorize)
                    st.success(f"✅ Found {len(df)} transactions")
            except ValueError as e:
                if 'WRONG_PASSWORD' in str(e):
                    st.error("Wrong password.\n- PhonePe → 10-digit mobile number\n- Paytm → date of birth as DDMMYYYY\n- Banks → usually DOB or account number")
                else:
                    st.error(str(e))
            except Exception as e:
                st.error(f"Could not read this PDF: {e}")

with tab_csv:
    st.caption("Google Pay → Profile → Manage Account → Data & Privacy → Download your data → Google Pay")
    uc = st.file_uploader("Upload GPay CSV export", type=['csv'])
    if uc:
        try:
            df = parse_csv(uc.read())
            if df.empty:
                st.error("No transactions found in CSV. Paste the first 2 rows here and we'll fix the column mapping.")
            else:
                df['category'] = df['description'].apply(categorize)
                st.success(f"✅ {len(df)} transactions loaded")
        except Exception as e:
            st.error(f"CSV error: {e}")

with tab_demo:
    if st.button("Load demo data", use_container_width=True):
        df = demo()
        st.success("✅ 85 demo transactions loaded")

if df is not None and not df.empty:
    render(df)
elif df is None:
    st.markdown("""<div style="background:#0f172a;border:2px dashed #334155;border-radius:16px;
        padding:2.5rem;text-align:center;margin-top:1rem">
        <div style="font-size:3rem">📄</div>
        <div style="color:#f1f5f9;font-size:1.1rem;font-weight:600;margin:.5rem 0">Upload a statement above or try the demo</div>
        <div style="color:#64748b;font-size:.9rem">Processed locally — your data never leaves your machine.</div>
    </div>""", unsafe_allow_html=True)