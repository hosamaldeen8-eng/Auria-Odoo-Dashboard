"""
Auria — Live Operations Dashboard
Run:  streamlit run dashboard.py
"""

import xmlrpc.client
import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from datetime import date, datetime, timedelta

# ── Connection ────────────────────────────────────────────────────────────────
ODOO_URL = "https://odoo.auria.global"
ODOO_DB  = "Auria_Business"
ODOO_UID = 8
ODOO_PWD = "123456"

AURIA_GREEN  = "#1F3420"
AURIA_MID    = "#3B6D11"
AURIA_AMBER  = "#D4A853"
AURIA_RED    = "#A32D2D"
AURIA_LIGHT  = "#EAF3DE"

LOC_NAMES = {37: "SJ/RM-Raw", 38: "SJ/PKG", 39: "SJ/RTF", 55: "SJ/FG", 45: "HD/FG"}

USER_NAMES = {
    8: "Hussam", 18: "Abdullah", 29: "Ala' Deep", 9: "Alaa Oshah",
    15: "Marwan", 13: "Nasser", 27: "Khan", 11: "Wesal", 23: "Bader", 6: "Moad",
}

# ── Odoo helper ───────────────────────────────────────────────────────────────
@st.cache_resource
def get_models():
    return xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

def odoo(model, method, domain=None, kwargs=None):
    models = get_models()
    return models.execute_kw(
        ODOO_DB, ODOO_UID, ODOO_PWD,
        model, method,
        [domain or []],
        kwargs or {},
    )

# ── Data fetchers (cached per TTL) ────────────────────────────────────────────
@st.cache_data(ttl=60)
def fetch_all():
    today = str(date.today())
    thirty_ago = str(date.today() - timedelta(days=30))

    tasks = odoo("project.task", "search_read",
        [["active", "=", True]],
        {"fields": ["name","project_id","user_ids","priority","date_deadline","stage_id"], "limit": 300})

    mos = odoo("mrp.production", "search_read",
        [["state", "in", ["confirmed","progress"]]],
        {"fields": ["name","product_id","product_qty","state","date_start"], "limit": 50})

    quants = odoo("stock.quant", "search_read",
        [["location_id","in",[37,38,39,55,45]], ["quantity",">",0]],
        {"fields": ["product_id","location_id","quantity"], "limit": 400})

    acct = odoo("account.move.line", "read_group",
        [["account_id.code","in",
          ["11040100","11040150","11040200","11040300",
           "11040500","11040800","11040900","11060000","51010000"]],
         ["move_id.state","=","posted"]],
        {"fields":["account_id","balance:sum"], "groupby":["account_id"]})

    overdue = odoo("project.task", "search_read",
        [["date_deadline","<",today],["active","=",True]],
        {"fields":["name","project_id","user_ids","date_deadline","priority"], "limit": 100})

    projects = odoo("project.project","search_read",[],
        {"fields":["id","name","task_count"]})

    sales = odoo("sale.order","search_read",
        [["state","in",["sale","done"]],["date_order",">=",thirty_ago]],
        {"fields":["name","amount_total","date_order"],"limit":200})

    return dict(tasks=tasks, mos=mos, quants=quants, acct=acct,
                overdue=overdue, projects=projects, sales=sales, today=today)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Auria — Operations",
    page_icon="🌿",
    layout="wide",
    initial_sidebar_state="collapsed",
)

