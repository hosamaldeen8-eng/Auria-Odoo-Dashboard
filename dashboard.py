"""Auria — Live Operations Dashboard"""

import xmlrpc.client, urllib.request, urllib.parse, urllib.error
import json, streamlit as st, pandas as pd
import plotly.express as px, plotly.graph_objects as go
from datetime import date, datetime, timedelta

# ── Credentials ───────────────────────────────────────────────────────────────
ODOO_URL  = "https://odoo.auria.global"
ODOO_DB   = "Auria_Business"; ODOO_UID = 8; ODOO_PWD = "123456"
PAGE_ID   = "145285001991586"; IG_ID = "17841462343514591"
AD_ACCT   = "act_1304156338260899"
USER_TOKEN= "EAASVMwJoNLIBRgwWum1jWBbWdpZCnn0bh42jIujGBr5EqRhOEIz5IW47oZBvDL3Xh1CGHyNmGTfOgTDufLwth2I76M3mhZBRP03voZBL83IbOXZA8BW1ZBubwYeePPZAbZCy7mPbZAgC5OJFGTEPAhNDSRmc0SeFHtECyqui88k7Caz70AEH87kAZCePIf4qmdINHMZBHQtquKy1qFrQwz3LkU5H2QBb39knwZBYhc3JaTXmL7uv8AMVuYm8upuIZA1RSoyDhyZCI06A0erwchSX0Xa50ZCrd7BegZDZD"

# ── Palette ───────────────────────────────────────────────────────────────────
BG="#0e1a0f";BG2="#1a2b1b";CARD="#1e2e1f";BORDER="#2d452e"
TEXT="#e8f5e9";MUTED="#7aaa78";GREEN="#1F3420";MID="#3B6D11"
AMBER="#D4A853";RED="#A32D2D";BLUE="#2d6fa8";PLOT_BG="#141e15"
CRIT_BG="#2e1010";CRIT_FG="#f4a0a0";CRIT_BD="#A32D2D"
WARN_BG="#2e2610";WARN_FG="#f4d080";WARN_BD="#D4A853"
OK_BG="#0f2010";OK_FG="#88cc88";OK_BD="#3B6D11"
INFO_BG="#0e1e2e";INFO_FG="#80b8f0";INFO_BD="#2d6fa8"

LOC_NAMES={37:"SJ/RM-Raw",38:"SJ/PKG",39:"SJ/RTF",55:"SJ/FG",45:"HD/FG"}
USER_NAMES={8:"Hussam",18:"Abdullah",29:"Ala' Deep",9:"Alaa Oshah",
            15:"Marwan",13:"Nasser",27:"Khan",11:"Wesal",23:"Bader",6:"Moad"}
DONE_STAGES=[14,15,28,29,41,66,68,70,74,75,79,83]

# ── Odoo ──────────────────────────────────────────────────────────────────────
@st.cache_resource
def get_models():
    return xmlrpc.client.ServerProxy(f"{ODOO_URL}/xmlrpc/2/object")

def odoo(model,method,domain=None,kwargs=None):
    return get_models().execute_kw(ODOO_DB,ODOO_UID,ODOO_PWD,
        model,method,[domain or []],kwargs or {})

# ── Meta ──────────────────────────────────────────────────────────────────────
def meta(path,params=None,token=None):
    p=params or {}; p["access_token"]=token or USER_TOKEN
    url=f"https://graph.facebook.com/v19.0/{path}?{urllib.parse.urlencode(p)}"
    try:
        r=urllib.request.urlopen(url,timeout=15); return json.loads(r.read())
    except urllib.error.HTTPError as e: return json.loads(e.read())
    except Exception as ex: return {"error":str(ex)}

@st.cache_data(ttl=3600)
def get_page_token():
    pages=meta("me/accounts",{"fields":"id,name,access_token"})
    return next((p["access_token"] for p in pages.get("data",[]) if p["id"]==PAGE_ID),None)

# ── Data fetchers ─────────────────────────────────────────────────────────────
@st.cache_data(ttl=30)
def fetch_odoo(cache_key=None):
    today=cache_key or str(date.today())
    thirty_ago=str(date.today()-timedelta(days=30))
    tasks=odoo("project.task","search_read",[["active","=",True]],
        {"fields":["name","project_id","user_ids","priority","date_deadline","stage_id"],"limit":300})
    mos=odoo("mrp.production","search_read",[["state","in",["confirmed","progress"]]],
        {"fields":["name","product_id","product_qty","state"],"limit":50})
    quants=odoo("stock.quant","search_read",
        [["location_id","in",[37,38,39,55,45]],["quantity",">",0]],
        {"fields":["product_id","location_id","quantity"],"limit":400})
    acct=odoo("account.move.line","read_group",
        [["account_id.code","in",["11040100","11040150","11040200","11040300",
          "11040500","11040800","11040900","11060000","51010000"]],
         ["move_id.state","=","posted"]],
        {"fields":["account_id","balance:sum"],"groupby":["account_id"]})
    overdue=odoo("project.task","search_read",
        [["date_deadline","<",today],["active","=",True],["stage_id","not in",DONE_STAGES]],
        {"fields":["name","project_id","user_ids","date_deadline","priority","stage_id"],"limit":100})
    projects=odoo("project.project","search_read",[],{"fields":["id","name","task_count"]})
    sales=odoo("sale.order","search_read",
        [["state","in",["sale","done"]],["date_order",">=",thirty_ago]],
        {"fields":["name","amount_total","date_order","user_id"],"limit":500})
    return dict(tasks=tasks,mos=mos,quants=quants,acct=acct,
                overdue=overdue,projects=projects,sales=sales,today=today)

