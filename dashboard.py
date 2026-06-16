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
USER_TOKEN= "EAAcSVW8N23cBRkEcgVDThTOd9lvKezMbzhB3kKLCeT6HUD7m4I5TMB5tg8ZAuXIlW0HcSnBqqFYpqYo1v59MMREn3L2xWTZCkwdE8AdXpQb3loaaMjWoydELwAQZAUZAuECSqPNX5RFJ3SWmYazVTLVIl6u2fmIZAlnLAV77kG90M7zqOiTFeP4K79mZBdC9poZAAZDZD"  # System User Token — permanent, never expires

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
# Stages excluded from overdue: Done, Cancelled, Delivered, Ordered, Received,
# Approved, Published, In Transit, Daily Report, D0NE (typo stage), Searching
DONE_STAGES=[14,15,28,29,41,66,68,69,70,74,75,79,83,116,159,167]

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
    tasks=odoo("project.task","search_read",
        [["active","=",True],["state","not in",["1_done","1_canceled"]]],
        {"fields":["name","project_id","user_ids","priority","date_deadline","stage_id","state"],"limit":300})
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
    # Filter by Odoo's built-in state: 1_done and 1_canceled = closed
    overdue=odoo("project.task","search_read",
        [["date_deadline","<",today],["active","=",True],
         ["state","not in",["1_done","1_canceled"]]],
        {"fields":["name","project_id","user_ids","date_deadline","priority","stage_id","state"],"limit":100})
    projects=odoo("project.project","search_read",[],{"fields":["id","name","task_count"]})
    sales=odoo("sale.order","search_read",
        [["state","in",["sale","done"]],["date_order",">=",thirty_ago]],
        {"fields":["name","amount_total","date_order","user_id"],"limit":500})
    return dict(tasks=tasks,mos=mos,quants=quants,acct=acct,
                overdue=overdue,projects=projects,sales=sales,today=today)

@st.cache_data(ttl=300)
def get_page_token_cached():
    """Get page access token from system user token."""
    pages = meta("me/accounts", {"fields":"id,name,access_token"})
    return next((p["access_token"] for p in pages.get("data",[]) if p["id"]==PAGE_ID), None)

@st.cache_data(ttl=300)
def fetch_meta_all():
    pt=get_page_token()
    if not pt: return {"error":"No page token"}

    # ── FB Posts ───────────────────────────────────────────────────────
    fb_posts=meta(f"{PAGE_ID}/posts",
        {"fields":"id,message,created_time,likes.summary(true),comments.summary(true),shares",
         "limit":"20"},token=pt)
    fb_posts_data=fb_posts.get("data",[])

    # ── FB Stories ─────────────────────────────────────────────────────
    fb_stories=meta(f"{PAGE_ID}/stories",
        {"fields":"id,media_type,creation_time,status"},token=pt)
    fb_stories_active=[s for s in fb_stories.get("data",[]) if s.get("status")=="published"]

    # ── IG Media ───────────────────────────────────────────────────────
    ig_media=meta(f"{IG_ID}/media",
        {"fields":"id,caption,media_type,timestamp,like_count,comments_count,permalink",
         "limit":"30"})
    ig_media_data=ig_media.get("data",[])

    # ── IG Stories ─────────────────────────────────────────────────────
    ig_stories=meta(f"{IG_ID}/stories",
        {"fields":"id,media_type,timestamp","limit":"25"})
    ig_stories_data=ig_stories.get("data",[])

    # ── IG Follower growth ─────────────────────────────────────────────
    from datetime import datetime as _dt, timedelta as _tdm
    _since=str((_dt.now()-_tdm(days=30)).date())
    _until=str(_dt.now().date())
    ig_followers=meta(f"{IG_ID}/insights",
        {"metric":"follower_count","period":"day","since":_since,"until":_until})
    ig_follower_data=ig_followers.get("data",[{}])[0].get("values",[]) if ig_followers.get("data") else []

    # ── IG Account info ────────────────────────────────────────────────
    ig_account=meta(f"{IG_ID}",
        {"fields":"id,name,followers_count,media_count,biography"})

    # ── FB Page info ───────────────────────────────────────────────────
    fb_page=meta(f"{PAGE_ID}",
        {"fields":"id,name,fan_count,followers_count"},token=pt)

    # ── Conversations (paginated) ──────────────────────────────────────
    all_convos=[]
    params={"fields":"id,updated_time,message_count,participants,messages{from,created_time,tags}","limit":"25"}
    batch=meta(f"{PAGE_ID}/conversations",params,token=pt)
    if "error" in batch and not fb_posts_data:
        return {"error":str(batch["error"])}
    all_convos.extend(batch.get("data",[]) if "error" not in batch else [])
    cursor=batch.get("paging",{}).get("cursors",{}).get("after") if "error" not in batch else None
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
                sum_c=summary_convos,sum_a=summary_ads,daily=daily_list,
                fb_posts=fb_posts_data,fb_stories=fb_stories_active,
                fb_page=fb_page,ig_media=ig_media_data,
                ig_stories=ig_stories_data,ig_followers=ig_follower_data,
                ig_account=ig_account)


