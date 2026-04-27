# CIN Automation API

Python Flask API that fetches Indian company data from MCA, NSE, BSE.
Called from Make.com instead of hitting MCA directly.

---

## Deploy on Railway (Free — 5 minutes)

### Step 1 — Create GitHub repo
1. Go to github.com → New repository
2. Name it: `cin-api`
3. Upload all 4 files:
   - main.py
   - requirements.txt
   - Procfile
   - railway.json

### Step 2 — Deploy on Railway
1. Go to railway.app → Sign up free
2. Click "New Project"
3. Click "Deploy from GitHub repo"
4. Select your `cin-api` repo
5. Railway auto-detects Python and deploys
6. Wait 2 minutes → Railway gives you a URL like:
   `https://cin-api-production.up.railway.app`

### Step 3 — Test your API
Open browser and go to:
`https://YOUR-RAILWAY-URL.up.railway.app/health`

You should see:
```json
{"status": "ok", "timestamp": "2024-04-27T..."}
```

---

## API Endpoints

### GET /health
Check if API is running.

### POST /company
Get single company data.

**Request body:**
```json
{
  "cin": "L65920MH1994PLC080618"
}
```

**Response:**
```json
{
  "status": "success",
  "cin": "L65920MH1994PLC080618",
  "mca": {
    "found": true,
    "company_name": "HDFC Bank Limited",
    "status": "Active",
    "incorporation_date": "30-08-1994",
    "registered_address": "...",
    "paid_up_capital": "...",
    "roc": "RoC-Mumbai"
  },
  "nse": {
    "found": true,
    "symbol": "HDFCBANK",
    "listed": true
  },
  "bse": {
    "found": true,
    "scrip_code": "500180",
    "listed": true
  },
  "processed_at": "2024-04-27T12:00:00"
}
```

### POST /batch
Process multiple CINs at once.

**Request body:**
```json
{
  "cin_list": [
    "L65920MH1994PLC080618",
    "L85110KA1981PLC013115",
    "L22210MH1995PLC084781"
  ]
}
```

---

## Make.com HTTP Module Config

After deploying, update your Make.com HTTP module:

```
URL:    https://YOUR-RAILWAY-URL.up.railway.app/company
Method: POST
Body:   Raw / application/json

{
  "cin": "{{4.value}}"
}
```

That's it! Make.com now calls YOUR API → YOUR API calls MCA → returns clean JSON.

---

## Test CINs

| Company    | CIN                      |
|-----------|--------------------------|
| HDFC Bank  | L65920MH1994PLC080618   |
| Infosys    | L85110KA1981PLC013115   |
| TCS        | L22210MH1995PLC084781   |
| Wipro      | L32102KA1945PLC020800   |
| ICICI Bank | L65190GJ1994PLC021012   |
