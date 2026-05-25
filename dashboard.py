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

# ── Always-dark Auria palette ─────────────────────────────────────────────────
BG          = "#0e1a0f"
BG2         = "#1a2b1b"
CARD        = "#1e2e1f"
BORDER      = "#2d452e"
TEXT        = "#e8f5e9"
MUTED       = "#7aaa78"
GREEN       = "#1F3420"
MID         = "#3B6D11"
AMBER       = "#D4A853"
RED         = "#A32D2D"
PLOT_BG     = "#141e15"
CRIT_BG     = "#2e1010"; CRIT_FG = "#f4a0a0"; CRIT_BD = "#A32D2D"
WARN_BG     = "#2e2610"; WARN_FG = "#f4d080"; WARN_BD = "#D4A853"
OK_BG       = "#0f2010"; OK_FG   = "#88cc88"; OK_BD   = "#3B6D11"

LOC_NAMES  = {37:"SJ/RM-Raw", 38:"SJ/PKG", 39:"SJ/RTF", 55:"SJ/FG", 45:"HD/FG"}
USER_NAMES = {
    8:"Hussam", 18:"Abdullah", 29:"Ala' Deep", 9:"Alaa Oshah",
    15:"Marwan", 13:"Nasser", 27:"Khan", 11:"Wesal", 23:"Bader", 6:"Moad",
}
DONE_STAGES = [14,15,28,29,41,66,68,70,74,75,79,83]

# ── Odoo ──────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_models():
    return xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

def odoo(model, method, domain=None, kwargs=None):
    return get_models().execute_kw(
        ODOO_DB, ODOO_UID, ODOO_PWD, model, method,
        [domain or []], kwargs or {})

@st.cache_data(ttl=30)
def fetch_all(cache_key=None):
    today      = cache_key or str(date.today())
    thirty_ago = str(date.today() - timedelta(days=30))
    tasks   = odoo("project.task","search_read",[["active","=",True]],
                {"fields":["name","project_id","user_ids","priority","date_deadline","stage_id"],"limit":300})
    mos     = odoo("mrp.production","search_read",[["state","in",["confirmed","progress"]]],
                {"fields":["name","product_id","product_qty","state"],"limit":50})
    quants  = odoo("stock.quant","search_read",
                [["location_id","in",[37,38,39,55,45]],["quantity",">",0]],
                {"fields":["product_id","location_id","quantity"],"limit":400})
    acct    = odoo("account.move.line","read_group",
                [["account_id.code","in",
                  ["11040100","11040150","11040200","11040300",
                   "11040500","11040800","11040900","11060000","51010000"]],
                 ["move_id.state","=","posted"]],
                {"fields":["account_id","balance:sum"],"groupby":["account_id"]})
    overdue = odoo("project.task","search_read",
                [["date_deadline","<",today],["active","=",True],
                 ["stage_id","not in",DONE_STAGES]],
                {"fields":["name","project_id","user_ids","date_deadline","priority","stage_id"],"limit":100})
    projects= odoo("project.project","search_read",[],{"fields":["id","name","task_count"]})
    sales   = odoo("sale.order","search_read",
                [["state","in",["sale","done"]],["date_order",">=",thirty_ago]],
                {"fields":["name","amount_total","date_order"],"limit":200})
    return dict(tasks=tasks,mos=mos,quants=quants,acct=acct,
                overdue=overdue,projects=projects,sales=sales,today=today)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Auria — Operations", page_icon="🌿",
                   layout="wide", initial_sidebar_state="collapsed")