@st.cache_data(ttl=300)
def fetch_meta_all():
    pt=get_page_token()
    if not pt: return {"error":"No page token"}

    # ── Conversations (paginated) ──────────────────────────────────────────
    all_convos=[]
    params={"fields":"id,updated_time,message_count,participants,messages{from,created_time,tags}","limit":"25"}
    batch=meta(f"{PAGE_ID}/conversations",params,token=pt)
    if "error" in batch: return {"error":str(batch["error"])}
    all_convos.extend(batch.get("data",[]))
    cursor=batch.get("paging",{}).get("cursors",{}).get("after")
    while cursor and len(all_convos)<150:
        p2=dict(params); p2["after"]=cursor
        batch=meta(f"{PAGE_ID}/conversations",p2,token=pt)
        data=batch.get("data",[]); 
        if not data: break
        all_convos.extend(data)
        cursor=batch.get("paging",{}).get("cursors",{}).get("after")

    # Parse conversations
    convos_parsed=[]; resp_times=[]; daily={}
    for c in all_convos:
        msgs=c.get("messages",{}).get("data",[])
        if not msgs: continue
        sent=sum(1 for m in msgs if m.get("from",{}).get("id")==PAGE_ID)
        rcvd=len(msgs)-sent
        day=c.get("updated_time","")[:10]
        customer=next((p["name"] for p in c.get("participants",{}).get("data",[])
                       if p["id"]!=PAGE_ID),"Unknown")
        # Platform detection from tags
        platform="Messenger"
        for m in msgs:
            for t in m.get("tags",{}).get("data",[]):
                if "instagram" in t.get("name","").lower():
                    platform="Instagram"; break

        # Response time
        sorted_msgs=sorted(msgs,key=lambda x:x.get("created_time",""))
        resp_min=None
        for i,m in enumerate(sorted_msgs):
            if m.get("from",{}).get("id")!=PAGE_ID:
                for j in range(i+1,len(sorted_msgs)):
                    if sorted_msgs[j].get("from",{}).get("id")==PAGE_ID:
                        t1=datetime.fromisoformat(m["created_time"].replace("Z","+00:00"))
                        t2=datetime.fromisoformat(sorted_msgs[j]["created_time"].replace("Z","+00:00"))
                        diff=(t2-t1).total_seconds()/60
                        if diff>=0: resp_min=round(diff,1); resp_times.append(resp_min)
                        break
                break

        convos_parsed.append({"customer":customer,"updated":day,"platform":platform,
                               "total":len(msgs),"sent":sent,"received":rcvd,"resp_min":resp_min})
        if day:
            daily.setdefault(day,{"received":0,"sent":0,"Messenger":0,"Instagram":0})
            daily[day]["received"]+=rcvd; daily[day]["sent"]+=sent
            daily[day][platform]=daily[day].get(platform,0)+1

    # ── Ads ────────────────────────────────────────────────────────────────
    ads_raw=meta(f"{AD_ACCT}/insights",
        {"fields":"campaign_name,campaign_id,impressions,reach,spend,clicks,cpm,actions,cost_per_action_type,objective",
         "date_preset":"last_30d","level":"campaign","limit":"25"})

    ads_parsed=[]
    total_spend=0; total_msgs_from_ads=0; total_reach=0; total_impressions=0
    for a in ads_raw.get("data",[]):
        actions={x["action_type"]:float(x["value"]) for x in a.get("actions",[])}
        cpas   ={x["action_type"]:float(x["value"]) for x in a.get("cost_per_action_type",[])}
        spend  =float(a.get("spend",0))
        msgs   =actions.get("onsite_conversion.total_messaging_connection",0)
        replies=actions.get("onsite_conversion.messaging_first_reply",0)
        welcome=actions.get("onsite_conversion.messaging_welcome_message_view",0)
        cpm    =float(a.get("cpm",0))
        reach  =int(a.get("reach",0))
        impr   =int(a.get("impressions",0))
        clicks =int(a.get("clicks",0))
        cpm_msg=cpas.get("onsite_conversion.total_messaging_connection",0)
        total_spend+=spend; total_msgs_from_ads+=msgs
        total_reach+=reach; total_impressions+=impr
        if spend>0 or msgs>0:
            ads_parsed.append({
                "campaign":a["campaign_name"].replace('\u202a','').replace('\u202c','').strip()[:55],
                "spend":spend,"reach":reach,"impressions":impr,"clicks":clicks,
                "msgs_started":int(msgs),"first_replies":int(replies),
                "welcome_views":int(welcome),"cpm":round(cpm,3),
                "cost_per_msg":round(cpm_msg,3) if cpm_msg else None,
                "reply_rate":round(replies/msgs*100,1) if msgs>0 else 0,
                "click_to_msg":round(msgs/clicks*100,1) if clicks>0 else 0,
            })
    ads_parsed.sort(key=lambda x:-x["msgs_started"])

    summary_convos={
        "total":len(convos_parsed),
        "total_rcvd":sum(c["received"] for c in convos_parsed),
        "total_sent":sum(c["sent"]     for c in convos_parsed),
        "avg_resp":round(sum(resp_times)/len(resp_times),1) if resp_times else None,
        "fast":sum(1 for r in resp_times if r<=30),
        "slow":sum(1 for r in resp_times if r>60),
        "messenger":sum(1 for c in convos_parsed if c["platform"]=="Messenger"),
        "instagram":sum(1 for c in convos_parsed if c["platform"]=="Instagram"),
    }
    summary_ads={
        "total_spend":round(total_spend,2),
        "total_msgs":int(total_msgs_from_ads),
        "total_reach":total_reach,
        "total_impressions":total_impressions,
        "avg_cpm":round(total_impressions and total_spend/total_impressions*1000,3) if total_impressions else 0,
        "avg_cost_per_msg":round(total_spend/total_msgs_from_ads,3) if total_msgs_from_ads else 0,
        "msg_to_sale_rate": None,  # linked below via Odoo
    }
    daily_list=[{"Date":k,"Received":v["received"],"Sent":v["sent"],
                 "Messenger":v.get("Messenger",0),"Instagram":v.get("Instagram",0)}
                for k,v in sorted(daily.items())]

    return dict(convos=convos_parsed,ads=ads_parsed,
                sum_c=summary_convos,sum_a=summary_ads,daily=daily_list)