@st.cache_data(ttl=30)
def fetch_team(cache_key=None):
    """Fetch all team management data per department."""
    from datetime import date, timedelta
    today = str(date.today())
    week_start = str(date.today() - timedelta(days=date.today().weekday()))
    week_ago   = str(date.today() - timedelta(days=7))

    # ── Tasks ────────────────────────────────────────────────────────────
    all_tasks = odoo("project.task","search_read",
        [["active","=",True],["project_id","!=",False]],
        {"fields":["name","stage_id","project_id","user_ids","state",
                   "date_deadline","write_date","priority"],"limit":300})

    done_week = odoo("project.task","search_read",
        [["state","=","1_done"],["write_date",">=",week_start],["project_id","!=",False]],
        {"fields":["name","project_id","user_ids","write_date"],"limit":200})

    # Daily report tasks (stage 116)
    daily_tasks = odoo("project.task","search_read",
        [["active","=",True],["stage_id","=",116]],
        {"fields":["name","user_ids","write_date","project_id"],"limit":50})

    # ── Production ───────────────────────────────────────────────────────
    mos = odoo("mrp.production","search_read",
        [["state","not in",["cancel","draft"]]],
        {"fields":["name","product_id","product_qty","qty_produced","state","date_start"],"limit":100})

    # RM receipts this week (incoming to SJ/RM)
    rm_receipts = odoo("stock.picking","search_read",
        [["picking_type_id","in",[64,1]],["state","=","done"],["date",">=",week_ago]],
        {"fields":["name","state","date","partner_id"],"limit":30})

    # Internal transfers SJ FG → HD FG (picking type 57)
    sj_hd = odoo("stock.picking","search_read",
        [["picking_type_id","=",57],["date",">=",week_ago]],
        {"fields":["name","state","date"],"limit":30})

    # ── Operations ───────────────────────────────────────────────────────
    # Sales validated this week
    sales_week = odoo("sale.order","search_read",
        [["state","in",["sale","done"]],["date_order",">=",week_ago]],
        {"fields":["name","state","date_order","amount_total"],"limit":100})

    # FG received in HD this week
    fg_hd = odoo("stock.picking","search_read",
        [["location_dest_id","in",[45,8]],["state","=","done"],["date",">=",week_ago]],
        {"fields":["name","state","date","location_id"],"limit":30})

    # Returns from Yamamah this week
    returns = odoo("stock.picking","search_read",
        [["picking_type_id","=",60],["date",">=",week_ago]],
        {"fields":["name","state","date"],"limit":30})

    # Deliveries to Yamamah
    deliveries = odoo("stock.picking","search_read",
        [["picking_type_id","in",[41,3]],["state","=","done"],["date",">=",week_ago]],
        {"fields":["name","state","date"],"limit":30})

    # ── Procurement ──────────────────────────────────────────────────────
    rfqs = odoo("purchase.order","search_read",
        [["state","in",["draft","sent"]],["date_order",">=",week_ago]],
        {"fields":["name","partner_id","state","date_order"],"limit":30})

    pos = odoo("purchase.order","search_read",
        [["state","in",["purchase","done"]],["date_order",">=",week_ago]],
        {"fields":["name","partner_id","state","date_order"],"limit":30})

    return dict(
        all_tasks=all_tasks, done_week=done_week, daily_tasks=daily_tasks,
        mos=mos, rm_receipts=rm_receipts, sj_hd=sj_hd,
        sales_week=sales_week, fg_hd=fg_hd, returns=returns, deliveries=deliveries,
        rfqs=rfqs, pos=pos,
        today=today, week_start=week_start
    )

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
    td=fetch_team(cache_key=str(date.today()))

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
tab1,tab2,tab3,tab4,tab5=st.tabs(["📊  Operations","💰  Sales & Team","📣  Marketing & Inbox","👥  Team","📝  Daily Reports"])

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
        # Social + Ad KPIs
        fb_p   = md.get("fb_page",{})
        ig_acc = md.get("ig_account",{})
        ig_med = md.get("ig_media",[])
        fb_sts = md.get("fb_stories",[])
        ig_sts = md.get("ig_stories",[])
        fb_pst = md.get("fb_posts",[])
        ig_flw = md.get("ig_followers",[])

        # Posts this week
        from datetime import datetime as _dtm, timedelta as _tdmk
        _wk_ago = (_dtm.now()-_tdmk(days=7)).strftime("%Y-%m-%d")
        ig_wk = [m for m in ig_med if m.get("timestamp","")[:10]>=_wk_ago]
        fb_wk = [p for p in fb_pst if p.get("created_time","")[:10]>=_wk_ago]

        # Total engagement this week
        ig_likes = sum(m.get("like_count",0) for m in ig_wk)
        ig_cmts  = sum(m.get("comments_count",0) for m in ig_wk)
        fb_likes = sum(p.get("likes",{}).get("summary",{}).get("total_count",0) for p in fb_wk)
        fb_cmts  = sum(p.get("comments",{}).get("summary",{}).get("total_count",0) for p in fb_wk)

        # Follower gain this week
        flw_vals = ig_flw[-7:] if ig_flw else []
        flw_gain = sum(v.get("value",0) for v in flw_vals)

        st.markdown(f"<p style='font-size:12px;color:{MUTED};text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px'>📱 Social Media — Live</p>",unsafe_allow_html=True)
        sc=st.columns(6)
        kpi(sc[0],"FB Followers",   f"{fb_p.get('fan_count',0):,}",     "Auria Page",BLUE)
        kpi(sc[1],"IG Followers",   f"{ig_acc.get('followers_count',0):,}","Auria IG",  "#c97bc9")
        kpi(sc[2],"IG Posts/wk",    str(len(ig_wk)),                       "this week",  MID)
        kpi(sc[3],"FB Posts/wk",    str(len(fb_wk)),                       "this week",  BLUE)
        kpi(sc[4],"Active Stories",  str(len(fb_sts)+len(ig_sts)),         "FB+IG now",  AMBER)
        kpi(sc[5],"IG Followers +",  f"+{flw_gain:,}",                     "gained/7d",  OK_FG if flw_gain>0 else CRIT_FG)

        st.markdown(f"<hr style='border-color:{BORDER};margin:12px 0'>",unsafe_allow_html=True)
        st.markdown(f"<p style='font-size:12px;color:{MUTED};text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px'>📊 Engagement this week</p>",unsafe_allow_html=True)
        ec=st.columns(4)
        kpi(ec[0],"IG Likes",   str(ig_likes), f"{len(ig_wk)} posts",  "#c97bc9")
        kpi(ec[1],"IG Comments",str(ig_cmts),  f"{len(ig_wk)} posts",  "#c97bc9")
        kpi(ec[2],"FB Likes",   str(fb_likes), f"{len(fb_wk)} posts",  BLUE)
        kpi(ec[3],"FB Comments",str(fb_cmts),  f"{len(fb_wk)} posts",  BLUE)

        st.markdown(f"<hr style='border-color:{BORDER};margin:12px 0'>",unsafe_allow_html=True)

        # Latest posts side by side
        lc1,lc2 = st.columns(2)
        with lc1:
            st.markdown(f"<p style='font-size:12px;color:{MUTED};text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px'>📸 Latest IG Posts</p>",unsafe_allow_html=True)
            for m in ig_med[:8]:
                ts  = m.get("timestamp","")[:10]
                cap = (m.get("caption","") or "—")[:60]
                mtype = "🎬" if m.get("media_type")=="VIDEO" else "🖼"
                st.markdown(
                    f'<div style="display:flex;gap:8px;padding:5px 0;border-bottom:0.5px solid {BORDER};align-items:center">' +
                    f'<span style="font-size:16px">{mtype}</span>' +
                    f'<div style="flex:1"><div style="font-size:12px;color:{TEXT}">{cap}</div>' +
                    f'<div style="font-size:10px;color:{MUTED}">{ts} · ❤️{m.get("like_count",0)} 💬{m.get("comments_count",0)}</div></div></div>',
                    unsafe_allow_html=True)
        with lc2:
            st.markdown(f"<p style='font-size:12px;color:{MUTED};text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px'>📘 Latest FB Posts</p>",unsafe_allow_html=True)
            for p in fb_pst[:8]:
                ts  = p.get("created_time","")[:10]
                msg = (p.get("message","") or "—")[:60]
                lk  = p.get("likes",{}).get("summary",{}).get("total_count",0)
                cm  = p.get("comments",{}).get("summary",{}).get("total_count",0)
                sh  = p.get("shares",{}).get("count",0) if p.get("shares") else 0
                st.markdown(
                    f'<div style="display:flex;gap:8px;padding:5px 0;border-bottom:0.5px solid {BORDER};align-items:center">' +
                    f'<span style="font-size:16px">📘</span>' +
                    f'<div style="flex:1"><div style="font-size:12px;color:{TEXT}">{msg}</div>' +
                    f'<div style="font-size:10px;color:{MUTED}">{ts} · ❤️{lk} 💬{cm} 🔁{sh}</div></div></div>',
                    unsafe_allow_html=True)

        # IG Follower growth chart
        if ig_flw:
            st.markdown(f"<hr style='border-color:{BORDER};margin:12px 0'>",unsafe_allow_html=True)
            st.markdown(f"<p style='font-size:12px;color:{MUTED};text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px'>📈 IG Follower growth — last 30 days</p>",unsafe_allow_html=True)
            df_flw=pd.DataFrame(ig_flw)
            df_flw["date"]=pd.to_datetime(df_flw["end_time"]).dt.strftime("%m-%d")
            fig_flw=px.bar(df_flw,x="date",y="value",color_discrete_sequence=["#c97bc9"])
            fig_flw.update_layout(margin=dict(l=0,r=0,t=10,b=0),height=180,
                                  plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,font_color=TEXT,
                                  xaxis_title="",yaxis_title="New followers")
            fig_flw.update_xaxes(gridcolor=BORDER); fig_flw.update_yaxes(gridcolor=BORDER)
            st.plotly_chart(fig_flw,use_container_width=True)

        st.markdown(f"<hr style='border-color:{BORDER};margin:12px 0'>",unsafe_allow_html=True)
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


        # ── CS Team Per-Member Performance ────────────────────────────────────
        st.markdown(f"<hr style='border-color:{BORDER};margin:14px 0'>",unsafe_allow_html=True)
        st.markdown(f"<p style='font-size:12px;color:{MUTED};text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px'>👥 CS Team — Orders & Messages this week</p>",unsafe_allow_html=True)

        from datetime import timedelta as _tdcs
        _mon_cs = str(date.today() - _tdcs(days=date.today().weekday()))
        _cs_orders = odoo("sale.order","search_read",
            [["state","in",["sale","done"]],["date_order",">=",_mon_cs]],
            {"fields":["name","user_id","date_order","amount_total"],"limit":500})

        _cs_by_sp = {}
        for _o in _cs_orders:
            _uid  = _o["user_id"][0] if _o["user_id"] else 0
            _name = _o["user_id"][1] if _o["user_id"] else "Unknown"
            _cs_by_sp.setdefault(_uid,{"name":_name,"orders":0,"total":0.0})
            _cs_by_sp[_uid]["orders"] += 1
            _cs_by_sp[_uid]["total"]  += _o["amount_total"]

        if _cs_by_sp:
            _sorted_cs  = sorted(_cs_by_sp.items(),key=lambda x:-x[1]["orders"])
            _max_orders = max(v["orders"] for _,v in _sorted_cs) or 1
            _tot_orders = sum(v["orders"] for _,v in _sorted_cs)
            _tot_rev    = sum(v["total"]  for _,v in _sorted_cs)
            _inbox_rcvd = sum_c.get("total_rcvd",0)
            _inbox_sent = sum_c.get("total_sent",0)

            # KPIs
            _ck = st.columns(4)
            kpi(_ck[0],"FB Messages In",  str(_inbox_rcvd), "received from customers", AMBER)
            kpi(_ck[1],"FB Messages Out", str(_inbox_sent), "sent by page", MID)
            kpi(_ck[2],"Orders this week", str(_tot_orders), "all CS team", OK_FG)
            kpi(_ck[3],"Revenue this week",f"{_tot_rev:,.0f}","LYD", AMBER)

            st.markdown("<div style='height:12px'></div>",unsafe_allow_html=True)

            # Per-member cards
            _medals  = ["🥇","🥈","🥉"]
            _cs_cols = st.columns(min(len(_sorted_cs),4))
            _clrs    = [AMBER,MID,"#5A9E34","#5b9bd5","#c97bc9"]
            for _i,(_uid,_sp) in enumerate(_sorted_cs):
                _col = _cs_cols[_i % 4]
                _c   = _clrs[_i % len(_clrs)]
                _pct = round(_sp["orders"]/_max_orders*100)
                _avg = round(_sp["total"]/_sp["orders"]) if _sp["orders"] else 0
                _share = round(_sp["orders"]/_tot_orders*100) if _tot_orders else 0
                _mn  = _medals[_i] if _i<3 else f"#{_i+1}"
                # Estimate msgs handled (proportional to orders)
                _msgs_est = round(_inbox_rcvd * _sp["orders"] / _tot_orders) if _tot_orders else 0
                _col.markdown(
                    f'<div style="background:{CARD};border:0.5px solid {BORDER};border-top:3px solid {_c};' +
                    f'border-radius:10px;padding:12px 14px;margin-bottom:8px">' +
                    f'<div style="font-size:13px;font-weight:600;color:{TEXT};margin-bottom:10px">{_mn} {_sp["name"].split()[0]}</div>' +
                    f'<div style="display:flex;justify-content:space-between;margin-bottom:4px">' +
                    f'<span style="font-size:11px;color:{MUTED}">📦 Orders</span>' +
                    f'<span style="font-size:14px;font-weight:700;color:{_c}">{_sp["orders"]}</span></div>' +
                    f'<div style="background:{BG2};border-radius:3px;height:4px;margin-bottom:8px">' +
                    f'<div style="width:{_pct}%;height:4px;background:{_c};border-radius:3px"></div></div>' +
                    f'<div style="display:flex;justify-content:space-between;margin-bottom:3px">' +
                    f'<span style="font-size:10px;color:{MUTED}">💬 Msgs est.</span>' +
                    f'<span style="font-size:11px;color:{TEXT}">{_msgs_est}</span></div>' +
                    f'<div style="display:flex;justify-content:space-between;margin-bottom:3px">' +
                    f'<span style="font-size:10px;color:{MUTED}">💰 Avg/order</span>' +
                    f'<span style="font-size:11px;color:{MUTED}">{_avg:,} LYD</span></div>' +
                    f'<div style="display:flex;justify-content:space-between">' +
                    f'<span style="font-size:10px;color:{MUTED}">📊 Share</span>' +
                    f'<span style="font-size:11px;color:{MUTED}">{_share}%</span></div>' +
                    f'</div>',
                    unsafe_allow_html=True)

            # Stacked bar — daily orders by agent
            _df_cs = pd.DataFrame([{
                "Date": pd.to_datetime(_o["date_order"]).date(),
                "Agent": _o["user_id"][1].split()[0] if _o["user_id"] else "—",
                "Orders": 1}
                for _o in _cs_orders])
            _df_csg = _df_cs.groupby(["Date","Agent"])["Orders"].sum().reset_index()
            _fig_cs = px.bar(_df_csg,x="Date",y="Orders",color="Agent",barmode="stack",
                color_discrete_sequence=[AMBER,MID,"#5A9E34","#5b9bd5"],
                title="Daily orders by CS agent")
            _fig_cs.update_layout(margin=dict(l=0,r=0,t=36,b=0),height=200,
                plot_bgcolor=PLOT_BG,paper_bgcolor=PLOT_BG,font_color=TEXT,
                title_font_color=MUTED,title_font_size=12,
                legend=dict(font=dict(color=TEXT,size=10)))
            _fig_cs.update_xaxes(gridcolor=BORDER); _fig_cs.update_yaxes(gridcolor=BORDER)
            st.plotly_chart(_fig_cs,use_container_width=True)

        st.markdown(f'<div style="font-size:10px;color:{MUTED};font-style:italic;margin-bottom:10px">⚡ FB messages shown are page totals. Per-agent breakdown estimated from Odoo order share. Exact per-agent FB counts require Meta Business Suite agent assignment.</div>',unsafe_allow_html=True)

        # ── Conversation table ─────────────────────────────────────────────────
        st.markdown(f"<p style='font-size:12px;color:{MUTED};margin:8px 0 4px'>All conversations (latest 100)</p>",unsafe_allow_html=True)
        df_c=pd.DataFrame([{"Customer":c["customer"],"Platform":c["platform"],
            "Last active":c["updated"],"Msgs in":c["received"],"Msgs out":c["sent"],
            "Total":c["total"],"Response":f"{c['resp_min']} min" if c["resp_min"] is not None else "—"}
            for c in sorted(convos,key=lambda x:x["updated"],reverse=True)])
        st.dataframe(df_c,use_container_width=True,hide_index=True)


# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — TEAM MANAGEMENT
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    from datetime import date as _date, timedelta as _td

    USER_NAMES_T = {
        8:"Hussam",18:"Abdullah",29:"Ala Deep",9:"Alaa Oshah",
        15:"Marwan",13:"Nasser",27:"Khan",11:"Wesal",23:"Bader",
        6:"Moad",31:"Weam",30:"Wegdan",24:"Amal",12:"Wala",10:"Znjabel"
    }

    all_t   = td["all_tasks"]
    done_w  = td["done_week"]
    mos_t   = td["mos"]
    rm_r    = td["rm_receipts"]
    sjhd    = td["sj_hd"]
    sw      = td["sales_week"]
    fg_hd_t = td["fg_hd"]
    ret_t   = td["returns"]
    del_t   = td["deliveries"]
    rfqs_t  = td["rfqs"]
    pos_t   = td["pos"]
    week_s  = td["week_start"]
    today_s = td["today"]

    OPEN_STATES = ["01_in_progress","02_changes_requested","03_approved","04_waiting_normal"]

    def dept_tasks(proj_id):
        open_t = [t for t in all_t if t["project_id"] and t["project_id"][0]==proj_id
                  and t["state"] in OPEN_STATES]
        done_t = [t for t in done_w if t["project_id"] and t["project_id"][0]==proj_id]
        return open_t, done_t

    def state_pill(state):
        m2 = {"01_in_progress":(AMBER,"In Progress"),
               "02_changes_requested":("#e69500","Changes Req."),
               "03_approved":(MID,"Approved"),
               "04_waiting_normal":(MUTED,"Waiting")}
        c,lbl = m2.get(state,(MUTED,"—"))
        return '<span style="background:'+c+'22;color:'+c+';padding:1px 7px;border-radius:20px;font-size:10px;font-weight:600">'+lbl+'</span>'

    def dl_pill(dl):
        if not dl: return ""
        d = dl[:10]
        color = CRIT_FG if d < today_s else WARN_FG if d == today_s else MUTED
        return '<span style="color:'+color+';font-size:10px">'+d+'</span>'

    def task_table_html(tasks, max_rows=10):
        if not tasks:
            return '<div class="al al-o" style="margin:0;font-size:12px">No open tasks</div>'
        rows = ""
        for t in tasks[:max_rows]:
            users = ", ".join(USER_NAMES_T.get(u,str(u)) for u in t.get("user_ids",[])) or "—"
            name = t["name"][:48]
            rows += "<tr><td style='padding:5px 8px;font-size:12px;color:"+TEXT+"'>"+name+"</td>"
            rows += "<td style='padding:5px 4px'>"+state_pill(t.get("state",""))+"</td>"
            rows += "<td style='padding:5px 4px;font-size:11px;color:"+MUTED+"'>"+users+"</td>"
            rows += "<td style='padding:5px 4px'>"+dl_pill(t.get("date_deadline",""))+"</td></tr>"
        if len(tasks)>max_rows:
            rows += "<tr><td colspan='4' style='font-size:10px;color:"+MUTED+";padding:4px 8px'>+"+str(len(tasks)-max_rows)+" more</td></tr>"
        hdr = ("<thead><tr>"
               "<th style='text-align:left;font-size:10px;color:"+MUTED+";padding:4px 8px;border-bottom:1px solid "+BORDER+"'>Task</th>"
               "<th style='font-size:10px;color:"+MUTED+";padding:4px;border-bottom:1px solid "+BORDER+"'>Status</th>"
               "<th style='font-size:10px;color:"+MUTED+";padding:4px;border-bottom:1px solid "+BORDER+"'>Owner</th>"
               "<th style='font-size:10px;color:"+MUTED+";padding:4px;border-bottom:1px solid "+BORDER+"'>Due</th>"
               "</tr></thead>")
        return "<table style='width:100%;border-collapse:collapse'>"+hdr+"<tbody>"+rows+"</tbody></table>"

    def done_table_html(tasks, max_rows=8):
        if not tasks: return '<div style="font-size:12px;color:'+MUTED+'">No completed tasks this week</div>'
        rows=""
        for t in tasks[:max_rows]:
            users = ", ".join(USER_NAMES_T.get(u,str(u)) for u in t.get("user_ids",[])) or "—"
            rows += "<tr><td style='padding:4px 8px;font-size:12px;color:"+TEXT+"'>✅ "+t["name"][:45]+"</td>"
            rows += "<td style='padding:4px;font-size:11px;color:"+MUTED+"'>"+users+"</td>"
            rows += "<td style='padding:4px;font-size:10px;color:"+MUTED+"'>"+t["write_date"][:10]+"</td></tr>"
        return "<table style='width:100%;border-collapse:collapse'><tbody>"+rows+"</tbody></table>"

    def picking_table_html(picks, max_rows=6):
        if not picks: return '<div style="font-size:12px;color:'+MUTED+'">None this week</div>'
        rows=""
        for p in picks[:max_rows]:
            color = OK_FG if p["state"]=="done" else WARN_FG if p["state"] in ["assigned","confirmed"] else MUTED
            rows += "<tr><td style='padding:4px 8px;font-size:12px;color:"+TEXT+"'>"+p["name"]+"</td>"
            rows += "<td style='padding:4px;font-size:11px;color:"+color+";font-weight:500'>"+p["state"]+"</td>"
            rows += "<td style='padding:4px;font-size:10px;color:"+MUTED+"'>"+p["date"][:10]+"</td></tr>"
        return "<table style='width:100%;border-collapse:collapse'><tbody>"+rows+"</tbody></table>"

    def dept_header_html(icon, name, open_count, done_count):
        return ("<div style='display:flex;align-items:center;gap:10px;margin-bottom:12px;"
                "padding-bottom:10px;border-bottom:2px solid "+BORDER+"'>"
                "<div style='font-size:22px'>"+icon+"</div><div>"
                "<div style='font-size:16px;font-weight:600;color:"+TEXT+"'>"+name+"</div>"
                "<div style='font-size:11px;color:"+MUTED+"'>"
                "<span style='color:"+AMBER+";font-weight:500'>"+str(open_count)+" open</span>"
                " &nbsp;·&nbsp; "
                "<span style='color:"+OK_FG+";font-weight:500'>"+str(done_count)+" done this week</span>"
                "</div></div></div>")

    def stat_row_html(items):
        cards = ""
        for lbl,val,col in items:
            cards += ("<div style='background:"+BG2+";border-radius:8px;padding:8px 12px;"
                      "text-align:center;flex:1'>"
                      "<div style='font-size:18px;font-weight:600;color:"+col+"'>"+str(val)+"</div>"
                      "<div style='font-size:10px;color:"+MUTED+";margin-top:2px'>"+lbl+"</div>"
                      "</div>")
        return "<div style='display:flex;gap:8px;margin-bottom:10px'>"+cards+"</div>"

    def slabel(label):
        return "<div style='font-size:10px;font-weight:600;text-transform:uppercase;letter-spacing:.06em;color:"+MUTED+";margin:10px 0 5px'>"+label+"</div>"

    def card_wrap(html):
        return "<div style='background:"+CARD+";border:0.5px solid "+BORDER+";border-radius:12px;padding:16px;height:100%'>"+html+"</div>"

    st.markdown(
        "<div style='display:flex;align-items:center;justify-content:space-between;margin-bottom:16px'>"
        "<div style='font-size:18px;font-weight:600;color:"+TEXT+"'>👥 Team Management — Weekly Overview</div>"
        "<div style='font-size:11px;color:"+MUTED+"'>Week from "+week_s+"</div></div>",
        unsafe_allow_html=True)

    # ── ROW 1: Production + Operations ──────────────────────────────────────
    r1c1, r1c2 = st.columns(2)

    with r1c1:
        open_t, done_t = dept_tasks(3)
        mo_prog  = [x for x in mos_t if x["state"]=="progress"]
        mo_done  = [x for x in mos_t if x["state"]=="done"]
        html = dept_header_html("🏭","Production",len(open_t),len(done_t))
        html += stat_row_html([("MOs Active",len(mo_prog),AMBER),("MOs Done",len(mo_done),OK_FG),("RM Receipts",len(rm_r),MID),("SJ→HD",len(sjhd),BLUE)])
        # Active MOs
        html += slabel("Active Manufacturing Orders")
        if mo_prog:
            mo_rows=""
            for mo in mo_prog[:6]:
                pct = round(mo["qty_produced"]/mo["product_qty"]*100) if mo["product_qty"] else 0
                bc = OK_FG if pct==100 else AMBER
                mo_rows += ("<tr><td style='padding:5px 8px;font-size:12px;color:"+TEXT+"'>"+mo["name"]+"</td>"
                    "<td style='padding:5px 8px;font-size:11px;color:"+MUTED+"'>"+mo["product_id"][1][:25]+"</td>"
                    "<td style='padding:5px 8px'><div style='display:flex;align-items:center;gap:6px'>"
                    "<div style='width:55px;height:5px;background:"+BG2+";border-radius:3px;overflow:hidden'>"
                    "<div style='width:"+str(pct)+"%;height:100%;background:"+bc+"'></div></div>"
                    "<span style='font-size:10px;color:"+MUTED+"'>"+str(pct)+"%</span></div></td></tr>")
            html += "<table style='width:100%;border-collapse:collapse'><tbody>"+mo_rows+"</tbody></table>"
        else:
            html += "<div style='font-size:12px;color:"+MUTED+"'>No active MOs</div>"
        html += slabel("SJ → HD Transfers ("+str(len(sjhd))+")")
        html += picking_table_html(sjhd,5)
        html += slabel("Open Tasks ("+str(len(open_t))+")")
        html += task_table_html(open_t)
        html += slabel("Done this week ("+str(len(done_t))+")")
        html += done_table_html(done_t)
        st.markdown(card_wrap(html), unsafe_allow_html=True)

    with r1c2:
        open_t, done_t = dept_tasks(7)
        del_done = len([d for d in del_t if d["state"]=="done"])
        fg_done  = len([f for f in fg_hd_t if f["state"]=="done"])
        ret_pend = len([r for r in ret_t if r["state"] in ["assigned","confirmed"]])
        html = dept_header_html("📦","Operations & Facilities",len(open_t),len(done_t))
        html += stat_row_html([("Sales (wk)",len(sw),AMBER),("Deliveries",del_done,MID),("FG Rcvd HD",fg_done,OK_FG),("Returns Pend",ret_pend,RED)])
        html += slabel("FG Received at HD ("+str(len(fg_hd_t))+")")
        html += picking_table_html(fg_hd_t)
        html += slabel("Returns from Yamamah ("+str(len(ret_t))+")")
        html += picking_table_html(ret_t,5)
        html += slabel("Open Tasks ("+str(len(open_t))+")")
        html += task_table_html(open_t)
        html += slabel("Done this week ("+str(len(done_t))+")")
        html += done_table_html(done_t)
        st.markdown(card_wrap(html), unsafe_allow_html=True)

    st.markdown("<div style='height:16px'></div>", unsafe_allow_html=True)

    # ── ROW 2: Procurement + Creative ───────────────────────────────────────
    r2c1, r2c2 = st.columns(2)

    with r2c1:
        open_t, done_t = dept_tasks(4)
        html = dept_header_html("🛒","Procurement & Supply Chain",len(open_t),len(done_t))
        html += stat_row_html([("RFQs (wk)",len(rfqs_t),MUTED),("POs Confirmed",len(pos_t),AMBER),("RM Receipts",len(rm_r),OK_FG)])
        if rfqs_t:
            html += slabel("Open RFQs ("+str(len(rfqs_t))+")")
            rows=""
            for p in rfqs_t[:6]:
                rows+=("<tr><td style='padding:4px 8px;font-size:12px;color:"+TEXT+"'>"+p["name"]+"</td>"
                       "<td style='padding:4px;font-size:11px;color:"+MUTED+"'>"+(p["partner_id"][1][:22] if p["partner_id"] else "—")+"</td>"
                       "<td style='padding:4px;font-size:10px;color:"+WARN_FG+";font-weight:500'>DRAFT</td></tr>")
            html += "<table style='width:100%;border-collapse:collapse'><tbody>"+rows+"</tbody></table>"
        if pos_t:
            html += slabel("Confirmed POs ("+str(len(pos_t))+")")
            rows=""
            for p in pos_t[:6]:
                rows+=("<tr><td style='padding:4px 8px;font-size:12px;color:"+TEXT+"'>"+p["name"]+"</td>"
                       "<td style='padding:4px;font-size:11px;color:"+MUTED+"'>"+(p["partner_id"][1][:22] if p["partner_id"] else "—")+"</td>"
                       "<td style='padding:4px;font-size:11px;color:"+OK_FG+";font-weight:500'>CONFIRMED</td></tr>")
            html += "<table style='width:100%;border-collapse:collapse'><tbody>"+rows+"</tbody></table>"
        html += slabel("Open Tasks ("+str(len(open_t))+")")
        html += task_table_html(open_t)
        html += slabel("Done this week ("+str(len(done_t))+")")
        html += done_table_html(done_t)
        st.markdown(card_wrap(html), unsafe_allow_html=True)

    with r2c2:
        open_t, done_t = dept_tasks(5)
        videos = [t for t in done_w if t["project_id"] and t["project_id"][0]==5
                  and any(kw in t["name"].lower() for kw in ["video","فيديو","reel","story","stories"])]
        html = dept_header_html("🎬","Creative & Content",len(open_t),len(done_t))
        html += stat_row_html([("Open Tasks",len(open_t),AMBER),("Done (wk)",len(done_t),OK_FG),("Videos/Reels",len(videos),MID)])
        html += ('<div class="al al-i" style="margin-bottom:8px;font-size:11px">'
                 'ℹ️ Live social media counts (Stories, Posts) need Buffer/Meta API — connect via n8n</div>')
        html += slabel("Open Tasks ("+str(len(open_t))+")")
        html += task_table_html(open_t)
        html += slabel("Done this week ("+str(len(done_t))+")")
        html += done_table_html(done_t)
        st.markdown(card_wrap(html), unsafe_allow_html=True)

    st.markdown("<div style='height:20px'></div>", unsafe_allow_html=True)

    # ── DAILY REPORT STATUS ─────────────────────────────────────────────────
    st.markdown(
        "<div style='font-weight:600;font-size:15px;margin-bottom:10px;color:"+TEXT+"'>📋 Daily Report Status</div>",
        unsafe_allow_html=True)

    daily_done_today = odoo("project.task","search_read",
        [["name","ilike","تقرير"],["write_date",">=",today_s],["active","=",True]],
        {"fields":["name","user_ids","write_date","state"],"limit":50})

    DEPT_DR = {
        "🏭 Production":    [18],
        "📦 Operations":   [15,13],
        "🛒 Procurement":  [29,27,9],
        "🎬 Creative":     [11,31],
        "💰 Finance":      [23],
        "🛎 Cust. Service":[9,12,24,10],
    }

    dr_cols = st.columns(len(DEPT_DR))
    for col,(dept_name,uids) in zip(dr_cols,DEPT_DR.items()):
        sub_today = any(any(u in t["user_ids"] for u in uids)
                        for t in daily_done_today if t["write_date"][:10]==today_s)
        wk_count  = sum(1 for t in daily_done_today
                        if any(u in t["user_ids"] for u in uids)
                        and t["write_date"][:10]>=week_s)
        bg = OK_BG if sub_today else CRIT_BG
        fg = OK_FG if sub_today else CRIT_FG
        icon = "✅" if sub_today else "⚠️"
        col.markdown(
            "<div style='background:"+bg+";border:0.5px solid "+fg+"44;border-radius:10px;"
            "padding:12px;text-align:center'>"
            "<div style='font-size:20px'>"+icon+"</div>"
            "<div style='font-size:12px;font-weight:600;color:"+fg+";margin-top:4px'>"+dept_name+"</div>"
            "<div style='font-size:10px;color:"+MUTED+";margin-top:4px'>"+str(wk_count)+"× this week</div>"
            "</div>", unsafe_allow_html=True)