# ── Force dark background on the whole app ────────────────────────────────────
st.markdown(f"""<style>
  html, body, [data-testid="stAppViewContainer"],
  [data-testid="stHeader"], [data-testid="stToolbar"],
  section.main > div {{ background-color: {BG} !important; }}
  [data-testid="stSidebar"] {{ background-color: {BG2} !important; }}
  h1,h2,h3,h4,h5,h6,p,span,label,div {{ color: {TEXT}; }}
  .stMarkdown p {{ color: {TEXT}; }}
  hr {{ border-color: {BORDER}; }}
  /* KPI cards */
  .kpi {{ background:{CARD};border:0.5px solid {BORDER};border-radius:12px;
          padding:14px 16px;height:95px; }}
  .kpi-lbl {{ font-size:12px;color:{MUTED};margin-bottom:4px; }}
  .kpi-num {{ font-size:28px;font-weight:600;line-height:1.1; }}
  .kpi-sub {{ font-size:11px;color:{MUTED};margin-top:2px; }}
  /* Alert rows */
  .al {{ display:flex;gap:10px;align-items:flex-start;padding:10px 14px;
         border-radius:8px;margin-bottom:8px;font-size:13px; }}
  .al-c {{ background:{CRIT_BG};border-left:4px solid {CRIT_BD};color:{CRIT_FG}; }}
  .al-w {{ background:{WARN_BG};border-left:4px solid {WARN_BD};color:{WARN_FG}; }}
  .al-o {{ background:{OK_BG};border-left:4px solid {OK_BD};color:{OK_FG}; }}
  /* MO cards */
  .mo  {{ background:{CARD};border:0.5px solid {BORDER};border-radius:12px;
          padding:12px 16px;margin-bottom:10px; }}
  .mo-t {{ font-weight:600;font-size:14px;color:{TEXT}; }}
  .mo-s {{ font-size:12px;color:{MUTED};margin:4px 0 8px; }}
  .badge {{ display:inline-block;padding:3px 10px;border-radius:20px;
            font-size:11px;font-weight:500;margin-right:6px; }}
  .bg  {{ background:{OK_BG};color:{OK_FG}; }}
  .ba  {{ background:{WARN_BG};color:{WARN_FG}; }}
  /* Streamlit native elements dark override */
  [data-testid="stDataFrame"] {{ background:{CARD} !important; }}
  .stButton > button {{ background:{CARD};border:0.5px solid {BORDER};
                        color:{TEXT};border-radius:8px; }}
  .stButton > button:hover {{ background:{BG2};border-color:{MID}; }}
  footer {{ visibility:hidden; }}
</style>""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="background:{GREEN};border-radius:12px;padding:16px 22px;
            margin-bottom:16px;display:flex;align-items:center;
            justify-content:space-between;">
  <div>
    <div style="font-size:20px;font-weight:600;color:#fff">
      🌿 Auria — لوحة العمليات
    </div>
    <div style="font-size:12px;color:#8fb88a;margin-top:2px">
      Live · odoo.auria.global
    </div>
  </div>
  <div style="font-size:13px;color:#8fb88a;text-align:right">
    {datetime.now().strftime("%A, %d %B %Y")}<br>
    <span style="font-size:11px">{datetime.now().strftime("%H:%M:%S")}</span>
  </div>
</div>""", unsafe_allow_html=True)

# ── Refresh ───────────────────────────────────────────────────────────────────
rc, rt = st.columns([1,6])
with rc:
    if st.button("🔄 Refresh"):
        st.cache_data.clear()
        st.rerun()
with rt:
    st.markdown(f"<span style='font-size:11px;color:{MUTED}'>Auto-refreshes every 30s</span>",
                unsafe_allow_html=True)

# ── Data ──────────────────────────────────────────────────────────────────────
with st.spinner("Fetching from Odoo…"):
    data = fetch_all(cache_key=str(date.today()))

tasks=data["tasks"]; mos=data["mos"]; quants=data["quants"]
acct=data["acct"];   overdue=data["overdue"]; projects=data["projects"]
sales=data["sales"]; today=data["today"]

acct_map = {}
for a in acct:
    n = a["account_id"][1] if a["account_id"] else ""
    acct_map[n] = round(a.get("balance",0) or 0, 2)

def bal(code):
    for k,v in acct_map.items():
        if k.startswith(code): return v
    return 0

raw_herbs=bal("11040100"); raw_oils=bal("11040150"); wip=bal("11040200")
fg_val=bal("11040300");    pkg_val=bal("11040500");  rtf_val=bal("11040800")
interim=abs(bal("11060000")); cogs=bal("51010000")
total_sales = sum(s["amount_total"] for s in sales)
urgent      = sum(1 for t in tasks if t["priority"]=="1")
n_over      = len(overdue)
n_mos       = len(mos)

