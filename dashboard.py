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
import urllib.request, json, urllib.parse

# ── Credentials ───────────────────────────────────────────────────────────────
ODOO_URL   = "https://odoo.auria.global"
ODOO_DB    = "Auria_Business"
ODOO_UID   = 8
ODOO_PWD   = "123456"
PAGE_ID    = "145285001991586"
IG_ID      = "17841462343514591"
USER_TOKEN = "EAASVMwJoNLIBRgwWum1jWBbWdpZCnn0bh42jIujGBr5EqRhOEIz5IW47oZBvDL3Xh1CGHyNmGTfOgTDufLwth2I76M3mhZBRP03voZBL83IbOXZA8BW1ZBubwYeePPZAbZCy7mPbZAgC5OJFGTEPAhNDSRmc0SeFHtECyqui88k7Caz70AEH87kAZCePIf4qmdINHMZBHQtquKy1qFrQwz3LkU5H2QBb39knwZBYhc3JaTXmL7uv8AMVuYm8upuIZA1RSoyDhyZCI06A0erwchSX0Xa50ZCrd7BegZDZD"

# ── Auria dark palette ─────────────────────────────────────────────────────────
BG       = "#0e1a0f"; BG2 = "#1a2b1b"; CARD = "#1e2e1f"; BORDER = "#2d452e"
TEXT     = "#e8f5e9"; MUTED = "#7aaa78"
GREEN    = "#1F3420"; MID = "#3B6D11"; AMBER = "#D4A853"; RED = "#A32D2D"
PLOT_BG  = "#141e15"
CRIT_BG  = "#2e1010"; CRIT_FG = "#f4a0a0"; CRIT_BD = "#A32D2D"
WARN_BG  = "#2e2610"; WARN_FG = "#f4d080"; WARN_BD = "#D4A853"
OK_BG    = "#0f2010"; OK_FG   = "#88cc88"; OK_BD   = "#3B6D11"

LOC_NAMES  = {37:"SJ/RM-Raw",38:"SJ/PKG",39:"SJ/RTF",55:"SJ/FG",45:"HD/FG"}
USER_NAMES = {8:"Hussam",18:"Abdullah",29:"Ala' Deep",9:"Alaa Oshah",
              15:"Marwan",13:"Nasser",27:"Khan",11:"Wesal",23:"Bader",6:"Moad"}
DONE_STAGES = [14,15,28,29,41,66,68,70,74,75,79,83]

# ── Odoo helper ───────────────────────────────────────────────────────────────
@st.cache_resource
def get_models():
    return xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

def odoo(model, method, domain=None, kwargs=None):
    return get_models().execute_kw(ODOO_DB, ODOO_UID, ODOO_PWD,
        model, method, [domain or []], kwargs or {})

# ── Meta helper ───────────────────────────────────────────────────────────────
def meta_get(path, params=None, token=None):
    p = params or {}
    p["access_token"] = token or USER_TOKEN
    url = f"https://graph.facebook.com/v19.0/{path}?{urllib.parse.urlencode(p)}"
    try:
        r = urllib.request.urlopen(url, timeout=15)
        return json.loads(r.read())
    except urllib.error.HTTPError as e:
        return json.loads(e.read())
    except Exception as ex:
        return {"error": str(ex)}

@st.cache_data(ttl=3600)
def get_page_token():
    pages = meta_get("me/accounts", {"fields": "id,name,access_token"})
    for p in pages.get("data", []):
        if p["id"] == PAGE_ID:
            return p["access_token"]
    return None

# ── Data fetchers ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def fetch_odoo(cache_key=None):
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
    DONE_S  = [14,15,28,29,41,66,68,70,74,75,79,83]
    overdue = odoo("project.task","search_read",
                [["date_deadline","<",today],["active","=",True],
                 ["stage_id","not in",DONE_S]],
                {"fields":["name","project_id","user_ids","date_deadline","priority","stage_id"],"limit":100})
    projects= odoo("project.project","search_read",[],{"fields":["id","name","task_count"]})
    sales   = odoo("sale.order","search_read",
                [["state","in",["sale","done"]],["date_order",">=",thirty_ago]],
                {"fields":["name","amount_total","date_order","user_id"],"limit":500})
    return dict(tasks=tasks,mos=mos,quants=quants,acct=acct,
                overdue=overdue,projects=projects,sales=sales,today=today)