# ══════════════════════════════════════════════════════════════════════════════
# TAB 4 — TEAM & DEPARTMENTS
# ══════════════════════════════════════════════════════════════════════════════
with tab4:
    from datetime import timedelta as _td
    today_dt = date.today()
    mon_dt   = today_dt - _td(days=today_dt.weekday())
    today_s  = str(today_dt)
    mon_s    = str(mon_dt)

    U = {8:"Hussam",18:"Abdullah",29:"Ala' Deep",9:"Alaa Oshah",
         15:"Marwan",13:"Nasser",27:"Khan",11:"Wesal",23:"Bader",
         6:"Moad",31:"Weam",30:"Wegdan",24:"Amal",12:"Wala",10:"Znjabel"}

    STATE_IC = {"01_in_progress":"🔵","02_changes_requested":"🟡",
                "03_approved":"🟢","1_done":"✅","1_canceled":"❌","04_waiting_normal":"⏳"}
    STATE_LB = {"01_in_progress":"In Progress","02_changes_requested":"Changes Req.",
                "03_approved":"Approved","1_done":"Done","1_canceled":"Cancelled",
                "04_waiting_normal":"Waiting"}

    @st.cache_data(ttl=60)
    def fetch_team(ck=None):
        _mon = str(date.today() - _td(days=date.today().weekday()))
        at = odoo("project.task","search_read",
            [["active","=",True],["project_id","!=",False]],
            {"fields":["name","project_id","user_ids","state","date_deadline",
                       "stage_id","write_date","priority"],"limit":500})
        ma = odoo("mrp.production","search_read",
            [["state","not in",["cancel","draft"]]],
            {"fields":["name","product_id","product_qty","qty_produced","state",
                       "date_start","date_finished"],"limit":200})
        tr = odoo("stock.picking","search_read",
            [["state","=","done"],["picking_type_code","=","internal"],["date_done",">=",_mon]],
            {"fields":["name","date_done","location_id","location_dest_id"],"limit":100})
        rm = odoo("stock.picking","search_read",
            [["state","=","done"],["picking_type_code","=","incoming"],["date_done",">=",_mon]],
            {"fields":["name","partner_id","date_done"],"limit":100})
        dv = odoo("stock.picking","search_read",
            [["state","=","done"],["picking_type_code","=","outgoing"],["date_done",">=",_mon]],
            {"fields":["name","partner_id","date_done"],"limit":200})
        fg = odoo("stock.move","search_read",
            [["state","=","done"],["location_dest_id","=",45],["date",">=",_mon]],
            {"fields":["product_id","quantity","date"],"limit":100})
        rt = odoo("stock.picking","search_read",
            [["state","=","done"],["location_id","=",44],["date_done",">=",_mon]],
            {"fields":["name","date_done"],"limit":50})
        rq = odoo("purchase.order","search_read",
            [["state","in",["draft","sent"]]],
            {"fields":["name","partner_id","state","date_order"],"limit":100})
        po = odoo("purchase.order","search_read",
            [["state","in",["purchase","done"]],["date_approve",">=",_mon]],
            {"fields":["name","partner_id","state","date_approve"],"limit":50})
        return dict(at=at,ma=ma,tr=tr,rm=rm,dv=dv,fg=fg,rt=rt,rq=rq,po=po)

    with st.spinner("Loading team data…"):
        td4 = fetch_team(ck=str(date.today()))

    _at = td4["at"]

    def _dept(pid):   return [t for t in _at if t["project_id"][0]==pid]
    def _real(ts):    return [t for t in ts if "التقرير اليومي" not in t["name"] and "تقرير يومي" not in t["name"]]
    def _open(ts):    return [t for t in _real(ts) if t["state"] not in ("1_done","1_canceled")]
    def _done_wk(ts): return [t for t in _real(ts) if t["state"]=="1_done" and t.get("write_date","")[:10]>=mon_s]
    def _over(ts):    return [t for t in _open(ts) if t.get("date_deadline") and t["date_deadline"][:10]<today_s]
    def _daily(ts):   return [t for t in ts if "التقرير اليومي" in t["name"] or "تقرير يومي" in t["name"]]

    def _sbadge(state):
        bg = {"1_done":OK_BG,"01_in_progress":INFO_BG,"03_approved":OK_BG,
              "02_changes_requested":WARN_BG,"1_canceled":CRIT_BG,"04_waiting_normal":BG2}.get(state,BG2)
        fg_c = {"1_done":OK_FG,"01_in_progress":INFO_FG,"03_approved":OK_FG,
                "02_changes_requested":WARN_FG,"1_canceled":CRIT_FG,"04_waiting_normal":MUTED}.get(state,MUTED)
        return f'<span style="background:{bg};color:{fg_c};padding:2px 7px;border-radius:10px;font-size:10px;white-space:nowrap">{STATE_IC.get(state,"⚪")} {STATE_LB.get(state,state)}</span>'

    def _dbadge(state):
        if state=="1_done":      return f'<span style="background:{OK_BG};color:{OK_FG};padding:2px 7px;border-radius:10px;font-size:10px">✅ Submitted</span>'
        if state=="03_approved": return f'<span style="background:{OK_BG};color:{OK_FG};padding:2px 7px;border-radius:10px;font-size:10px">🟢 Approved</span>'
        if state=="01_in_progress": return f'<span style="background:{WARN_BG};color:{WARN_FG};padding:2px 7px;border-radius:10px;font-size:10px">🟡 Pending</span>'
        return f'<span style="background:{CRIT_BG};color:{CRIT_FG};padding:2px 7px;border-radius:10px;font-size:10px">🔴 Missing</span>'

    def dept_card(title, icon, pid, color, metrics_html):
        ts     = _dept(pid)
        open_  = _open(ts)
        done_  = _done_wk(ts)
        over_  = _over(ts)
        daily_ = _daily(ts)

        # open tasks rows
        open_rows = ""
        for t in sorted(open_, key=lambda x:(x.get("date_deadline") or "9999"))[:8]:
            users = [U.get(u,str(u)) for u in (t["user_ids"] or [])][:2]
            dl    = (t.get("date_deadline") or "")[:10]
            is_od = dl and dl<today_s
            dl_span = f'<span style="font-size:10px;color:{"#f4a0a0" if is_od else MUTED};margin-right:4px">{dl}</span>' if dl else ""
            dots = "".join(
                f'<span style="background:{color};color:#fff;border-radius:50%;'
                f'width:18px;height:18px;font-size:9px;display:inline-flex;'
                f'align-items:center;justify-content:center;margin-left:2px">{u[0]}</span>'
                for u in users)
            open_rows += (
                f'<div style="display:flex;align-items:center;gap:6px;padding:4px 0;'
                f'border-bottom:0.5px solid {BORDER}">'
                f'<div style="flex:1;font-size:12px;color:{TEXT};line-height:1.3">{t["name"][:44]}</div>'
                f'<div style="display:flex;align-items:center;gap:3px;flex-shrink:0">'
                f'{dl_span}{dots}{_sbadge(t["state"])}</div></div>')

        # done rows
        done_rows = ""
        for t in done_[:5]:
            user = U.get((t["user_ids"] or [None])[0],"—") if t["user_ids"] else "—"
            done_rows += (
                f'<div style="display:flex;gap:6px;padding:3px 0;border-bottom:0.5px solid {BORDER};align-items:center">'
                f'<span style="color:{OK_FG};font-size:11px">✅</span>'
                f'<span style="font-size:11px;color:{MUTED};flex:1">{t["name"][:40]}</span>'
                f'<span style="font-size:10px;color:{MUTED}">{user}</span></div>')

        # daily report rows
        daily_rows = ""
        for dr in daily_:
            users = [U.get(u,str(u)) for u in (dr["user_ids"] or [])]
            daily_rows += (
                f'<div style="display:flex;justify-content:space-between;align-items:center;'
                f'padding:4px 0;border-bottom:0.5px solid {BORDER}">'
                f'<span style="font-size:12px;color:{TEXT}">{", ".join(users) or "—"}</span>'
                f'{_dbadge(dr["state"])}</div>')

        no_open  = f'<div style="font-size:11px;color:{OK_FG};padding:6px 0">🎉 All clear</div>'
        no_done  = f'<div style="font-size:11px;color:{MUTED}">None yet this week</div>'
        no_daily = f'<div style="font-size:11px;color:{MUTED}">Not tracked</div>'

        st.markdown(
            f'<div style="background:{CARD};border:0.5px solid {BORDER};border-top:3px solid {color};'
            f'border-radius:12px;padding:16px;margin-bottom:14px">'

            # header
            f'<div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:12px">'
            f'<div style="font-size:16px;font-weight:600;color:{TEXT}">{icon} {title}</div>'
            f'<div style="display:flex;gap:8px">'
            f'<div style="text-align:center;background:{BG2};border-radius:8px;padding:4px 10px">'
            f'<div style="font-size:18px;font-weight:600;color:{color}">{len(open_)}</div>'
            f'<div style="font-size:10px;color:{MUTED}">Open</div></div>'
            f'<div style="text-align:center;background:{BG2};border-radius:8px;padding:4px 10px">'
            f'<div style="font-size:18px;font-weight:600;color:{OK_FG}">{len(done_)}</div>'
            f'<div style="font-size:10px;color:{MUTED}">Done/wk</div></div>'
            f'<div style="text-align:center;background:{BG2};border-radius:8px;padding:4px 10px">'
            f'<div style="font-size:18px;font-weight:600;color:{"#f4a0a0" if over_ else OK_FG}">{len(over_)}</div>'
            f'<div style="font-size:10px;color:{MUTED}">Overdue</div></div>'
            f'</div></div>'

            # metrics
            f'{metrics_html}'

            # two columns
            f'<div style="display:grid;grid-template-columns:1fr 1fr;gap:14px;margin-top:12px">'

            # left: open tasks
            f'<div><div style="font-size:10px;font-weight:500;color:{MUTED};text-transform:uppercase;'
            f'letter-spacing:.07em;margin-bottom:6px">Open Tasks</div>'
            f'{open_rows or no_open}</div>'

            # right: daily + done
            f'<div><div style="font-size:10px;font-weight:500;color:{MUTED};text-transform:uppercase;'
            f'letter-spacing:.07em;margin-bottom:6px">Today\'s Report</div>'
            f'{daily_rows or no_daily}'
            f'<div style="font-size:10px;font-weight:500;color:{MUTED};text-transform:uppercase;'
            f'letter-spacing:.07em;margin:10px 0 6px">Completed This Week</div>'
            f'{done_rows or no_done}</div>'

            f'</div></div>',
            unsafe_allow_html=True)

    # ── PRODUCTION ──────────────────────────────────────────────────
    _ma  = td4["ma"]
    _mo_active = [m for m in _ma if m["state"] in ("confirmed","progress")]
    _mo_done   = [m for m in _ma if m["state"]=="done" and (m.get("date_finished") or "")[:10]>=mon_s]
    _rm_n = len(td4["rm"])
    _tr_hd= [t for t in td4["tr"] if "HD" in (t["location_dest_id"][1] if t["location_dest_id"] else "") or "Alyamama" in (t["location_dest_id"][1] if t["location_dest_id"] else "")]

    mo_metrics = (
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:6px">'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{AMBER}">{len(_mo_active)}</div>'
        f'<div style="font-size:10px;color:{MUTED}">Active MOs</div></div>'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{OK_FG}">{len(_mo_done)}</div>'
        f'<div style="font-size:10px;color:{MUTED}">MOs Done/wk</div></div>'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{MID}">{_rm_n}</div>'
        f'<div style="font-size:10px;color:{MUTED}">RM Received/wk</div></div>'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{INFO_FG}">{len(_tr_hd)}</div>'
        f'<div style="font-size:10px;color:{MUTED}">Transfers SJ→HD</div></div></div>'
        + (f'<div style="font-size:10px;color:{MUTED};margin-top:2px">' +
           "  ·  ".join(f"{m['name']} {m['product_id'][1][:18]} ({m['qty_produced']:.0f}/{m['product_qty']:.0f})" for m in _mo_active[:4]) +
           '</div>' if _mo_active else ""))

    dept_card("Production Operations","🏭",3,AMBER,mo_metrics)

    # ── OPERATIONS ──────────────────────────────────────────────────
    ops_metrics = (
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:6px">'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{MID}">{len(td4["dv"])}</div>'
        f'<div style="font-size:10px;color:{MUTED}">Sales Shipped/wk</div></div>'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{OK_FG}">{len(td4["fg"])}</div>'
        f'<div style="font-size:10px;color:{MUTED}">FG Moves→HD/wk</div></div>'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{WARN_FG}">{len(td4["rt"])}</div>'
        f'<div style="font-size:10px;color:{MUTED}">Returns/Yamamah</div></div>'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{INFO_FG}">{len(td4["tr"])}</div>'
        f'<div style="font-size:10px;color:{MUTED}">Internal Transfers</div></div></div>')

    dept_card("Operations & Facilities","⚙️",7,MID,ops_metrics)

    # ── PROCUREMENT ─────────────────────────────────────────────────
    _rq = td4["rq"]; _po = td4["po"]
    _draft = sum(1 for r in _rq if r["state"]=="draft")
    proc_metrics = (
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:6px">'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{WARN_FG}">{len(_rq)}</div>'
        f'<div style="font-size:10px;color:{MUTED}">Open RFQs</div></div>'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{AMBER}">{_draft}</div>'
        f'<div style="font-size:10px;color:{MUTED}">Draft RFQs</div></div>'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{OK_FG}">{len(_po)}</div>'
        f'<div style="font-size:10px;color:{MUTED}">POs Confirmed/wk</div></div>'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{MID}">{_rm_n}</div>'
        f'<div style="font-size:10px;color:{MUTED}">RM Received/wk</div></div></div>'
        + (f'<div style="font-size:10px;color:{MUTED};margin-top:2px">' +
           "  ·  ".join(f"{r['name']} {(r['partner_id'][1] if r['partner_id'] else '—')[:18]}" for r in _rq[:6]) +
           '</div>' if _rq else ""))

    dept_card("Procurement & Supply Chain","📦",4,INFO_FG,proc_metrics)

    # ── CREATIVE ────────────────────────────────────────────────────
    cr_metrics = (
        f'<div style="display:grid;grid-template-columns:repeat(4,1fr);gap:8px;margin-bottom:6px">'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:#c97bc9">—</div>'
        f'<div style="font-size:10px;color:{MUTED}">Active Sponsors</div></div>'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{MID}">—</div>'
        f'<div style="font-size:10px;color:{MUTED}">Videos Posted</div></div>'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{INFO_FG}">—</div>'
        f'<div style="font-size:10px;color:{MUTED}">Stories Posted</div></div>'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{AMBER}">—</div>'
        f'<div style="font-size:10px;color:{MUTED}">Posts Scheduled</div></div></div>'
        f'<div style="font-size:10px;color:{MUTED};font-style:italic">⚡ Buffer / Meta API integration coming soon</div>')

    dept_card("Creative & Content","🎨",5,"#c97bc9",cr_metrics)

    # ── CUSTOMER SERVICE ────────────────────────────────────────────
    _sc = {}
    try: _sc = md.get("sum_c",{}) if "md" in dir() else {}
    except: pass
    cs_metrics = (
        f'<div style="display:grid;grid-template-columns:repeat(3,1fr);gap:8px;margin-bottom:6px">'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{AMBER}">{_sc.get("total_rcvd","—")}</div>'
        f'<div style="font-size:10px;color:{MUTED}">Messages Received</div></div>'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{MID}">{_sc.get("avg_resp","—")}</div>'
        f'<div style="font-size:10px;color:{MUTED}">Avg Response (min)</div></div>'
        f'<div style="background:{BG2};border-radius:8px;padding:8px;text-align:center">'
        f'<div style="font-size:20px;font-weight:600;color:{OK_FG}">{total_ords if "total_ords" in dir() else "—"}</div>'
        f'<div style="font-size:10px;color:{MUTED}">Orders This Month</div></div></div>')

    dept_card("Customer Service","💬",6,"#5b9bd5",cs_metrics)

    # ── WEEK DAILY REPORT SUMMARY ────────────────────────────────────
    st.markdown(f"<hr style='border-color:{BORDER};margin:4px 0 14px'>", unsafe_allow_html=True)
    st.markdown(
        f"<p style='font-size:11px;color:{MUTED};text-transform:uppercase;letter-spacing:.07em;margin-bottom:10px'>"
        f"Week {mon_dt.strftime('%d %b')} → {today_dt.strftime('%d %b %Y')} — Daily Report Status</p>",
        unsafe_allow_html=True)

    _all_dr  = [t for t in _at if "التقرير اليومي" in t["name"] or "تقرير يومي" in t["name"]]
    _dr_done = sum(1 for t in _all_dr if t["state"] in ("1_done","03_approved"))
    _dr_pend = sum(1 for t in _all_dr if t["state"]=="01_in_progress")
    _dr_tot  = len(_all_dr)
    _dr_rate = round(_dr_done/_dr_tot*100) if _dr_tot else 0

    wc = st.columns(4)
    def _wkpi(col,lbl,val,color):
        col.markdown(
            f'<div class="kpi" style="height:70px"><div class="kpi-lbl">{lbl}</div>'
            f'<div class="kpi-num" style="color:{color};font-size:22px">{val}</div></div>',
            unsafe_allow_html=True)
    _wkpi(wc[0],"Total Members",str(_dr_tot),MUTED)
    _wkpi(wc[1],"Submitted / Approved",str(_dr_done),OK_FG)
    _wkpi(wc[2],"Pending Today",str(_dr_pend),WARN_FG if _dr_pend else OK_FG)
    _wkpi(wc[3],"Submission Rate",f"{_dr_rate}%",OK_FG if _dr_rate>=80 else WARN_FG if _dr_rate>=50 else CRIT_FG)

    st.markdown("<div style='height:10px'></div>", unsafe_allow_html=True)
    _mh = f'<div style="display:flex;flex-wrap:wrap;gap:8px;margin-top:4px">'
    for t in sorted(_all_dr, key=lambda x:x["project_id"][1]):
        _users = [U.get(u,str(u)) for u in (t["user_ids"] or [])]
        _proj  = t["project_id"][1].replace(" & Content","").replace(" & Supply Chain","").replace(" & Facilities","").replace(" & Strategic","")
        _mh += (
            f'<div style="background:{CARD};border:0.5px solid {BORDER};border-radius:8px;padding:8px 12px;min-width:150px">'
            f'<div style="font-size:10px;color:{MUTED};margin-bottom:3px">{_proj}</div>'
            f'<div style="font-size:13px;font-weight:500;color:{TEXT};margin-bottom:5px">{", ".join(_users) or "—"}</div>'
            f'{_dbadge(t["state"])}</div>')
    _mh += '</div>'
    st.markdown(_mh, unsafe_allow_html=True)