# ── KPIs ──────────────────────────────────────────────────────────────────────
st.markdown(f"<p style='font-size:13px;color:{MUTED};margin-bottom:8px'>Key performance indicators</p>",
            unsafe_allow_html=True)
cols = st.columns(6)
def kpi(col, lbl, num, sub="", color=AMBER):
    col.markdown(f"""<div class="kpi">
      <div class="kpi-lbl">{lbl}</div>
      <div class="kpi-num" style="color:{color}">{num}</div>
      <div class="kpi-sub">{sub}</div>
    </div>""", unsafe_allow_html=True)

kpi(cols[0], "Sales — 30 days",  f"{total_sales:,.0f}", "LYD")
kpi(cols[1], "Finished Goods",   f"{fg_val:,.0f}",       "LYD")
kpi(cols[2], "Packaging",        f"{pkg_val:,.0f}",       "LYD")
kpi(cols[3], "Active MOs",       str(n_mos),              "manufacturing orders", MID)
kpi(cols[4], "Overdue tasks",    str(n_over),             f"{urgent} urgent",
    RED if n_over>3 else AMBER)
kpi(cols[5], "Interim Received", f"{interim:,.0f}",
    "⚠️ CRITICAL >50K" if interim>50000 else "LYD",
    RED if interim>50000 else AMBER)

st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)
st.markdown(f"<hr style='border-color:{BORDER};margin:4px 0 16px'>", unsafe_allow_html=True)

# ── Alerts + MOs ──────────────────────────────────────────────────────────────
ca, cm = st.columns([1.2,1])

with ca:
    st.markdown(f"<p style='font-weight:600;font-size:15px;margin-bottom:10px'>Alerts</p>",
                unsafe_allow_html=True)
    if interim>50000:
        st.markdown(f'<div class="al al-c">🔴 <span><b>Interim {interim:,.0f} LYD</b> — exceeds 50K critical threshold. Unmatched vendor bills.</span></div>',
                    unsafe_allow_html=True)
    if abs(wip)>100:
        st.markdown(f'<div class="al al-w">⚠️ <span><b>WIP {wip:,.0f} LYD</b> — unclosed manufacturing orders.</span></div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="al al-o">✅ <span><b>WIP = 0</b> — manufacturing accounts clean.</span></div>',
                    unsafe_allow_html=True)
    if n_over>0:
        st.markdown(f'<div class="al al-w">⚠️ <span><b>{n_over} overdue tasks</b> — {urgent} marked urgent.</span></div>',
                    unsafe_allow_html=True)
    else:
        st.markdown('<div class="al al-o">✅ <span>No overdue tasks.</span></div>',
                    unsafe_allow_html=True)
    if n_mos>0:
        mo_names = ", ".join(m["name"] for m in mos)
        st.markdown(f'<div class="al al-o">🏭 <span><b>{n_mos} active MO(s):</b> {mo_names}</span></div>',
                    unsafe_allow_html=True)

with cm:
    st.markdown(f"<p style='font-weight:600;font-size:15px;margin-bottom:10px'>Active manufacturing orders</p>",
                unsafe_allow_html=True)
    if mos:
        for m in mos:
            bc = "bg" if m["state"]=="progress" else "ba"
            st.markdown(f"""<div class="mo">
              <div class="mo-t">{m["name"]}</div>
              <div class="mo-s">{m["product_id"][1]}</div>
              <span class="badge bg">{m["product_qty"]} units</span>
              <span class="badge {bc}">{m["state"]}</span>
            </div>""", unsafe_allow_html=True)
    else:
        st.markdown(f'<div class="al al-o">No active manufacturing orders.</div>',
                    unsafe_allow_html=True)

st.markdown(f"<hr style='border-color:{BORDER};margin:16px 0'>", unsafe_allow_html=True)

# ── Inventory ─────────────────────────────────────────────────────────────────
st.markdown(f"<p style='font-weight:600;font-size:15px;margin-bottom:10px'>Inventory</p>",
            unsafe_allow_html=True)