# ── Page config ───────────────────────────────────────────────────────────────
st.set_page_config(page_title="Auria — Operations",page_icon="🌿",
                   layout="wide",initial_sidebar_state="collapsed")

st.markdown(f"""<style>
  html,body,[data-testid="stAppViewContainer"],[data-testid="stHeader"],
  section.main>div{{background-color:{BG} !important}}
  [data-testid="stSidebar"]{{background-color:{BG2} !important}}
  h1,h2,h3,h4,h5,h6,p,span,label,div{{color:{TEXT}}}
  [data-testid="stTabs"] button{{color:{MUTED} !important;font-size:14px}}
  [data-testid="stTabs"] button[aria-selected="true"]{{color:{AMBER} !important;
      border-bottom:2px solid {AMBER} !important}}
  hr{{border-color:{BORDER}}}
  .kpi{{background:{CARD};border:0.5px solid {BORDER};border-radius:12px;padding:14px 16px;min-height:90px}}
  .kpi-lbl{{font-size:11px;color:{MUTED};margin-bottom:4px;text-transform:uppercase;letter-spacing:.04em}}
  .kpi-num{{font-size:26px;font-weight:600;line-height:1.1}}
  .kpi-sub{{font-size:11px;color:{MUTED};margin-top:2px}}
  .al{{display:flex;gap:10px;align-items:flex-start;padding:10px 14px;border-radius:8px;margin-bottom:8px;font-size:13px}}
  .al-c{{background:{CRIT_BG};border-left:4px solid {CRIT_BD};color:{CRIT_FG}}}
  .al-w{{background:{WARN_BG};border-left:4px solid {WARN_BD};color:{WARN_FG}}}
  .al-o{{background:{OK_BG};border-left:4px solid {OK_BD};color:{OK_FG}}}
  .al-i{{background:{INFO_BG};border-left:4px solid {INFO_BD};color:{INFO_FG}}}
  .mo{{background:{CARD};border:0.5px solid {BORDER};border-radius:12px;padding:12px 16px;margin-bottom:10px}}
  .badge{{display:inline-block;padding:3px 10px;border-radius:20px;font-size:11px;font-weight:500;margin-right:6px}}
  .bg{{background:{OK_BG};color:{OK_FG}}}
  .ba{{background:{WARN_BG};color:{WARN_FG}}}
  .bi{{background:{INFO_BG};color:{INFO_FG}}}
  .ad-card{{background:{CARD};border:0.5px solid {BORDER};border-radius:12px;padding:14px 16px;margin-bottom:10px}}
  .ad-title{{font-size:13px;font-weight:500;color:{TEXT};margin-bottom:10px;line-height:1.4}}
  .ad-stat{{display:inline-block;background:{BG2};border-radius:8px;padding:6px 10px;
            margin:3px;text-align:center;min-width:70px}}
  .ad-val{{font-size:16px;font-weight:600}}
  .ad-lbl{{font-size:10px;color:{MUTED}}}
  .sp-card{{background:{CARD};border:0.5px solid {BORDER};border-radius:12px;padding:16px;margin-bottom:10px}}
  .sp-name{{font-size:16px;font-weight:600;color:{TEXT};margin-bottom:10px}}
  .sp-stat{{display:inline-block;padding:6px 12px;border-radius:8px;background:{BG2};margin:3px;text-align:center}}
  .sp-val{{font-size:18px;font-weight:600}}
  .sp-lbl{{font-size:10px;color:{MUTED}}}
  .plat-fb{{background:#1a2e45;color:#5b9bd5;border-radius:4px;padding:1px 7px;font-size:11px}}
  .plat-ig{{background:#2e1a2e;color:#c97bc9;border-radius:4px;padding:1px 7px;font-size:11px}}
  .stButton>button{{background:{CARD};border:0.5px solid {BORDER};color:{TEXT};border-radius:8px}}
  .stButton>button:hover{{background:{BG2};border-color:{MID}}}
  footer{{visibility:hidden}}
</style>""",unsafe_allow_html=True)

# ── Header ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="background:{GREEN};border-radius:12px;padding:16px 22px;margin-bottom:16px;
            display:flex;align-items:center;justify-content:space-between">
  <div>
    <div style="font-size:20px;font-weight:600;color:#fff">🌿 Auria — لوحة العمليات</div>
    <div style="font-size:12px;color:#8fb88a;margin-top:2px">Live · Odoo + Facebook Ads + Messenger</div>
  </div>
  <div style="font-size:13px;color:#8fb88a;text-align:right">
    {datetime.now().strftime("%A, %d %B %Y")}<br>
    <span style="font-size:11px">{datetime.now().strftime("%H:%M:%S")}</span>
  </div>