st.markdown(f"""
<style>
  [data-testid="stAppViewContainer"] {{ background: #f7f6f2; }}
  .header-bar {{
      background: {AURIA_GREEN}; color: white; padding: 14px 24px;
      border-radius: 12px; margin-bottom: 20px;
      display: flex; align-items: center; justify-content: space-between;
  }}
  .header-bar h1 {{ margin: 0; font-size: 20px; font-weight: 500; }}
  .header-bar small {{ opacity: .7; font-size: 12px; }}
  .alert-crit {{
      background: #FCEBEB; border-left: 4px solid {AURIA_RED};
      padding: 10px 14px; border-radius: 6px; margin-bottom: 8px; font-size: 13px;
  }}
  .alert-warn {{
      background: #FFF3CD; border-left: 4px solid {AURIA_AMBER};
      padding: 10px 14px; border-radius: 6px; margin-bottom: 8px; font-size: 13px;
  }}
  .alert-ok {{
      background: {AURIA_LIGHT}; border-left: 4px solid {AURIA_MID};
      padding: 10px 14px; border-radius: 6px; margin-bottom: 8px; font-size: 13px;
  }}
  .metric-label {{ font-size: 12px; color: #666; margin-bottom: 2px; }}
  .metric-val   {{ font-size: 26px; font-weight: 600; color: {AURIA_AMBER}; }}
  .metric-sub   {{ font-size: 11px; color: #888; }}
</style>
""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div class="header-bar">
  <div><h1>🌿 Auria — لوحة العمليات</h1><small>Live data from odoo.auria.global</small></div>
  <div style="text-align:right;font-size:13px;opacity:.85">
      {datetime.now().strftime("%A, %d %B %Y · %H:%M")}
  </div>
</div>
""", unsafe_allow_html=True)

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner("Fetching live data from Odoo…"):
    data = fetch_all()

tasks    = data["tasks"]
mos      = data["mos"]
quants   = data["quants"]
acct     = data["acct"]
overdue  = data["overdue"]
projects = data["projects"]
sales    = data["sales"]
today    = data["today"]

# Parse accounting
acct_map = {}
for a in acct:
    name = a["account_id"][1] if a["account_id"] else ""
    acct_map[name] = round(a.get("balance", 0) or 0, 2)

def bal(code):
    for k, v in acct_map.items():
        if k.startswith(code):
            return v
    return 0

raw_herbs = bal("11040100")
raw_oils  = bal("11040150")
wip       = bal("11040200")
fg_val    = bal("11040300")
pkg_val   = bal("11040500")
rtf_val   = bal("11040800")
interim   = abs(bal("11060000"))
cogs      = bal("51010000")

total_sales_30d = sum(s["amount_total"] for s in sales)
urgent_tasks    = sum(1 for t in tasks if t["priority"] == "1")
n_overdue       = len(overdue)
n_mos           = len(mos)

# ── KPI row ───────────────────────────────────────────────────────────────────
st.markdown("#### Key performance indicators")
k1,k2,k3,k4,k5,k6 = st.columns(6)
def kpi(col, label, val, sub="", color=AURIA_AMBER):
    col.markdown(f"""
    <div style="background:white;border-radius:10px;padding:12px 14px;
                border:0.5px solid #ddd;height:90px">
      <div class="metric-label">{label}</div>
      <div class="metric-val" style="color:{color}">{val}</div>
      <div class="metric-sub">{sub}</div>
    </div>""", unsafe_allow_html=True)

kpi(k1, "Sales — 30 days", f"{total_sales_30d:,.0f}", "LYD")
kpi(k2, "Finished Goods", f"{fg_val:,.0f}", "LYD value")
kpi(k3, "Packaging", f"{pkg_val:,.0f}", "LYD value")
kpi(k4, "Active MOs", str(n_mos), "manufacturing orders", AURIA_MID)
kpi(k5, "Overdue tasks", str(n_overdue), f"{urgent_tasks} urgent",
    AURIA_RED if n_overdue > 3 else AURIA_AMBER)
kpi(k6, "Interim Received", f"{interim:,.0f}",
    "⚠️ CRITICAL — >50K" if interim > 50000 else "LYD",
    AURIA_RED if interim > 50000 else AURIA_AMBER)

st.markdown("<br>", unsafe_allow_html=True)

# ── Alerts ────────────────────────────────────────────────────────────────────
col_alert, col_mos = st.columns([1.2, 1])

with col_alert:
    st.markdown("#### Alerts")
    if interim > 50000:
        st.markdown(f'<div class="alert-crit">🔴 <b>Interim Received {interim:,.0f} LYD</b> — exceeds critical threshold of 50,000. Unmatched vendor bills need urgent review.</div>', unsafe_allow_html=True)
    if abs(wip) > 100:
        st.markdown(f'<div class="alert-warn">⚠️ <b>WIP balance {wip:,.0f} LYD</b> — unclosed manufacturing orders detected.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="alert-ok">✅ <b>WIP = 0</b> — all manufacturing accounts are clean.</div>', unsafe_allow_html=True)
    if n_overdue > 0:
        st.markdown(f'<div class="alert-warn">⚠️ <b>{n_overdue} overdue tasks</b> — {urgent_tasks} marked urgent.</div>', unsafe_allow_html=True)
    else:
        st.markdown('<div class="alert-ok">✅ No overdue tasks.</div>', unsafe_allow_html=True)
    if n_mos > 0:
        mo_names = ", ".join(m["name"] for m in mos)
        st.markdown(f'<div class="alert-ok">🏭 <b>{n_mos} active MO(s):</b> {mo_names}</div>', unsafe_allow_html=True)