ci1, ci2 = st.columns(2)

with ci1:
    lt = {}
    for q in quants:
        lid = q["location_id"][0]
        lt[lid] = lt.get(lid,0) + q["quantity"]
    df_loc = pd.DataFrame([{"Location":LOC_NAMES.get(k,str(k)),"Units":round(v)}
                            for k,v in lt.items()]).sort_values("Units",ascending=True)
    fig = px.bar(df_loc, x="Units", y="Location", orientation="h",
                 color_discrete_sequence=[MID], title="Units by location")
    fig.update_layout(margin=dict(l=0,r=0,t=36,b=0), height=260,
                      plot_bgcolor=PLOT_BG, paper_bgcolor=PLOT_BG, font_color=TEXT,
                      title_font_color=MUTED, title_font_size=13)
    fig.update_xaxes(gridcolor=BORDER, zerolinecolor=BORDER)
    fig.update_yaxes(gridcolor=BORDER)
    st.plotly_chart(fig, use_container_width=True)

with ci2:
    labels = ["Raw Herbs","Raw Oils","RTF","Fin. Goods","Packaging","By-Products"]
    values = [raw_herbs, raw_oils, rtf_val, fg_val, pkg_val, bal("11040900")]
    colors = [GREEN, MID, "#5A9E34", AMBER, "#888780", "#A0A89A"]
    fig2 = go.Figure(go.Pie(labels=labels, values=values, marker_colors=colors,
                            hole=0.45, textinfo="label+percent",
                            textfont=dict(color=TEXT)))
    fig2.update_layout(title="Inventory value (LYD)",
                       margin=dict(l=0,r=0,t=36,b=0), height=260,
                       paper_bgcolor=PLOT_BG, font_color=TEXT,
                       title_font_color=MUTED, title_font_size=13,
                       legend=dict(font=dict(size=11, color=TEXT)))
    st.plotly_chart(fig2, use_container_width=True)

ci3, ci4 = st.columns(2)
def top_p(loc_id, n=10):
    items = [(q["product_id"][1], round(q["quantity"]))
             for q in quants if q["location_id"][0]==loc_id]
    return sorted(items, key=lambda x:-x[1])[:n]

with ci3:
    items = top_p(55)
    if items:
        df = pd.DataFrame(items, columns=["Product","Qty"])
        fig = px.bar(df, x="Qty", y="Product", orientation="h",
                     color_discrete_sequence=[GREEN], title="SJ/FG — top products")
        fig.update_layout(margin=dict(l=0,r=0,t=36,b=0), height=320,
                          plot_bgcolor=PLOT_BG, paper_bgcolor=PLOT_BG, font_color=TEXT,
                          title_font_color=MUTED, title_font_size=13)
        fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
        st.plotly_chart(fig, use_container_width=True)

with ci4:
    items = top_p(45)
    if items:
        df = pd.DataFrame(items, columns=["Product","Qty"])
        fig = px.bar(df, x="Qty", y="Product", orientation="h",
                     color_discrete_sequence=[AMBER], title="HD/FG — top products")
        fig.update_layout(margin=dict(l=0,r=0,t=36,b=0), height=320,
                          plot_bgcolor=PLOT_BG, paper_bgcolor=PLOT_BG, font_color=TEXT,
                          title_font_color=MUTED, title_font_size=13)
        fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
        st.plotly_chart(fig, use_container_width=True)

st.markdown(f"<hr style='border-color:{BORDER};margin:16px 0'>", unsafe_allow_html=True)

# ── Sales trend ───────────────────────────────────────────────────────────────
st.markdown(f"<p style='font-weight:600;font-size:15px;margin-bottom:10px'>Sales — last 30 days</p>",
            unsafe_allow_html=True)