</div>""",unsafe_allow_html=True)

rc,rt=st.columns([1,6])
with rc:
    if st.button("🔄 Refresh"):
        st.cache_data.clear(); st.rerun()
with rt:
    st.markdown(f"<span style='font-size:11px;color:{MUTED}'>Auto-refreshes every 30s</span>",unsafe_allow_html=True)

# ── Load ──────────────────────────────────────────────────────────────────────
with st.spinner("Fetching Odoo + Meta data…"):
    od=fetch_odoo(cache_key=str(date.today()))
    md=fetch_meta_all()

tasks=od["tasks"]; mos=od["mos"]; quants=od["quants"]; acct=od["acct"]
overdue=od["overdue"]; projects=od["projects"]; sales=od["sales"]; today=od["today"]

acct_map={}
for a in acct:
    n=a["account_id"][1] if a["account_id"] else ""
    acct_map[n]=round(a.get("balance",0) or 0,2)
def bal(code):
    for k,v in acct_map.items():
        if k.startswith(code): return v
    return 0

raw_herbs=bal("11040100");raw_oils=bal("11040150");wip=bal("11040200")
fg_val=bal("11040300");pkg_val=bal("11040500");rtf_val=bal("11040800")
interim=abs(bal("11060000"));cogs=bal("51010000")
total_sales=sum(s["amount_total"] for s in sales)
urgent=sum(1 for t in tasks if t["priority"]=="1")
n_over=len(overdue); n_mos=len(mos)

def kpi(col,lbl,num,sub="",color=AMBER):
    col.markdown(f"""<div class="kpi"><div class="kpi-lbl">{lbl}</div>
      <div class="kpi-num" style="color:{color}">{num}</div>
      <div class="kpi-sub">{sub}</div></div>""",unsafe_allow_html=True)

# ════════════════ TABS ════════════════════════════════════════════════════════
tab1,tab2,tab3=st.tabs(["📊  Operations","💰  Sales & Team","📣  Marketing & Inbox"])

# ══════════════════════════════════════════════════════════════════════════════
# TAB 1 — OPERATIONS
# ══════════════════════════════════════════════════════════════════════════════
with tab1:
    st.markdown(f"<p style='font-size:12px;color:{MUTED};margin-bottom:8px;text-transform:uppercase;letter-spacing:.05em'>Key performance indicators</p>",unsafe_allow_html=True)
    c=st.columns(6)
    kpi(c[0],"Sales 30d",f"{total_sales:,.0f}","LYD")
    kpi(c[1],"Finished Goods",f"{fg_val:,.0f}","LYD")
    kpi(c[2],"Packaging",f"{pkg_val:,.0f}","LYD")
    kpi(c[3],"Active MOs",str(n_mos),"orders",MID)
    kpi(c[4],"Overdue tasks",str(n_over),f"{urgent} urgent",RED if n_over>3 else AMBER)
    kpi(c[5],"Interim Rcvd",f"{interim:,.0f}","⚠️ CRITICAL" if interim>50000 else "LYD",
        RED if interim>50000 else AMBER)
    st.markdown(f"<hr style='border-color:{BORDER};margin:14px 0'>",unsafe_allow_html=True)

    ca,cm=st.columns([1.2,1])
    with ca:
        st.markdown(f"<p style='font-weight:600;font-size:14px;margin-bottom:8px'>Alerts</p>",unsafe_allow_html=True)
        if interim>50000: st.markdown(f'<div class="al al-c">🔴 <span><b>Interim {interim:,.0f} LYD</b> — exceeds 50K. Unmatched vendor bills.</span></div>',unsafe_allow_html=True)
        st.markdown(f'<div class="al al-{"w" if abs(wip)>100 else "o"}">{"⚠️" if abs(wip)>100 else "✅"} <span><b>WIP {wip:,.2f} LYD</b> — {"unclosed MOs!" if abs(wip)>100 else "clean."}</span></div>',unsafe_allow_html=True)
        if n_over>0: st.markdown(f'<div class="al al-w">⚠️ <span><b>{n_over} overdue tasks</b> — {urgent} urgent.</span></div>',unsafe_allow_html=True)
        else: st.markdown('<div class="al al-o">✅ <span>No overdue tasks.</span></div>',unsafe_allow_html=True)
        if n_mos>0: st.markdown(f'<div class="al al-o">🏭 <span>{", ".join(m["name"] for m in mos)}</span></div>',unsafe_allow_html=True)
    with cm:
        st.markdown(f"<p style='font-weight:600;font-size:14px;margin-bottom:8px'>Active MOs</p>",unsafe_allow_html=True)
        for m in mos:
            st.markdown(f"""<div class="mo"><b style="font-size:13px">{m["name"]}</b>
              <div style="font-size:12px;color:{MUTED};margin:4px 0">{m["product_id"][1]}</div>
              <span class="badge bg">{m["product_qty"]} units</span>
              <span class="badge {"bg" if m["state"]=="progress" else "ba"}">{m["state"]}</span>
            </div>""",unsafe_allow_html=True)
        if not mos: st.markdown(f'<div class="al al-o">No active MOs.</div>',unsafe_allow_html=True)

    st.markdown(f"<hr style='border-color:{BORDER};margin:14px 0'>",unsafe_allow_html=True)
    st.markdown(f"<p style='font-weight:600;font-size:14px;margin-bottom:8px'>Inventory</p>",unsafe_allow_html=True)
    i1,i2=st.columns(2)
    with i1:
        lt={}
        for q in quants: lt[q["location_id"][0]]=lt.get(q["location_id"][0],0)+q["quantity"]
        df_l=pd.DataFrame([{"Location":LOC_NAMES.get(k,str(k)),"Units":round(v)} for k,v in lt.items()]).sort_values("Units",ascending=True)
        fig=px.bar(df_l,x="Units",y="Location",orientation="h",color_discrete_sequence=[MID],title="Units by location")
        fig.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=240,plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,font_color=TEXT,title_font_color=MUTED,title_font_size=12)
        fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
        st.plotly_chart(fig,use_container_width=True)
    with i2:
        fig2=go.Figure(go.Pie(labels=["Raw Herbs","Raw Oils","RTF","Fin. Goods","Packaging"],
            values=[raw_herbs,raw_oils,rtf_val,fg_val,pkg_val],
            marker_colors=[GREEN,MID,"#5A9E34",AMBER,"#888780"],hole=0.45,
            textinfo="label+percent",textfont=dict(color=TEXT)))
        fig2.update_layout(title="Inventory value (LYD)",margin=dict(l=0,r=0,t=36,b=0),height=240,paper_bgcolor=PLOT_BG,font_color=TEXT,title_font_color=MUTED,title_font_size=12,legend=dict(font=dict(size=10,color=TEXT)))
        st.plotly_chart(fig2,use_container_width=True)

    i3,i4=st.columns(2)
    def top_p(loc,n=8):
        items=[(q["product_id"][1],round(q["quantity"])) for q in quants if q["location_id"][0]==loc]
        return sorted(items,key=lambda x:-x[1])[:n]
    for col,loc,color,title in [(i3,55,GREEN,"SJ/FG"),(i4,45,AMBER,"HD/FG")]:
        items=top_p(loc)
        if items:
            df=pd.DataFrame(items,columns=["Product","Qty"])
            fig=px.bar(df,x="Qty",y="Product",orientation="h",color_discrete_sequence=[color],title=f"{title} — top products")
            fig.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=280,plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,font_color=TEXT,title_font_color=MUTED,title_font_size=12)
            fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
            col.plotly_chart(fig,use_container_width=True)

    st.markdown(f"<hr style='border-color:{BORDER};margin:14px 0'>",unsafe_allow_html=True)
    if sales:
        df_s=pd.DataFrame(sales)
        df_s["date"]=pd.to_datetime(df_s["date_order"]).dt.date
        df_d=df_s.groupby("date")["amount_total"].sum().reset_index()
        df_d.columns=["Date","Revenue (LYD)"]
        fig=px.area(df_d,x="Date",y="Revenue (LYD)",color_discrete_sequence=[MID],title="Daily revenue — 30 days")
        fig.update_traces(fill="tozeroy",fillcolor="rgba(59,109,17,0.25)",line_color=MID)
        fig.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=180,plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,font_color=TEXT,title_font_color=MUTED,title_font_size=12)
        fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
        st.plotly_chart(fig,use_container_width=True)

    st.markdown(f"<hr style='border-color:{BORDER};margin:14px 0'>",unsafe_allow_html=True)
    tt1,tt2=st.columns([1,1.3])
    with tt1:
        df_p=pd.DataFrame([{"Project":p["name"],"Tasks":p["task_count"]} for p in projects if p["task_count"]>0]).sort_values("Tasks",ascending=True)
        fig=px.bar(df_p,x="Tasks",y="Project",orientation="h",color_discrete_sequence=[MID])
        fig.update_layout(margin=dict(l=0,r=0,t=10,b=0),height=260,plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,font_color=TEXT)
        fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
        st.plotly_chart(fig,use_container_width=True)
    with tt2:
        st.markdown(f"<p style='font-size:12px;color:{MUTED};margin-bottom:6px'>Overdue tasks</p>",unsafe_allow_html=True)
        if overdue:
            rows=[{"Task":t["name"],"Project":t["project_id"][1] if t["project_id"] else "—",
                   "Owner":", ".join(USER_NAMES.get(u,str(u)) for u in t["user_ids"]) or "—",
                   "Deadline":t["date_deadline"][:10] if t["date_deadline"] else "—",
                   "!":"🔴" if t["priority"]=="1" else ""} for t in overdue]
            st.dataframe(pd.DataFrame(rows),use_container_width=True,hide_index=True)
        else:
            st.markdown(f'<div class="al al-o">✅ No overdue tasks.</div>',unsafe_allow_html=True)

    st.markdown(f"<hr style='border-color:{BORDER};margin:14px 0'>",unsafe_allow_html=True)
    st.markdown(f"<p style='font-weight:600;font-size:14px;margin-bottom:8px'>Accounting</p>",unsafe_allow_html=True)
    acct_rows=[("11040100","Raw Herbs",raw_herbs,False),("11040150","Raw Oils",raw_oils,False),
               ("11040200","WIP",wip,abs(wip)>100),("11040300","Finished Goods",fg_val,False),
               ("11040500","Packaging",pkg_val,False),("11040800","RTF",rtf_val,False),
               ("11040900","By-Products",bal("11040900"),False),
               ("11060000","Interim Received",interim,interim>50000),("51010000","COGS",cogs,False)]
    st.dataframe(pd.DataFrame([{"Code":c,"Account":n,"Balance (LYD)":f"{v:,.2f}",
        "Status":"⚠️ CRITICAL" if f else "✅ OK"} for c,n,v,f in acct_rows]),
        use_container_width=True,hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 2 — SALES & TEAM
# ══════════════════════════════════════════════════════════════════════════════
with tab2:
    persons={}
    for o in sales:
        uid=o["user_id"][0] if o["user_id"] else 0
        name=o["user_id"][1] if o["user_id"] else "Unknown"
        if uid not in persons:
            persons[uid]={"name":name,"orders":0,"total":0.0,"dates":[]}
        persons[uid]["orders"]+=1; persons[uid]["total"]+=o["amount_total"]
        persons[uid]["dates"].append(o["date_order"][:10])
    sp=sorted(persons.items(),key=lambda x:-x[1]["total"])
    total_rev=sum(p["total"] for _,p in sp)
    total_ords=sum(p["orders"] for _,p in sp)

    # Get inbox stats per salesperson by linking customer names to conversations
    # (Salesperson label = conversation assigned label in Meta Business Suite)
    # Since labels aren't in API, we match by salesperson name appearing in convo participants
    convos=md.get("convos",[]) if "error" not in md else []
    sum_a=md.get("sum_a",{}) if "error" not in md else {}

    # Top KPIs row
    st.markdown(f"<p style='font-size:12px;color:{MUTED};margin-bottom:8px;text-transform:uppercase;letter-spacing:.04em'>Sales performance — last 30 days</p>",unsafe_allow_html=True)
    c=st.columns(5)
    kpi(c[0],"Total revenue",f"{total_rev:,.0f}","LYD")
    kpi(c[1],"Total orders",str(total_ords),"confirmed + done")
    kpi(c[2],"Avg order value",f"{round(total_rev/total_ords):,.0f}" if total_ords else "—","LYD per order")
    kpi(c[3],"FB msgs received",str(md.get("sum_c",{}).get("total_rcvd","—")),"from customers")
    kpi(c[4],"Msgs → orders conv.",
        f"{round(total_ords/md.get('sum_c',{}).get('total_rcvd',1)*100,1)}%" if md.get("sum_c",{}).get("total_rcvd") else "—",
        "inbox to Odoo rate",MID)

    st.markdown(f"<hr style='border-color:{BORDER};margin:14px 0'>",unsafe_allow_html=True)

    # Charts row
    sc1,sc2=st.columns(2)
    with sc1:
        df_sp=pd.DataFrame([{"Salesperson":p["name"],"Revenue (LYD)":round(p["total"]),"Orders":p["orders"]} for _,p in sp])
        fig=px.bar(df_sp.sort_values("Revenue (LYD)",ascending=True),x="Revenue (LYD)",y="Salesperson",
                   orientation="h",color_discrete_sequence=[AMBER],title="Revenue by salesperson (LYD)")
        fig.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=260,plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,font_color=TEXT,title_font_color=MUTED,title_font_size=12)
        fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
        st.plotly_chart(fig,use_container_width=True)
    with sc2:
        fig=px.bar(df_sp.sort_values("Orders",ascending=True),x="Orders",y="Salesperson",
                   orientation="h",color_discrete_sequence=[MID],title="Orders by salesperson")
        fig.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=260,plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,font_color=TEXT,title_font_color=MUTED,title_font_size=12)
        fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
        st.plotly_chart(fig,use_container_width=True)

    # Per-person cards
    st.markdown(f"<p style='font-weight:600;font-size:14px;margin:4px 0 10px'>Individual performance</p>",unsafe_allow_html=True)
    cols_sp=st.columns(min(len(sp),3))
    colors_c=[AMBER,MID,"#5A9E34","#888780",RED]
    medals=["🥇","🥈","🥉"]
    for i,(uid,p) in enumerate(sp):
        col=cols_sp[i%3]; c=colors_c[i%len(colors_c)]
        share=round(p["total"]/total_rev*100,1) if total_rev else 0
        avg=round(p["total"]/p["orders"]) if p["orders"] else 0
        medal=medals[i] if i<3 else f"#{i+1}"
        col.markdown(f"""<div class="sp-card">
          <div class="sp-name">{medal} {p["name"]}</div>
          <div>
            <div class="sp-stat"><div class="sp-val" style="color:{c}">{p["total"]:,.0f}</div><div class="sp-lbl">LYD revenue</div></div>
            <div class="sp-stat"><div class="sp-val" style="color:{c}">{p["orders"]}</div><div class="sp-lbl">orders</div></div>
            <div class="sp-stat"><div class="sp-val" style="color:{c}">{avg:,}</div><div class="sp-lbl">avg LYD/order</div></div>
            <div class="sp-stat"><div class="sp-val" style="color:{c}">{share}%</div><div class="sp-lbl">share</div></div>
          </div>
        </div>""",unsafe_allow_html=True)

    # Daily trend
    st.markdown(f"<p style='font-weight:600;font-size:14px;margin:12px 0 8px'>Daily revenue trend</p>",unsafe_allow_html=True)
    df_daily=pd.DataFrame([{"Date":o["date_order"][:10],
        "Salesperson":o["user_id"][1] if o["user_id"] else "Unknown",
        "Amount":o["amount_total"]} for o in sales])
    df_daily["Date"]=pd.to_datetime(df_daily["Date"])
    df_grp=df_daily.groupby(["Date","Salesperson"])["Amount"].sum().reset_index()
    fig=px.line(df_grp,x="Date",y="Amount",color="Salesperson",
                color_discrete_sequence=[AMBER,MID,"#5A9E34","#888780",RED],
                title="Daily revenue per salesperson")
    fig.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=240,plot_bgcolor=PLOT_BG,
                      paper_bgcolor=PLOT_BG,font_color=TEXT,title_font_color=MUTED,
                      title_font_size=12,legend=dict(font=dict(color=TEXT)))
    fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
    st.plotly_chart(fig,use_container_width=True)

    # Inbox → assign note
    st.markdown(f"""<div class="al al-i">💡 <span>
      <b>Link inbox to salesperson:</b> In Meta Business Suite, assign conversations to agents using the
      <b>"Assign to"</b> button. Once assigned, each agent's handle appears as a label.
      Go to <b>Business Suite → Inbox → All conversations → Assign</b>.
      Auria currently has {md.get("sum_c",{}).get("total",0)} tracked conversations —
      {md.get("sum_c",{}).get("total_rcvd",0)} messages received,
      avg response {md.get("sum_c",{}).get("avg_resp","—")} min.
    </span></div>""",unsafe_allow_html=True)

    # Orders table
    st.markdown(f"<p style='font-size:12px;color:{MUTED};margin:10px 0 4px'>All orders</p>",unsafe_allow_html=True)
    df_t=pd.DataFrame([{"Order":o["name"],
        "Salesperson":o["user_id"][1] if o["user_id"] else "—",
        "Amount (LYD)":f"{o['amount_total']:,.2f}",
        "Date":o["date_order"][:10]} for o in sorted(sales,key=lambda x:x["date_order"],reverse=True)])
    st.dataframe(df_t,use_container_width=True,hide_index=True)

# ══════════════════════════════════════════════════════════════════════════════
# TAB 3 — MARKETING & INBOX
# ══════════════════════════════════════════════════════════════════════════════
with tab3:
    if "error" in md:
        st.markdown(f'<div class="al al-c">🔴 Meta error: {md["error"]}</div>',unsafe_allow_html=True)
    else:
        sum_c=md.get("sum_c",{}); sum_a=md.get("sum_a",{})
        ads=md.get("ads",[]); convos=md.get("convos",[]); daily=md.get("daily",[])

        # ── Section 1: Ad performance KPIs ────────────────────────────────
        st.markdown(f"<p style='font-size:12px;color:{MUTED};text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px'>📣 Ad performance — last 30 days</p>",unsafe_allow_html=True)
        ac=st.columns(6)
        kpi(ac[0],"Total ad spend",f"${sum_a.get('total_spend',0):,.2f}","USD")
        kpi(ac[1],"Total reach",f"{sum_a.get('total_reach',0):,}","unique people")
        kpi(ac[2],"Impressions",f"{sum_a.get('total_impressions',0):,}","total views")
        kpi(ac[3],"Msgs started",str(sum_a.get('total_msgs',0)),"from ads",MID)
        kpi(ac[4],"Avg CPM",f"${sum_a.get('avg_cpm',0):.3f}","per 1000 impressions")
        kpi(ac[5],"Avg cost/msg",f"${sum_a.get('avg_cost_per_msg',0):.3f}","per conversation",
            MID if sum_a.get('avg_cost_per_msg',99)<0.15 else AMBER)

        st.markdown(f"<hr style='border-color:{BORDER};margin:14px 0'>",unsafe_allow_html=True)

        # ── Section 2: Campaign cards ──────────────────────────────────────
        st.markdown(f"<p style='font-weight:600;font-size:14px;margin-bottom:10px'>Campaign breakdown</p>",unsafe_allow_html=True)

        # Sort options
        sort_by=st.selectbox("Sort by",["Messages started","Spend","Reach","Reply rate"],
                              label_visibility="collapsed")
        sort_map={"Messages started":"msgs_started","Spend":"spend",
                  "Reach":"reach","Reply rate":"reply_rate"}
        ads_sorted=sorted(ads,key=lambda x:-x.get(sort_map[sort_by],0))

        for a in ads_sorted:
            cr=AMBER if a["reply_rate"]>30 else MUTED
            cm_color=MID if (a["cost_per_msg"] or 99)<0.1 else AMBER if (a["cost_per_msg"] or 99)<0.2 else RED
            st.markdown(f"""<div class="ad-card">
              <div class="ad-title">{a["campaign"]}</div>
              <div>
                <div class="ad-stat"><div class="ad-val" style="color:{AMBER}">${a["spend"]:.2f}</div><div class="ad-lbl">spend</div></div>
                <div class="ad-stat"><div class="ad-val" style="color:{MUTED}">{a["reach"]:,}</div><div class="ad-lbl">reach</div></div>
                <div class="ad-stat"><div class="ad-val" style="color:{MUTED}">{a["impressions"]:,}</div><div class="ad-lbl">impressions</div></div>
                <div class="ad-stat"><div class="ad-val" style="color:{MID}">{a["msgs_started"]}</div><div class="ad-lbl">msgs started</div></div>
                <div class="ad-stat"><div class="ad-val" style="color:{MID}">{a["first_replies"]}</div><div class="ad-lbl">first replies</div></div>
                <div class="ad-stat"><div class="ad-val" style="color:{cm_color}">${a["cost_per_msg"]:.3f}</div><div class="ad-lbl">cost/msg</div></div>
                <div class="ad-stat"><div class="ad-val" style="color:{cr}">{a["reply_rate"]}%</div><div class="ad-lbl">reply rate</div></div>
                <div class="ad-stat"><div class="ad-val" style="color:{MUTED}">{a["clicks"]:,}</div><div class="ad-lbl">clicks</div></div>
                <div class="ad-stat"><div class="ad-val" style="color:{MUTED}">${a["cpm"]:.3f}</div><div class="ad-lbl">CPM</div></div>
              </div>
            </div>""",unsafe_allow_html=True)

        # ── Section 3: Ad charts ───────────────────────────────────────────
        st.markdown(f"<hr style='border-color:{BORDER};margin:14px 0'>",unsafe_allow_html=True)
        df_ads=pd.DataFrame(ads_sorted)
        if not df_ads.empty:
            fc1,fc2=st.columns(2)
            with fc1:
                fig=px.bar(df_ads.sort_values("msgs_started",ascending=True).tail(10),
                           x="msgs_started",y="campaign",orientation="h",
                           color_discrete_sequence=[MID],title="Messages started per campaign")
                fig.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=320,
                                  plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,
                                  font_color=TEXT,title_font_color=MUTED,title_font_size=12)
                fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
                st.plotly_chart(fig,use_container_width=True)
            with fc2:
                df_cpm=df_ads[df_ads["cost_per_msg"].notna() & (df_ads["cost_per_msg"]>0)].sort_values("cost_per_msg").head(10)
                if not df_cpm.empty:
                    fig=px.bar(df_cpm,x="cost_per_msg",y="campaign",orientation="h",
                               color_discrete_sequence=[AMBER],title="Cost per message (USD) — best performers")
                    fig.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=320,
                                      plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,
                                      font_color=TEXT,title_font_color=MUTED,title_font_size=12)
                    fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
                    st.plotly_chart(fig,use_container_width=True)

        # ── Section 4: Inbox stats ─────────────────────────────────────────
        st.markdown(f"<hr style='border-color:{BORDER};margin:14px 0'>",unsafe_allow_html=True)
        st.markdown(f"<p style='font-size:12px;color:{MUTED};text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px'>💬 Inbox performance — Messenger</p>",unsafe_allow_html=True)

        ic=st.columns(6)
        avg_r=sum_c.get("avg_resp")
        kpi(ic[0],"Conversations",str(sum_c.get("total",0)),"total threads")
        kpi(ic[1],"Msgs received",str(sum_c.get("total_rcvd",0)),"from customers")
        kpi(ic[2],"Msgs sent",str(sum_c.get("total_sent",0)),"by page")
        kpi(ic[3],"Avg response",f"{avg_r} min" if avg_r else "—","first reply",
            RED if avg_r and avg_r>60 else MID)
        kpi(ic[4],"Fast ≤30 min",str(sum_c.get("fast",0)),"quick replies",MID)
        kpi(ic[5],"Slow >60 min",str(sum_c.get("slow",0)),"slow replies",
            RED if sum_c.get("slow",0)>10 else AMBER)

        st.markdown("<div style='height:12px'></div>",unsafe_allow_html=True)

        # Daily chart
        if daily:
            df_day=pd.DataFrame(daily)
            df_day["Date"]=pd.to_datetime(df_day["Date"])
            dc1,dc2=st.columns(2)
            with dc1:
                fig=px.bar(df_day,x="Date",y=["Received","Sent"],barmode="group",
                           color_discrete_sequence=[AMBER,MID],title="Daily message volume")
                fig.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=220,plot_bgcolor=PLOT_BG,
                                  paper_bgcolor=PLOT_BG,font_color=TEXT,title_font_color=MUTED,
                                  title_font_size=12,legend=dict(font=dict(color=TEXT)))
                fig.update_xaxes(gridcolor=BORDER); fig.update_yaxes(gridcolor=BORDER)
                st.plotly_chart(fig,use_container_width=True)
            with dc2:
                resp_times=[c["resp_min"] for c in convos if c["resp_min"] is not None]
                if resp_times:
                    df_rt=pd.DataFrame({"Response time (min)":resp_times})
                    fig2=px.histogram(df_rt,x="Response time (min)",nbins=20,
                                      color_discrete_sequence=[AMBER],title="Response time distribution")
                    fig2.add_vline(x=30,line_dash="dash",line_color=MID,annotation_text="30 min target")
                    fig2.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=220,plot_bgcolor=PLOT_BG,
                                       paper_bgcolor=PLOT_BG,font_color=TEXT,title_font_color=MUTED,title_font_size=12)
                    fig2.update_xaxes(gridcolor=BORDER); fig2.update_yaxes(gridcolor=BORDER)
                    st.plotly_chart(fig2,use_container_width=True)

        # Conversations table
        st.markdown(f"<p style='font-size:12px;color:{MUTED};margin:8px 0 4px'>All conversations</p>",unsafe_allow_html=True)
        df_c=pd.DataFrame([{"Customer":c["customer"],"Platform":c["platform"],
            "Last active":c["updated"],"Msgs in":c["received"],"Msgs out":c["sent"],
            "Total":c["total"],"Response":f"{c['resp_min']} min" if c["resp_min"] is not None else "—"}
            for c in sorted(convos,key=lambda x:x["updated"],reverse=True)])
        st.dataframe(df_c,use_container_width=True,hide_index=True)

# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="margin-top:24px;padding:10px 0;border-top:1px solid {BORDER};
            font-size:11px;color:{MUTED};text-align:center">
  Auria Operations Dashboard · Odoo + Meta Ads + Messenger · refreshes every 30s
</div>""",unsafe_allow_html=True)
st.markdown("<script>setTimeout(()=>window.location.reload(),30000);</script>",unsafe_allow_html=True)