@st.cache_data(ttl=300)
def fetch_meta():
    """Fetch FB conversations using auto-exchanged page token."""
    results = {"conversations":[], "summary":{}, "error": None, "daily":[]}

    page_token = get_page_token()
    if not page_token:
        results["error"] = "Could not obtain page token"
        return results

    # Paginate through conversations
    all_convos = []
    params = {"fields":"id,updated_time,message_count,participants,messages{from,created_time}",
              "limit":"25"}
    batch = meta_get(f"{PAGE_ID}/conversations", params, token=page_token)
    if "error" in batch:
        results["error"] = str(batch["error"])
        return results

    all_convos.extend(batch.get("data",[]))
    cursor = batch.get("paging",{}).get("cursors",{}).get("after")
    while cursor and len(all_convos) < 100:
        p2 = dict(params); p2["after"] = cursor
        batch = meta_get(f"{PAGE_ID}/conversations", p2, token=page_token)
        data = batch.get("data",[])
        if not data: break
        all_convos.extend(data)
        cursor = batch.get("paging",{}).get("cursors",{}).get("after")

    # Parse each conversation
    parsed = []
    resp_times = []
    daily = {}

    for c in all_convos:
        msgs = c.get("messages",{}).get("data",[])
        if not msgs: continue

        sent  = sum(1 for m in msgs if m.get("from",{}).get("id")==PAGE_ID)
        rcvd  = len(msgs) - sent
        day   = c.get("updated_time","")[:10]
        customer = next((p["name"] for p in c.get("participants",{}).get("data",[])
                         if p["id"] != PAGE_ID), "Unknown")

        # Response time
        sorted_msgs = sorted(msgs, key=lambda x: x.get("created_time",""))
        resp_min = None
        for i, m in enumerate(sorted_msgs):
            if m.get("from",{}).get("id") != PAGE_ID:
                for j in range(i+1, len(sorted_msgs)):
                    if sorted_msgs[j].get("from",{}).get("id") == PAGE_ID:
                        t1 = datetime.fromisoformat(m["created_time"].replace("Z","+00:00"))
                        t2 = datetime.fromisoformat(sorted_msgs[j]["created_time"].replace("Z","+00:00"))
                        diff = (t2-t1).total_seconds()/60
                        if diff >= 0:
                            resp_min = round(diff,1)
                            resp_times.append(resp_min)
                        break
                break

        parsed.append({"customer":customer,"updated":day,"total":len(msgs),
                        "sent":sent,"received":rcvd,"resp_min":resp_min})
        if day:
            daily[day] = daily.get(day,{"rcvd":0,"sent":0})
            daily[day]["rcvd"] += rcvd
            daily[day]["sent"] += sent

    results["conversations"] = parsed
    results["summary"] = {
        "total_convos": len(parsed),
        "total_rcvd":   sum(c["received"] for c in parsed),
        "total_sent":   sum(c["sent"]     for c in parsed),
        "avg_resp_min": round(sum(resp_times)/len(resp_times),1) if resp_times else None,
        "fast_replies": sum(1 for r in resp_times if r <= 30),
        "slow_replies": sum(1 for r in resp_times if r > 60),
    }
    results["daily"] = [{"Date":k,"Received":v["rcvd"],"Sent":v["sent"]}
                         for k,v in sorted(daily.items())]
    return results

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Auria — Operations", page_icon="🌿",
                   layout="wide", initial_sidebar_state="collapsed")