if sales:
    df_s = pd.DataFrame(sales)
    df_s["date"] = pd.to_datetime(df_s["date_order"]).dt.date
    df_d = df_s.groupby("date")["amount_total"].sum().reset_index()
    df_d.columns = ["Date","Revenue (LYD)"]
    fig = px.area(df_d, x="Date", y="Revenue (LYD)", color_discrete_sequence=[MID])
    fig.update_traces(fill="tozeroy", fillcolor="rgba(59,109,17,0.3)", line_color=MID)
    fig.update_layout(margin=dict(l=0,r=0,t=10,b=0), height=200,
                      plot_bgcolor=PLOT_BG, paper_bgcolor=PLOT_BG, font_color=TEXT)
    fig.update_xaxes(gridcolor=BORDER, zerolinecolor=BORDER)
    fig.update_yaxes(gridcolor=BORDER)
    st.plotly_chart(fig, use_container_width=True)

st.markdown(f"<hr style='border-color:{BORDER};margin:16px 0'>", unsafe_allow_html=True)

# ── Tasks ─────────────────────────────────────────────────────────────────────
st.markdown(f"<p style='font-weight:600;font-size:15px;margin-bottom:10px'>Tasks</p>",
            unsafe_allow_html=True)
tt1, tt2 = st.columns([1,1.3])

with tt1:
    st.markdown(f"<p style='font-size:13px;color:{MUTED};margin-bottom:6px'>By project</p>",
                unsafe_allow_html=True)
    df_p = pd.DataFrame([{"Project":p["name"],"Tasks":p["task_count"]}
                          for p in projects if p["task_count"]>0]).sort_values("Tasks",ascending=True)
    fig = px.bar(df_p, x="Tasks", y="Project", orientation="h",
                 color_discrete_sequence=[MID])
    fig.update_layout(margin=dict(l=0,r=0,t=10,b=0), height=300,
                      plot_bgcolor=PLOT_BG, paper_bgcolor=PLOT_BG, font_color=TEXT)
    fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
    st.plotly_chart(fig, use_container_width=True)

with tt2:
    st.markdown(f"<p style='font-size:13px;color:{MUTED};margin-bottom:6px'>Overdue tasks</p>",
                unsafe_allow_html=True)
    if overdue:
        rows = []
        for t in overdue:
            u = ", ".join(USER_NAMES.get(x,str(x)) for x in t["user_ids"]) or "—"
            dl = t["date_deadline"][:10] if t["date_deadline"] else "—"
            rows.append({"Task":t["name"],
                         "Project":t["project_id"][1] if t["project_id"] else "—",
                         "Owner":u, "Deadline":dl,
                         "!":"🔴" if t["priority"]=="1" else ""})
        st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True,
                     column_config={"!": st.column_config.TextColumn(width="small")})
    else:
        st.markdown(f'<div class="al al-o">✅ No overdue tasks.</div>', unsafe_allow_html=True)

st.markdown(f"<hr style='border-color:{BORDER};margin:16px 0'>", unsafe_allow_html=True)

# ── Accounting ────────────────────────────────────────────────────────────────
st.markdown(f"<p style='font-weight:600;font-size:15px;margin-bottom:10px'>Accounting summary</p>",
            unsafe_allow_html=True)
rows = [
    ("11040100","Raw Herbs",        raw_herbs, False),
    ("11040150","Raw Oils",         raw_oils,  False),
    ("11040200","WIP",              wip,       abs(wip)>100),
    ("11040300","Finished Goods",   fg_val,    False),
    ("11040500","Packaging",        pkg_val,   False),
    ("11040800","RTF",              rtf_val,   False),
    ("11040900","By-Products",      bal("11040900"), False),
    ("11060000","Interim Received", interim,   interim>50000),
    ("51010000","COGS",             cogs,      False),
]
st.dataframe(
    pd.DataFrame([{"Code":c,"Account":n,"Balance (LYD)":f"{v:,.2f}",
                   "Status":"⚠️ CRITICAL" if f else "✅ OK"}
                  for c,n,v,f in rows]),
    use_container_width=True, hide_index=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="margin-top:24px;padding:10px 0;border-top:1px solid {BORDER};
            font-size:11px;color:{MUTED};text-align:center">
  Auria Operations Dashboard · refreshes every 30s · {ODOO_URL}
</div>""", unsafe_allow_html=True)

st.markdown("<script>setTimeout(()=>window.location.reload(),30000);</script>",
            unsafe_allow_html=True)