with col_mos:
    st.markdown("#### Active manufacturing orders")
    if mos:
        for m in mos:
            state_color = AURIA_MID if m["state"] == "progress" else AURIA_AMBER
            st.markdown(f"""
            <div style="background:white;border-radius:10px;padding:12px 14px;
                        border:0.5px solid #ddd;margin-bottom:8px">
              <div style="font-weight:600;font-size:14px">{m["name"]}</div>
              <div style="font-size:12px;color:#555;margin:4px 0">{m["product_id"][1]}</div>
              <div style="display:flex;gap:10px;font-size:12px">
                <span style="background:{AURIA_LIGHT};color:{AURIA_MID};
                             padding:2px 8px;border-radius:20px">
                  {m["product_qty"]} units
                </span>
                <span style="background:{'#EAF3DE' if m['state']=='progress' else '#FFF3CD'};
                             color:{state_color};padding:2px 8px;border-radius:20px">
                  {m["state"]}
                </span>
              </div>
            </div>""", unsafe_allow_html=True)
    else:
        st.info("No active manufacturing orders.")

st.markdown("---")

# ── Inventory charts ───────────────────────────────────────────────────────────
st.markdown("#### Inventory")
c1, c2 = st.columns(2)

with c1:
    # Units by location
    loc_totals = {}
    for q in quants:
        lid = q["location_id"][0]
        loc_totals[lid] = loc_totals.get(lid, 0) + q["quantity"]
    df_loc = pd.DataFrame([
        {"Location": LOC_NAMES.get(k, str(k)), "Units": round(v)}
        for k, v in loc_totals.items()
    ]).sort_values("Units", ascending=True)
    fig = px.bar(df_loc, x="Units", y="Location", orientation="h",
                 color_discrete_sequence=[AURIA_MID],
                 title="Total units by location")
    fig.update_layout(margin=dict(l=0,r=0,t=40,b=0), height=280,
                      plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(fig, use_container_width=True)

with c2:
    # Accounting stock values pie
    labels = ["Raw Herbs","Raw Oils","RTF","Finished Goods","Packaging","By-Products"]
    values = [raw_herbs, raw_oils, rtf_val, fg_val, pkg_val, bal("11040900")]
    colors = [AURIA_GREEN, AURIA_MID, "#5A9E34","#D4A853","#888780","#A0A89A"]
    fig2 = go.Figure(go.Pie(labels=labels, values=values,
                            marker_colors=colors,
                            hole=0.45, textinfo="label+percent"))
    fig2.update_layout(title="Inventory value breakdown (LYD)",
                       margin=dict(l=0,r=0,t=40,b=0), height=280,
                       paper_bgcolor="white",
                       legend=dict(font=dict(size=11)))
    st.plotly_chart(fig2, use_container_width=True)

# Top products at each location
c3, c4 = st.columns(2)
def top_products(loc_id, n=10):
    items = [(q["product_id"][1], round(q["quantity"]))
             for q in quants if q["location_id"][0] == loc_id]
    return sorted(items, key=lambda x: -x[1])[:n]

with c3:
    items = top_products(55)  # SJ/FG
    if items:
        df = pd.DataFrame(items, columns=["Product","Qty"])
        fig = px.bar(df, x="Qty", y="Product", orientation="h",
                     color_discrete_sequence=[AURIA_GREEN],
                     title="SJ/FG — top finished goods")
        fig.update_layout(margin=dict(l=0,r=0,t=40,b=0), height=320,
                          plot_bgcolor="white", paper_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)

with c4:
    items = top_products(45)  # HD/FG
    if items:
        df = pd.DataFrame(items, columns=["Product","Qty"])
        fig = px.bar(df, x="Qty", y="Product", orientation="h",
                     color_discrete_sequence=[AURIA_AMBER],
                     title="HD/FG — top finished goods")
        fig.update_layout(margin=dict(l=0,r=0,t=40,b=0), height=320,
                          plot_bgcolor="white", paper_bgcolor="white")
        st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ── Sales trend ───────────────────────────────────────────────────────────────
st.markdown("#### Sales — last 30 days")
if sales:
    df_sales = pd.DataFrame(sales)
    df_sales["date"] = pd.to_datetime(df_sales["date_order"]).dt.date
    df_daily = df_sales.groupby("date")["amount_total"].sum().reset_index()
    df_daily.columns = ["Date","Revenue (LYD)"]
    fig = px.area(df_daily, x="Date", y="Revenue (LYD)",
                  color_discrete_sequence=[AURIA_MID],
                  title="Daily revenue (LYD)")
    fig.update_traces(fill="tozeroy", fillcolor=AURIA_LIGHT, line_color=AURIA_MID)
    fig.update_layout(margin=dict(l=0,r=0,t=40,b=0), height=220,
                      plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(fig, use_container_width=True)

st.markdown("---")

# ── Tasks ─────────────────────────────────────────────────────────────────────
st.markdown("#### Tasks")
tc1, tc2 = st.columns([1, 1.3])

with tc1:
    st.markdown("##### By project")
    df_proj = pd.DataFrame([
        {"Project": p["name"], "Tasks": p["task_count"]}
        for p in projects if p["task_count"] > 0
    ]).sort_values("Tasks", ascending=True)
    fig = px.bar(df_proj, x="Tasks", y="Project", orientation="h",
                 color_discrete_sequence=[AURIA_GREEN])
    fig.update_layout(margin=dict(l=0,r=0,t=10,b=0), height=300,
                      plot_bgcolor="white", paper_bgcolor="white")
    st.plotly_chart(fig, use_container_width=True)

with tc2:
    st.markdown("##### Overdue tasks")
    if overdue:
        rows = []
        for t in overdue:
            unames = ", ".join(USER_NAMES.get(u, str(u)) for u in t["user_ids"]) or "—"
            dl = t["date_deadline"][:10] if t["date_deadline"] else "—"
            rows.append({
                "Task": t["name"],
                "Project": t["project_id"][1] if t["project_id"] else "—",
                "Owner": unames,
                "Deadline": dl,
                "Urgent": "🔴" if t["priority"] == "1" else "",
            })
        df_od = pd.DataFrame(rows)
        st.dataframe(df_od, use_container_width=True, hide_index=True,
                     column_config={"Urgent": st.column_config.TextColumn(width="small")})
    else:
        st.success("No overdue tasks 🎉")

st.markdown("---")

# ── Accounting summary ────────────────────────────────────────────────────────
st.markdown("#### Accounting summary")
acct_rows = [
    ("11040100", "Raw Herbs",         raw_herbs, False),
    ("11040150", "Raw Oils",          raw_oils,  False),
    ("11040200", "WIP",               wip,       abs(wip) > 100),
    ("11040300", "Finished Goods",    fg_val,    False),
    ("11040500", "Packaging",         pkg_val,   False),
    ("11040800", "RTF",               rtf_val,   False),
    ("11040900", "By-Products",       bal("11040900"), False),
    ("11060000", "Interim Received",  interim,   interim > 50000),
    ("51010000", "COGS",              cogs,      False),
]
df_acct = pd.DataFrame([
    {"Code": c, "Account": n, "Balance (LYD)": f"{v:,.2f}",
     "Status": "⚠️ CRITICAL" if flag else ("✅ OK" if not flag else "")}
    for c, n, v, flag in acct_rows
])
st.dataframe(df_acct, use_container_width=True, hide_index=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="margin-top:30px;padding:10px 0;border-top:1px solid #ddd;
            font-size:11px;color:#999;text-align:center">
  Auria Operations Dashboard · Data refreshes every 60 seconds ·
  Connected to {ODOO_URL}
</div>""", unsafe_allow_html=True)

# Auto-refresh every 60 s
st.markdown("""
<script>
  setTimeout(() => window.location.reload(), 60000);
</script>""", unsafe_allow_html=True)