st.markdown(f"""<style>
  html,body,[data-testid="stAppViewContainer"],[data-testid="stHeader"],
  section.main>div {{ background-color:{BG} !important; }}
  [data-testid="stSidebar"] {{ background-color:{BG2} !important; }}
  h1,h2,h3,h4,h5,h6,p,span,label,div {{ color:{TEXT}; }}
  [data-testid="stTabs"] button {{ color:{MUTED} !important; }}
  [data-testid="stTabs"] button[aria-selected="true"] {{ color:{AMBER} !important;
      border-bottom:2px solid {AMBER} !important; }}
  hr {{ border-color:{BORDER}; }}
  .kpi {{ background:{CARD};border:0.5px solid {BORDER};border-radius:12px;
          padding:14px 16px;height:95px; }}
  .kpi-lbl {{ font-size:12px;color:{MUTED};margin-bottom:4px; }}
  .kpi-num {{ font-size:28px;font-weight:600;line-height:1.1; }}
  .kpi-sub {{ font-size:11px;color:{MUTED};margin-top:2px; }}
  .al {{ display:flex;gap:10px;align-items:flex-start;padding:10px 14px;
         border-radius:8px;margin-bottom:8px;font-size:13px; }}
  .al-c {{ background:{CRIT_BG};border-left:4px solid {CRIT_BD};color:{CRIT_FG}; }}
  .al-w {{ background:{WARN_BG};border-left:4px solid {WARN_BD};color:{WARN_FG}; }}
  .al-o {{ background:{OK_BG};border-left:4px solid {OK_BD};color:{OK_FG}; }}
  .mo  {{ background:{CARD};border:0.5px solid {BORDER};border-radius:12px;
          padding:12px 16px;margin-bottom:10px; }}
  .mo-t {{ font-weight:600;font-size:14px;color:{TEXT}; }}
  .mo-s {{ font-size:12px;color:{MUTED};margin:4px 0 8px; }}
  .badge {{ display:inline-block;padding:3px 10px;border-radius:20px;
            font-size:11px;font-weight:500;margin-right:6px; }}
  .bg {{ background:{OK_BG};color:{OK_FG}; }}
  .ba {{ background:{WARN_BG};color:{WARN_FG}; }}
  .sp-card {{ background:{CARD};border:0.5px solid {BORDER};border-radius:12px;
              padding:16px;margin-bottom:10px; }}
  .sp-name {{ font-size:16px;font-weight:600;color:{TEXT};margin-bottom:10px; }}
  .sp-stat {{ display:inline-block;padding:6px 14px;border-radius:8px;
              background:{BG2};margin-right:8px;margin-bottom:6px;text-align:center; }}
  .sp-stat-val {{ font-size:18px;font-weight:600;color:{AMBER}; }}
  .sp-stat-lbl {{ font-size:10px;color:{MUTED}; }}
  .stButton>button {{ background:{CARD};border:0.5px solid {BORDER};
                      color:{TEXT};border-radius:8px; }}
  .stButton>button:hover {{ background:{BG2};border-color:{MID}; }}
  footer {{ visibility:hidden; }}
</style>""", unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="background:{GREEN};border-radius:12px;padding:16px 22px;
            margin-bottom:16px;display:flex;align-items:center;justify-content:space-between;">
  <div>
    <div style="font-size:20px;font-weight:600;color:#fff">🌿 Auria — لوحة العمليات</div>
    <div style="font-size:12px;color:#8fb88a;margin-top:2px">Live · odoo.auria.global</div>
  </div>
  <div style="font-size:13px;color:#8fb88a;text-align:right">
    {datetime.now().strftime("%A, %d %B %Y")}<br>
    <span style="font-size:11px">{datetime.now().strftime("%H:%M:%S")}</span>
  </div>
</div>""", unsafe_allow_html=True)

rc, rt = st.columns([1,6])
with rc:
    if st.button("🔄 Refresh"):
        st.cache_data.clear(); st.rerun()
with rt:
    st.markdown(f"<span style='font-size:11px;color:{MUTED}'>Auto-refreshes every 30s</span>",
                unsafe_allow_html=True)

# ── Load data ─────────────────────────────────────────────────────────────────
with st.spinner("Fetching from Odoo…"):
    data = fetch_odoo(cache_key=str(date.today()))

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
urgent = sum(1 for t in tasks if t["priority"]=="1")
n_over = len(overdue); n_mos = len(mos)

# ── TABS ──────────────────────────────────────────────────────────────────────
tab1, tab2, tab3 = st.tabs(["📊 Operations", "💰 Sales by Salesperson", "💬 FB / IG Inbox"])

# ════════════════════════════════════════════════════════
# TAB 1 — OPERATIONS (existing dashboard)
# ════════════════════════════════════════════════════════
with tab1:
    st.markdown(f"<p style='font-size:13px;color:{MUTED};margin-bottom:8px'>Key performance indicators</p>",
                unsafe_allow_html=True)
    cols = st.columns(6)
    def kpi(col, lbl, num, sub="", color=AMBER):
        col.markdown(f"""<div class="kpi">
          <div class="kpi-lbl">{lbl}</div>
          <div class="kpi-num" style="color:{color}">{num}</div>
          <div class="kpi-sub">{sub}</div>
        </div>""", unsafe_allow_html=True)

    kpi(cols[0],"Sales — 30d",   f"{total_sales:,.0f}","LYD")
    kpi(cols[1],"Finished Goods",f"{fg_val:,.0f}",     "LYD")
    kpi(cols[2],"Packaging",     f"{pkg_val:,.0f}",     "LYD")
    kpi(cols[3],"Active MOs",    str(n_mos),            "orders", MID)
    kpi(cols[4],"Overdue tasks", str(n_over),           f"{urgent} urgent",
        RED if n_over>3 else AMBER)
    kpi(cols[5],"Interim Rcvd",  f"{interim:,.0f}",
        "⚠️ CRITICAL" if interim>50000 else "LYD",
        RED if interim>50000 else AMBER)

    st.markdown(f"<hr style='border-color:{BORDER};margin:16px 0'>", unsafe_allow_html=True)
    ca, cm = st.columns([1.2,1])
    with ca:
        st.markdown(f"<p style='font-weight:600;font-size:15px;margin-bottom:10px'>Alerts</p>",
                    unsafe_allow_html=True)
        if interim>50000:
            st.markdown(f'<div class="al al-c">🔴 <span><b>Interim {interim:,.0f} LYD</b> — exceeds 50K. Unmatched vendor bills.</span></div>', unsafe_allow_html=True)
        st.markdown(f'<div class="al al-{"w" if abs(wip)>100 else "o"}">{"⚠️" if abs(wip)>100 else "✅"} <span><b>WIP {wip:,.2f} LYD</b> — {"unclosed MOs!" if abs(wip)>100 else "clean."}</span></div>', unsafe_allow_html=True)
        if n_over>0:
            st.markdown(f'<div class="al al-w">⚠️ <span><b>{n_over} overdue tasks</b> — {urgent} urgent.</span></div>', unsafe_allow_html=True)
        else:
            st.markdown('<div class="al al-o">✅ <span>No overdue tasks.</span></div>', unsafe_allow_html=True)
        if n_mos>0:
            st.markdown(f'<div class="al al-o">🏭 <span><b>{n_mos} MO(s):</b> {", ".join(m["name"] for m in mos)}</span></div>', unsafe_allow_html=True)
    with cm:
        st.markdown(f"<p style='font-weight:600;font-size:15px;margin-bottom:10px'>Active MOs</p>",
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

    st.markdown(f"<hr style='border-color:{BORDER};margin:16px 0'>", unsafe_allow_html=True)
    st.markdown(f"<p style='font-weight:600;font-size:15px;margin-bottom:10px'>Inventory</p>",
                unsafe_allow_html=True)
    ci1, ci2 = st.columns(2)
    with ci1:
        lt = {}
        for q in quants:
            lid=q["location_id"][0]; lt[lid]=lt.get(lid,0)+q["quantity"]
        df_loc = pd.DataFrame([{"Location":LOC_NAMES.get(k,str(k)),"Units":round(v)}
                                for k,v in lt.items()]).sort_values("Units",ascending=True)
        fig = px.bar(df_loc,x="Units",y="Location",orientation="h",
                     color_discrete_sequence=[MID],title="Units by location")
        fig.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=260,
                          plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,font_color=TEXT,
                          title_font_color=MUTED,title_font_size=13)
        fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
        st.plotly_chart(fig, use_container_width=True)
    with ci2:
        fig2 = go.Figure(go.Pie(
            labels=["Raw Herbs","Raw Oils","RTF","Fin. Goods","Packaging","By-Products"],
            values=[raw_herbs,raw_oils,rtf_val,fg_val,pkg_val,bal("11040900")],
            marker_colors=[GREEN,MID,"#5A9E34",AMBER,"#888780","#A0A89A"],
            hole=0.45, textinfo="label+percent", textfont=dict(color=TEXT)))
        fig2.update_layout(title="Inventory value (LYD)",margin=dict(l=0,r=0,t=36,b=0),
                           height=260,paper_bgcolor=PLOT_BG,font_color=TEXT,
                           title_font_color=MUTED,title_font_size=13,
                           legend=dict(font=dict(size=11,color=TEXT)))
        st.plotly_chart(fig2, use_container_width=True)

    ci3, ci4 = st.columns(2)
    def top_p(loc_id,n=10):
        items=[(q["product_id"][1],round(q["quantity"])) for q in quants if q["location_id"][0]==loc_id]
        return sorted(items,key=lambda x:-x[1])[:n]
    with ci3:
        items=top_p(55)
        if items:
            df=pd.DataFrame(items,columns=["Product","Qty"])
            fig=px.bar(df,x="Qty",y="Product",orientation="h",
                       color_discrete_sequence=[GREEN],title="SJ/FG — top products")
            fig.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=320,
                              plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,font_color=TEXT,
                              title_font_color=MUTED,title_font_size=13)
            fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
            st.plotly_chart(fig, use_container_width=True)
    with ci4:
        items=top_p(45)
        if items:
            df=pd.DataFrame(items,columns=["Product","Qty"])
            fig=px.bar(df,x="Qty",y="Product",orientation="h",
                       color_discrete_sequence=[AMBER],title="HD/FG — top products")
            fig.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=320,
                              plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,font_color=TEXT,
                              title_font_color=MUTED,title_font_size=13)
            fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
            st.plotly_chart(fig, use_container_width=True)

    st.markdown(f"<hr style='border-color:{BORDER};margin:16px 0'>", unsafe_allow_html=True)
    st.markdown(f"<p style='font-weight:600;font-size:15px;margin-bottom:10px'>Sales — last 30 days</p>",
                unsafe_allow_html=True)
    if sales:
        df_s=pd.DataFrame(sales)
        df_s["date"]=pd.to_datetime(df_s["date_order"]).dt.date
        df_d=df_s.groupby("date")["amount_total"].sum().reset_index()
        df_d.columns=["Date","Revenue (LYD)"]
        fig=px.area(df_d,x="Date",y="Revenue (LYD)",color_discrete_sequence=[MID])
        fig.update_traces(fill="tozeroy",fillcolor="rgba(59,109,17,0.3)",line_color=MID)
        fig.update_layout(margin=dict(l=0,r=0,t=10,b=0),height=200,
                          plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,font_color=TEXT)
        fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
        st.plotly_chart(fig, use_container_width=True)

    st.markdown(f"<hr style='border-color:{BORDER};margin:16px 0'>", unsafe_allow_html=True)
    st.markdown(f"<p style='font-weight:600;font-size:15px;margin-bottom:10px'>Tasks</p>",
                unsafe_allow_html=True)
    tt1, tt2 = st.columns([1,1.3])
    with tt1:
        df_p=pd.DataFrame([{"Project":p["name"],"Tasks":p["task_count"]}
                            for p in projects if p["task_count"]>0]).sort_values("Tasks",ascending=True)
        fig=px.bar(df_p,x="Tasks",y="Project",orientation="h",color_discrete_sequence=[MID])
        fig.update_layout(margin=dict(l=0,r=0,t=10,b=0),height=300,
                          plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,font_color=TEXT)
        fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
        st.plotly_chart(fig, use_container_width=True)
    with tt2:
        st.markdown(f"<p style='font-size:13px;color:{MUTED};margin-bottom:6px'>Overdue tasks</p>",
                    unsafe_allow_html=True)
        if overdue:
            rows=[]
            for t in overdue:
                u=", ".join(USER_NAMES.get(x,str(x)) for x in t["user_ids"]) or "—"
                dl=t["date_deadline"][:10] if t["date_deadline"] else "—"
                rows.append({"Task":t["name"],"Project":t["project_id"][1] if t["project_id"] else "—",
                             "Owner":u,"Deadline":dl,"!":"🔴" if t["priority"]=="1" else ""})
            st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        else:
            st.markdown(f'<div class="al al-o">✅ No overdue tasks.</div>',unsafe_allow_html=True)

    st.markdown(f"<hr style='border-color:{BORDER};margin:16px 0'>", unsafe_allow_html=True)
    st.markdown(f"<p style='font-weight:600;font-size:15px;margin-bottom:10px'>Accounting</p>",
                unsafe_allow_html=True)
    acct_rows=[("11040100","Raw Herbs",raw_herbs,False),("11040150","Raw Oils",raw_oils,False),
               ("11040200","WIP",wip,abs(wip)>100),("11040300","Finished Goods",fg_val,False),
               ("11040500","Packaging",pkg_val,False),("11040800","RTF",rtf_val,False),
               ("11040900","By-Products",bal("11040900"),False),
               ("11060000","Interim Received",interim,interim>50000),("51010000","COGS",cogs,False)]
    st.dataframe(pd.DataFrame([{"Code":c,"Account":n,"Balance (LYD)":f"{v:,.2f}",
                                 "Status":"⚠️ CRITICAL" if f else "✅ OK"}
                                for c,n,v,f in acct_rows]),
                 use_container_width=True,hide_index=True)

# ════════════════════════════════════════════════════════
# TAB 2 — SALES BY SALESPERSON
# ════════════════════════════════════════════════════════
with tab2:
    st.markdown(f"<p style='font-weight:600;font-size:18px;margin-bottom:16px'>💰 Sales performance — last 30 days</p>",
                unsafe_allow_html=True)

    # Build per-person stats from Odoo sales
    persons = {}
    for o in sales:
        uid  = o["user_id"][0] if o["user_id"] else 0
        name = o["user_id"][1] if o["user_id"] else "Unknown"
        dt   = o["date_order"][:10]
        if uid not in persons:
            persons[uid] = {"name":name,"orders":0,"total":0.0,"dates":[]}
        persons[uid]["orders"] += 1
        persons[uid]["total"]  += o["amount_total"]
        persons[uid]["dates"].append(dt)

    if not persons:
        st.markdown(f'<div class="al al-w">⚠️ No sales data found for the last 30 days.</div>',
                    unsafe_allow_html=True)
    else:
        sorted_persons = sorted(persons.items(), key=lambda x:-x[1]["total"])
        total_rev  = sum(p["total"]  for _,p in sorted_persons)
        total_ords = sum(p["orders"] for _,p in sorted_persons)

        # Top KPIs
        tk1,tk2,tk3 = st.columns(3)
        def tkpi(col,lbl,num,sub="",color=AMBER):
            col.markdown(f"""<div class="kpi" style="height:80px">
              <div class="kpi-lbl">{lbl}</div>
              <div class="kpi-num" style="color:{color}">{num}</div>
              <div class="kpi-sub">{sub}</div>
            </div>""", unsafe_allow_html=True)
        tkpi(tk1,"Total revenue",   f"{total_rev:,.0f}",  "LYD — 30 days")
        tkpi(tk2,"Total orders",    str(total_ords),       "confirmed + done")
        tkpi(tk3,"Avg order value", f"{total_rev/total_ords:,.0f}" if total_ords else "—", "LYD")

        st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

        # Leaderboard bar chart
        df_sp = pd.DataFrame([{"Salesperson":p["name"],
                                "Revenue (LYD)":round(p["total"]),
                                "Orders":p["orders"]}
                               for _,p in sorted_persons])
        sc1, sc2 = st.columns(2)
        with sc1:
            fig=px.bar(df_sp.sort_values("Revenue (LYD)",ascending=True),
                       x="Revenue (LYD)",y="Salesperson",orientation="h",
                       color_discrete_sequence=[AMBER],title="Revenue by salesperson (LYD)")
            fig.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=280,
                              plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,font_color=TEXT,
                              title_font_color=MUTED,title_font_size=13)
            fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
            st.plotly_chart(fig, use_container_width=True)
        with sc2:
            fig=px.bar(df_sp.sort_values("Orders",ascending=True),
                       x="Orders",y="Salesperson",orientation="h",
                       color_discrete_sequence=[MID],title="Order count by salesperson")
            fig.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=280,
                              plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,font_color=TEXT,
                              title_font_color=MUTED,title_font_size=13)
            fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
            st.plotly_chart(fig, use_container_width=True)

        # Per-person cards
        st.markdown(f"<p style='font-weight:600;font-size:15px;margin:16px 0 10px'>Individual performance</p>",
                    unsafe_allow_html=True)
        sp_cols = st.columns(min(len(sorted_persons), 3))
        colors_cycle = [AMBER, MID, "#5A9E34", "#888780", RED]
        for i, (uid, p) in enumerate(sorted_persons):
            col = sp_cols[i % 3]
            share = round(p["total"] / total_rev * 100, 1) if total_rev else 0
            avg   = round(p["total"] / p["orders"], 0) if p["orders"] else 0
            rank  = i + 1
            medal = "🥇" if rank==1 else "🥈" if rank==2 else "🥉" if rank==3 else f"#{rank}"
            c = colors_cycle[i % len(colors_cycle)]
            col.markdown(f"""<div class="sp-card">
              <div class="sp-name">{medal} {p["name"]}</div>
              <div>
                <div class="sp-stat">
                  <div class="sp-stat-val" style="color:{c}">{p["total"]:,.0f}</div>
                  <div class="sp-stat-lbl">LYD revenue</div>
                </div>
                <div class="sp-stat">
                  <div class="sp-stat-val" style="color:{c}">{p["orders"]}</div>
                  <div class="sp-stat-lbl">orders</div>
                </div>
                <div class="sp-stat">
                  <div class="sp-stat-val" style="color:{c}">{avg:,.0f}</div>
                  <div class="sp-stat-lbl">avg LYD/order</div>
                </div>
                <div class="sp-stat">
                  <div class="sp-stat-val" style="color:{c}">{share}%</div>
                  <div class="sp-stat-lbl">of total sales</div>
                </div>
              </div>
            </div>""", unsafe_allow_html=True)

        # Daily trend per salesperson
        st.markdown(f"<p style='font-weight:600;font-size:15px;margin:20px 0 10px'>Daily revenue trend</p>",
                    unsafe_allow_html=True)
        df_daily = pd.DataFrame([
            {"Date": o["date_order"][:10],
             "Salesperson": o["user_id"][1] if o["user_id"] else "Unknown",
             "Amount": o["amount_total"]}
            for o in sales
        ])
        df_daily["Date"] = pd.to_datetime(df_daily["Date"])
        df_grp = df_daily.groupby(["Date","Salesperson"])["Amount"].sum().reset_index()
        fig = px.line(df_grp, x="Date", y="Amount", color="Salesperson",
                      color_discrete_sequence=[AMBER, MID, "#5A9E34", "#888780", RED],
                      title="Daily revenue per salesperson (LYD)")
        fig.update_layout(margin=dict(l=0,r=0,t=36,b=0), height=280,
                          plot_bgcolor=PLOT_BG, paper_bgcolor=PLOT_BG, font_color=TEXT,
                          title_font_color=MUTED, title_font_size=13,
                          legend=dict(font=dict(color=TEXT)))
        fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
        st.plotly_chart(fig, use_container_width=True)

        # Full table
        st.markdown(f"<p style='font-size:13px;color:{MUTED};margin:12px 0 6px'>All orders</p>",
                    unsafe_allow_html=True)
        df_table = pd.DataFrame([{
            "Order": o["name"],
            "Salesperson": o["user_id"][1] if o["user_id"] else "—",
            "Amount (LYD)": f"{o['amount_total']:,.2f}",
            "Date": o["date_order"][:10],
        } for o in sorted(sales, key=lambda x: x["date_order"], reverse=True)])
        st.dataframe(df_table, use_container_width=True, hide_index=True)

# ════════════════════════════════════════════════════════
# TAB 3 — FB / IG INBOX
# ════════════════════════════════════════════════════════
with tab3:
    st.markdown(f"<p style='font-weight:600;font-size:18px;margin-bottom:16px'>💬 Facebook / Instagram inbox stats</p>",
                unsafe_allow_html=True)

    with st.spinner("Fetching Meta inbox data…"):
        meta = fetch_meta()

    if meta.get("error"):
        st.markdown(f'<div class="al al-c">🔴 Meta API error: {meta["error"]}</div>',
                    unsafe_allow_html=True)
    else:
        s     = meta.get("summary", {})
        convos= meta.get("conversations", [])
        daily = meta.get("daily", [])

        if not convos:
            st.markdown(f'<div class="al al-w">⚠️ No conversations found.</div>',
                        unsafe_allow_html=True)
        else:
            avg_resp = s.get("avg_resp_min")

            # KPIs
            mk1,mk2,mk3,mk4,mk5,mk6 = st.columns(6)
            def mkpi(col,lbl,num,sub="",color=AMBER):
                col.markdown(f"""<div class="kpi">
                  <div class="kpi-lbl">{lbl}</div>
                  <div class="kpi-num" style="color:{color}">{num}</div>
                  <div class="kpi-sub">{sub}</div>
                </div>""", unsafe_allow_html=True)

            mkpi(mk1,"Conversations",     str(s.get("total_convos",0)), "FB threads")
            mkpi(mk2,"Messages received", str(s.get("total_rcvd",0)),   "from customers")
            mkpi(mk3,"Messages sent",     str(s.get("total_sent",0)),   "by page")
            mkpi(mk4,"Avg response",
                 f"{avg_resp} min" if avg_resp else "—", "first reply",
                 RED if avg_resp and avg_resp>60 else MID if avg_resp else MUTED)
            mkpi(mk5,"Fast replies ≤30m", str(s.get("fast_replies",0)), "conversations", MID)
            mkpi(mk6,"Slow replies >60m", str(s.get("slow_replies",0)), "conversations",
                 RED if s.get("slow_replies",0)>5 else AMBER)

            st.markdown(f"<hr style='border-color:{BORDER};margin:16px 0'>", unsafe_allow_html=True)

            # Daily message volume chart
            if daily:
                df_day = pd.DataFrame(daily)
                df_day["Date"] = pd.to_datetime(df_day["Date"])
                mc1, mc2 = st.columns(2)
                with mc1:
                    fig = px.bar(df_day, x="Date", y=["Received","Sent"],
                                 barmode="group",
                                 color_discrete_sequence=[AMBER, MID],
                                 title="Daily message volume")
                    fig.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=240,
                                      plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,
                                      font_color=TEXT,title_font_color=MUTED,
                                      title_font_size=13,
                                      legend=dict(font=dict(color=TEXT)))
                    fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
                    st.plotly_chart(fig, use_container_width=True)

                with mc2:
                    resp_times = [c["resp_min"] for c in convos if c["resp_min"] is not None]
                    if resp_times:
                        df_rt = pd.DataFrame({"Response time (min)": resp_times})
                        fig2 = px.histogram(df_rt, x="Response time (min)",
                                            color_discrete_sequence=[AMBER],
                                            title="Response time distribution")
                        fig2.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=240,
                                           plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,
                                           font_color=TEXT,title_font_color=MUTED,
                                           title_font_size=13)
                        fig2.update_xaxes(gridcolor=BORDER); fig2.update_yaxes(gridcolor=BORDER)
                        st.plotly_chart(fig2, use_container_width=True)

            # Conversation table
            st.markdown(f"<p style='font-size:13px;color:{MUTED};margin:12px 0 6px'>All conversations (latest 100)</p>",
                        unsafe_allow_html=True)
            df_conv = pd.DataFrame([{
                "Customer":    c["customer"],
                "Last active": c["updated"],
                "Msgs in":     c["received"],
                "Msgs out":    c["sent"],
                "Total":       c["total"],
                "Response":    f"{c['resp_min']} min" if c["resp_min"] is not None else "—",
            } for c in sorted(convos, key=lambda x: x["updated"], reverse=True)])
            st.dataframe(df_conv, use_container_width=True, hide_index=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="margin-top:24px;padding:10px 0;border-top:1px solid {BORDER};
            font-size:11px;color:{MUTED};text-align:center">
  Auria Operations Dashboard · refreshes every 30s · {ODOO_URL}
</div>""", unsafe_allow_html=True)
st.markdown("<script>setTimeout(()=>window.location.reload(),30000);</script>",
            unsafe_allow_html=True)
