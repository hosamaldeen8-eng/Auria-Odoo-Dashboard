# Auria Operations Dashboard

Live Streamlit dashboard connected to odoo.auria.global

## Run locally

```bash
pip install -r requirements.txt
streamlit run dashboard.py
```

Opens at http://localhost:8501 — refreshes every 60 seconds automatically.

## Deploy free on Streamlit Cloud

1. Push this folder to a GitHub repo (can be private)
2. Go to https://share.streamlit.io
3. Click **New app** → select your repo → set main file to `dashboard.py`
4. Click **Deploy** — live URL in ~2 minutes

## Deploy on a VPS (Ubuntu)

```bash
# Install
sudo apt update && sudo apt install python3-pip -y
pip install -r requirements.txt

# Run in background
nohup streamlit run dashboard.py --server.port 8501 --server.headless true &

# Optional: Nginx reverse proxy so it's on port 80
# /etc/nginx/sites-available/auria
server {
    listen 80;
    server_name your-domain.com;
    location / {
        proxy_pass http://localhost:8501;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

## Credentials

Odoo connection is hardcoded in `dashboard.py`. To use environment variables instead:

```python
import os
ODOO_PWD = os.environ.get("ODOO_PWD", "123456")
```

Then on Streamlit Cloud, add `ODOO_PWD` under **App settings → Secrets**.