# ══════════════════════════════════════════════════════════════════════════════
# TAB 5 — DAILY REPORT SUMMARY (AI-powered)
# ══════════════════════════════════════════════════════════════════════════════
with tab5:
    import re as _re
    from datetime import timedelta as _td5

    today_dt5 = date.today()
    mon_dt5   = today_dt5 - _td5(days=today_dt5.weekday())
    mon_s5    = str(mon_dt5)
    today_s5  = str(today_dt5)

    U5 = {8:"Hussam",18:"Abdullah",29:"Ala' Deep",9:"Alaa Oshah",
          15:"Marwan",13:"Nasser",27:"Khan",11:"Wesal",23:"Bader",
          6:"Moad",31:"Weam",30:"Wegdan",24:"Amal",12:"Wala",10:"Znjabel"}

    def _strip_html(html):
        if not html: return ""
        t = _re.sub(r'<br\s*/?>', '\n', html or "")
        t = _re.sub(r'</p>', '\n', t)
        t = _re.sub(r'</li>', '\n', t)
        t = _re.sub(r'<li>', '• ', t)
        t = _re.sub(r'<[^>]+>', '', t)
        t = _re.sub(r'[ \t]+', ' ', t)
        t = _re.sub(r'\n{3,}', '\n\n', t)
        return t.strip()

    def _parse_report(html):
        """Parse structured HTML daily report into sections."""
        if not html or len(html) < 20: return None
        # Extract name and date from header line
        # Format: 📋 التقرير اليومي — NAME | DATE
        header = _re.search(r'التقرير اليومي.*?—\s*([^|<]+?)\s*(?:\|([^<]+))?</', html)
        name  = header.group(1).strip() if header else ""
        rdate = header.group(2).strip() if (header and header.group(2)) else ""

        def _section(markers):
            """Extract items after any of the given Arabic markers."""
            for marker in markers:
                pat = rf'{_re.escape(marker)}.*?</(?:b|strong)>\s*</p>(.*?)(?=<p>|$)'
                m2 = _re.search(pat, html, _re.DOTALL)
                if m2:
                    block = m2.group(1)
                    items = _re.findall(r'<li>(.*?)</li>', block, _re.DOTALL)
                    if items:
                        return [_re.sub(r'<[^>]+>','',i).strip() for i in items if i.strip()]
                    # plain paragraph
                    txt = _re.sub(r'<[^>]+>','',block).strip()
                    return [txt] if txt and txt != "لا يوجد" else []
            return []

        def _text_section(markers):
            for marker in markers:
                pat = rf'{_re.escape(marker)}.*?</(?:b|strong)>\s*</p>(.*?)(?=<p>|$)'
                m2 = _re.search(pat, html, _re.DOTALL)
                if m2:
                    return _re.sub(r'<[^>]+>','',m2.group(1)).strip()
            return ""

        achievements = _section(["✅ المنجز اليوم","✅ الإنجازات","الإنجازات","المنجز"])
        challenges   = _text_section(["⚠️ التحديات","🔴 التحديات","التحديات"])
        pending      = _section(["📌 المهام المعلقة","المهام المعلقة","المعلق"])
        tomorrow     = _section(["📌 غداً","📅 خطة الغد","خطة الغد","غداً","غد"])
        notes        = _text_section(["💬 ملاحظات","ملاحظات"])

        # Build clean plain-text version for AI
        lines = []
        if name:  lines.append(f"الاسم: {name}")
        if rdate: lines.append(f"التاريخ: {rdate}")
        if achievements: lines.append("الإنجازات:\n" + "\n".join(f"  • {a}" for a in achievements))
        if challenges and challenges != "لا يوجد": lines.append(f"التحديات: {challenges}")
        if pending:   lines.append("المعلق:\n" + "\n".join(f"  • {p}" for p in pending))
        if tomorrow:  lines.append("غداً:\n"   + "\n".join(f"  • {t}" for t in tomorrow))
        if notes:     lines.append(f"ملاحظات: {notes}")

        return {
            "name": name, "date": rdate,
            "achievements": achievements,
            "challenges": challenges,
            "pending": pending,
            "tomorrow": tomorrow,
            "notes": notes,
            "text": "\n".join(lines),
            "raw": _strip_html(html)
        }

    @st.cache_data(ttl=120)
    def fetch_daily_data(ck=None):
        thirty = str(date.today() - _td5(days=30))
        # All daily report tasks — exclude Customer Service (project_id=6)
        daily_tasks = odoo("project.task","search_read",
            [["active","=",True],["project_id","!=",6],
             "|",["name","ilike","التقرير اليومي"],["name","ilike","تقرير يومي"]],
            {"fields":["id","name","project_id","user_ids","state","write_date"],"limit":50})
        task_ids = [t["id"] for t in daily_tasks]

        # All messages on those tasks last 30 days
        msgs = odoo("mail.message","search_read",
            [["res_id","in",task_ids],["model","=","project.task"],
             ["message_type","in",["comment","email"]],["date",">=",thirty]],
            {"fields":["res_id","body","date","author_id"],"limit":300})

        return {"tasks": daily_tasks, "msgs": msgs, "task_ids": task_ids}

    st.markdown(
        f"<p style='font-size:12px;color:{MUTED};text-transform:uppercase;"
        f"letter-spacing:.06em;margin-bottom:14px'>"
        f"Daily Report Intelligence — Week of {mon_dt5.strftime('%d %b')} → {today_dt5.strftime('%d %b %Y')}</p>",
        unsafe_allow_html=True)

    # Date range selector
    dr_col1, dr_col2, dr_col3 = st.columns([1,1,3])
    with dr_col1:
        range_opt = st.selectbox("Period",["This week","Yesterday","Last 7 days","Last 30 days"],
                                 label_visibility="collapsed")
    with dr_col2:
        if st.button("🔄 Refresh data"):
            st.cache_data.clear(); st.rerun()

    range_map = {
        "This week":   mon_s5,
        "Yesterday":   str(today_dt5 - _td5(days=1)),
        "Last 7 days": str(today_dt5 - _td5(days=7)),
        "Last 30 days":str(today_dt5 - _td5(days=30)),
    }
    since = range_map[range_opt]

    with st.spinner("Loading reports…"):
        dd = fetch_daily_data(ck=str(date.today()))

    daily_tasks = dd["tasks"]
    all_msgs    = dd["msgs"]
    task_map5   = {t["id"]: t for t in daily_tasks}

    # Filter messages by selected period
    period_msgs = [m for m in all_msgs if m["date"][:10] >= since]

    # Build per-member data
    members = {}
    for task in daily_tasks:
        proj = task["project_id"][1]
        for uid in (task["user_ids"] or []):
            uname = U5.get(uid, str(uid))
            if uname not in members:
                members[uname] = {
                    "uid": uid, "project": proj,
                    "task_id": task["id"], "task_state": task["state"],
                    "msgs": [], "last_update": task.get("write_date","")[:10]
                }

    # Attach messages to members
    for msg in all_msgs:
        if not msg.get("author_id"): continue
        author_name = msg["author_id"][1]
        body = _strip_html(msg.get("body",""))
        if not body or len(body.strip()) < 3: continue
        date_str = msg["date"][:10]
        if date_str < since: continue
        # Match to member by name (partial)
        matched = None
        for mname in members:
            if mname.lower() in author_name.lower() or author_name.lower() in mname.lower():
                matched = mname; break
        # Also match by task
        if not matched:
            task = task_map5.get(msg["res_id"],{})
            for uid in (task.get("user_ids") or []):
                uname = U5.get(uid)
                if uname and uname in members:
                    matched = uname; break
        if matched:
            parsed = _parse_report(msg.get("body",""))
            members[matched]["msgs"].append({
                "date": date_str,
                "body": body,
                "parsed": parsed
            })

    # ── Submission overview ─────────────────────────────────────────
    submitted = [k for k,v in members.items() if v["msgs"]]
    pending   = [k for k,v in members.items() if not v["msgs"]]
    total_m   = len(members)

    # KPI row
    mk = st.columns(4)
    def _mk(col, lbl, val, color):
        col.markdown(
            f'<div class="kpi" style="height:75px"><div class="kpi-lbl">{lbl}</div>'
            f'<div class="kpi-num" style="color:{color};font-size:22px">{val}</div></div>',
            unsafe_allow_html=True)
    _mk(mk[0],"Team Members",    str(total_m),       MUTED)
    _mk(mk[1],"Submitted",       str(len(submitted)),OK_FG)
    _mk(mk[2],"No Report",       str(len(pending)),  CRIT_FG if pending else OK_FG)
    _mk(mk[3],"Completion Rate", f"{round(len(submitted)/total_m*100) if total_m else 0}%",
        OK_FG if len(submitted)/total_m>=0.8 else WARN_FG if total_m else MUTED)

    st.markdown(f"<hr style='border-color:{BORDER};margin:14px 0'>", unsafe_allow_html=True)

    # ── Missing reports alert ───────────────────────────────────────
    if pending:
        pnames = ", ".join(pending)
        st.markdown(
            f'<div class="al al-c">🔴 <span><b>No report submitted</b> this period: {pnames}</span></div>',
            unsafe_allow_html=True)

    # ── AI Summary ─────────────────────────────────────────────────
    st.markdown(
        f"<p style='font-weight:600;font-size:14px;margin-bottom:10px'>🤖 AI Summary</p>",
        unsafe_allow_html=True)

    # Build context for Claude
    report_context = []
    for mname, md5 in members.items():
        if md5["msgs"]:
            entries = "\n".join(
                f"[{msg['date']}] {msg['body'][:300]}"
                for msg in sorted(md5["msgs"], key=lambda x: x["date"]))
            report_context.append(f"**{mname} ({md5['project']}):**\n{entries}")

    if not report_context:
        st.markdown(
            f'<div class="al al-w">⚠️ <span>No report messages found for the selected period. '
            f'Team members should submit their daily reports as Log Notes on their daily report tasks in Odoo.</span></div>',
            unsafe_allow_html=True)
    else:
        # Build context using parsed structure where available
        report_context = []
        for mname, md5 in members.items():
            if md5["msgs"]:
                entries = []
                for msg in sorted(md5["msgs"], key=lambda x: x["date"]):
                    p = msg.get("parsed")
                    if p and p.get("text"):
                        entries.append(f"[{msg['date']}]\n{p['text']}")
                    elif msg.get("body"):
                        entries.append(f"[{msg['date']}] {msg['body'][:300]}")
                if entries:
                    report_context.append(f"**{mname} ({md5['project']}):**\n" + "\n\n".join(entries))
        context_text = "\n\n".join(report_context)
        missing_text = f"No report: {', '.join(pending)}" if pending else "All members reported."

        ai_prompt = f"""You are the operations assistant for Auria, a Libyan natural haircare brand.
Below are the daily report messages submitted by the team in Odoo this period ({since} to {today_s5}).

{context_text}

{missing_text}

Write a concise management summary in English with these sections:
1. **Overall Status** — 2-3 sentences on team activity level
2. **Key Achievements** — bullet list of concrete things done
3. **Challenges & Blockers** — issues flagged by the team
4. **Pending & Follow-up** — what needs management attention
5. **Missing Reports** — who hasn't submitted (be direct)

Be decisive and specific. Use the actual names and details from the messages. Keep it under 300 words."""

        # Session state for AI summary
        if "dr_summary" not in st.session_state:
            st.session_state.dr_summary = None
            st.session_state.dr_summary_period = None

        col_gen, col_clear = st.columns([1,5])
        with col_gen:
            gen_btn = st.button("✨ Generate Summary", type="primary")
        with col_clear:
            if st.session_state.dr_summary:
                if st.button("🗑 Clear"):
                    st.session_state.dr_summary = None
                    st.rerun()

        if gen_btn:
            with st.spinner("Claude is reading the reports…"):
                import urllib.request as _ur2
                import json as _j2
                try:
                    try:
                        _oai_key = st.secrets["OPENAI_API_KEY"]
                    except Exception:
                        _oai_key = ""
                    if not _oai_key:
                        st.error("❌ OPENAI_API_KEY not found in Streamlit Secrets. Go to app Settings → Secrets and add it.")
                        raise Exception("No API key configured")
                    resp = _ur2.urlopen(
                        _ur2.Request(
                            "https://api.openai.com/v1/chat/completions",
                            data=_j2.dumps({
                                "model": "gpt-4o",
                                "max_tokens": 1000,
                                "messages": [
                                    {"role":"system","content":"You are the operations assistant for Auria, a Libyan natural haircare brand. Be concise, decisive and specific."},
                                    {"role":"user","content": ai_prompt}
                                ]
                            }).encode(),
                            headers={
                                "Content-Type": "application/json",
                                "Authorization": f"Bearer {_oai_key}",
                            },
                            method="POST"
                        ), timeout=30)
                    result = _j2.loads(resp.read())
                    st.session_state.dr_summary = result["choices"][0]["message"]["content"]
                    st.session_state.dr_summary_period = range_opt
                    st.rerun()
                except Exception as e:
                    err_msg = str(e)
                    if "401" in err_msg:
                        st.error("❌ OpenAI API key is invalid or expired. Check Streamlit Secrets → OPENAI_API_KEY")
                    elif "No API key" in err_msg:
                        pass  # already shown above
                    else:
                        st.error(f"AI error: {e}")

        if st.session_state.dr_summary:
            st.markdown(
                f'<div style="background:{BG2};border:0.5px solid {BORDER};border-left:3px solid {AMBER};'
                f'border-radius:8px;padding:16px;margin-top:8px;font-size:13px;color:{TEXT};line-height:1.7">'
                f'{st.session_state.dr_summary.replace(chr(10),"<br>").replace("**","<b>",1)}</div>',
                unsafe_allow_html=True)

    st.markdown(f"<hr style='border-color:{BORDER};margin:16px 0'>", unsafe_allow_html=True)

    # ── Per-member report cards ─────────────────────────────────────
    st.markdown(
        f"<p style='font-weight:600;font-size:14px;margin-bottom:12px'>📋 Individual Reports</p>",
        unsafe_allow_html=True)

    # Group by project
    by_proj5 = {}
    for mname, md5 in members.items():
        by_proj5.setdefault(md5["project"], []).append((mname, md5))

    PROJ_COLORS = {
        "Production Operations": AMBER,
        "Operations & Facilities": MID,
        "Procurement & Supply Chain": INFO_FG,
        "Creative & Content": "#c97bc9",
        "Customer Service": "#5b9bd5",
        "Financial management": WARN_FG,
        "Management & Strategic": MUTED,
    }

    STATE_DR = {
        "1_done":"✅ Submitted","03_approved":"🟢 Approved",
        "01_in_progress":"🟡 Pending","1_canceled":"❌ Cancelled",
    }

    for proj, member_list in sorted(by_proj5.items()):
        color = PROJ_COLORS.get(proj, MUTED)
        st.markdown(
            f'<div style="font-size:11px;font-weight:600;color:{color};text-transform:uppercase;'
            f'letter-spacing:.07em;margin:12px 0 8px;padding-left:4px;border-left:3px solid {color};padding-left:8px">'
            f'{proj}</div>',
            unsafe_allow_html=True)

        cols5 = st.columns(min(len(member_list), 3))
        for i, (mname, md5) in enumerate(member_list):
            col = cols5[i % 3]
            has_reports = bool(md5["msgs"])
            state_lbl = STATE_DR.get(md5["task_state"],"⚪ Unknown")

            # Latest message
            latest = ""
            all_entries = ""
            if md5["msgs"]:
                sorted_msgs5 = sorted(md5["msgs"], key=lambda x: x["date"], reverse=True)
                latest = sorted_msgs5[0]["body"][:200]
                all_entries = "\n\n".join(
                    f'<div style="border-bottom:0.5px solid {BORDER};padding:6px 0">'
                    f'<div style="font-size:10px;color:{MUTED};margin-bottom:3px">{msg["date"]}</div>'
                    f'<div style="font-size:12px;color:{TEXT};white-space:pre-wrap;line-height:1.5">{msg["body"][:300]}</div>'
                    f'</div>'
                    for msg in sorted_msgs5[:5])

            card_border = color if has_reports else CRIT_BD
            card_bg     = CARD

            expander_label = f"{mname} — {len(md5['msgs'])} report{'s' if len(md5['msgs'])!=1 else ''}"
            with col.expander(expander_label, expanded=False):
                st.markdown(
                    f'<div style="background:{card_bg};border-radius:8px">'
                    f'<div style="display:flex;justify-content:space-between;align-items:center;'
                    f'padding:4px 0 8px;border-bottom:0.5px solid {BORDER};margin-bottom:8px">'
                    f'<span style="font-size:11px;color:{MUTED}">Task status</span>'
                    f'<span style="font-size:11px;color:{color}">{state_lbl}</span>'
                    f'</div>'
                    f'<div style="font-size:11px;color:{MUTED};margin-bottom:4px">Last updated: {md5["last_update"]}</div>'
                    + (all_entries if all_entries else
                       f'<div style="font-size:12px;color:{CRIT_FG};padding:8px 0">🔴 No report submitted this period</div>')
                    + '</div>',
                    unsafe_allow_html=True)

    # ── Submission history chart ────────────────────────────────────
    st.markdown(f"<hr style='border-color:{BORDER};margin:16px 0'>", unsafe_allow_html=True)
    st.markdown(
        f"<p style='font-weight:600;font-size:14px;margin-bottom:10px'>📅 Submission History — Last 30 Days</p>",
        unsafe_allow_html=True)

    # Build date x member heatmap data
    all_dates = sorted(set(m["date"][:10] for m in all_msgs if m.get("date")))[-14:]
    member_names5 = list(members.keys())

    heat_data = []
    for mname in member_names5:
        row = {"Member": mname}
        member_dates = set(msg["date"] for msg in members[mname]["msgs"])
        for d in all_dates:
            row[d] = 1 if d in member_dates else 0
        heat_data.append(row)

    if heat_data and all_dates:
        df_heat = pd.DataFrame(heat_data).set_index("Member")
        fig_heat = go.Figure(data=go.Heatmap(
            z=df_heat.values,
            x=[d[5:] for d in df_heat.columns],  # MM-DD
            y=df_heat.index.tolist(),
            colorscale=[[0,"#1e2e1f"],[1,"#3B6D11"]],
            showscale=False,
            text=[["✅" if v else "—" for v in row] for row in df_heat.values],
            texttemplate="%{text}",
            hovertemplate="<b>%{y}</b><br>%{x}<br>%{text}<extra></extra>",
            xgap=3, ygap=3
        ))
        fig_heat.update_layout(
            margin=dict(l=0,r=0,t=10,b=0), height=max(200, len(member_names5)*32+40),
            plot_bgcolor=PLOT_BG, paper_bgcolor=PLOT_BG, font_color=TEXT)
        fig_heat.update_xaxes(side="top", gridcolor=BORDER, tickfont=dict(size=10))
        fig_heat.update_yaxes(gridcolor=BORDER, tickfont=dict(size=11))
        st.plotly_chart(fig_heat, use_container_width=True)
    else:
        st.markdown(
            f'<div class="al al-w">⚠️ No submission history to display for this period.</div>',
            unsafe_allow_html=True)


# ── Footer ────────────────────────────────────────────────────────────────────
st.markdown(f"""
<div style="margin-top:24px;padding:10px 0;border-top:1px solid {BORDER};
            font-size:11px;color:{MUTED};text-align:center">
  Auria Operations Dashboard · Odoo + Meta Ads + Messenger · refreshes every 30s
</div>""",unsafe_allow_html=True)
st.markdown("<script>setTimeout(()=>window.location.reload(),30000);</script>",unsafe_allow_html=True)
