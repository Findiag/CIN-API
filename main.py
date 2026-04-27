from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
from bs4 import BeautifulSoup
import re
import time
import logging
from datetime import datetime

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Rate Limiter ───────────────────────────────────────────────
class RateLimiter:
    def __init__(self, rpm=30):
        self.interval = 60 / rpm
        self.last_request = 0

    def wait(self):
        elapsed = time.time() - self.last_request
        if elapsed < self.interval:
            time.sleep(self.interval - elapsed)
        self.last_request = time.time()

mca_limiter  = RateLimiter(rpm=30)
nse_limiter  = RateLimiter(rpm=60)
bse_limiter  = RateLimiter(rpm=30)

# ─── CIN Validator ──────────────────────────────────────────────
def validate_cin(cin: str) -> bool:
    pattern = r'^[A-Z]{1}[0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$'
    return bool(re.match(pattern, cin.strip().upper()))

# ─── MCA Fetcher ────────────────────────────────────────────────
def fetch_mca_data(cin: str) -> dict:
    mca_limiter.wait()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'application/json, text/html',
        'Referer': 'https://www.mca.gov.in/',
        'Origin': 'https://www.mca.gov.in',
    }

    # Try endpoint 1 — MCA v3 POST
    try:
        url = "https://www.mca.gov.in/mcaservices/data/advanced_search/getCompanyDetailsSignup"
        payload = {
            "companyName": "",
            "cin": cin,
            "listOfStates": "",
            "registrationNumber": ""
        }
        r = requests.post(url, json=payload, headers=headers, timeout=20)
        if r.status_code == 200:
            data = r.json()
            company = data.get('companyBasicDetail') or data.get('data') or {}
            if company and company.get('companyName'):
                logger.info(f"MCA v3 success for {cin}")
                return {
                    "found": True,
                    "source": "mca_v3",
                    "company_name": company.get('companyName', ''),
                    "status": company.get('companyStatus', ''),
                    "incorporation_date": company.get('dateOfIncorporation', ''),
                    "registered_address": company.get('registeredOfficeAddress', ''),
                    "paid_up_capital": company.get('paidUpCapital', ''),
                    "roc": company.get('roc', ''),
                    "category": company.get('companyCategory', ''),
                    "company_class": company.get('companyClass', ''),
                    "email": company.get('email', ''),
                    "directors_count": company.get('numberOfDirectors', 0),
                }
    except Exception as e:
        logger.warning(f"MCA v3 failed for {cin}: {e}")

    time.sleep(2)

    # Try endpoint 2 — MCA public master data
    try:
        url2 = f"https://www.mca.gov.in/mcaservices/data/public/getCompanyMasterData/{cin}"
        r2 = requests.get(url2, headers=headers, timeout=20)
        if r2.status_code == 200:
            data2 = r2.json()
            logger.info(f"MCA public success for {cin}")
            return {
                "found": True,
                "source": "mca_public",
                "raw": data2
            }
    except Exception as e:
        logger.warning(f"MCA public failed for {cin}: {e}")

    time.sleep(2)

    # Try endpoint 3 — MCA search HTML scrape
    try:
        url3 = f"https://www.mca.gov.in/mcaservices/?action=SearchCompany&cin={cin}"
        r3 = requests.get(url3, headers=headers, timeout=20)
        if r3.status_code == 200 and len(r3.text) > 1000:
            soup = BeautifulSoup(r3.text, 'html.parser')
            data3 = parse_mca_html(soup, cin)
            if data3.get('company_name'):
                logger.info(f"MCA HTML scrape success for {cin}")
                return data3
    except Exception as e:
        logger.warning(f"MCA HTML scrape failed for {cin}: {e}")

    return {"found": False, "cin": cin, "error": "MCA data not found after 3 attempts"}


def parse_mca_html(soup, cin: str) -> dict:
    data = {"found": False, "cin": cin, "source": "mca_html"}
    try:
        name_tag = soup.find('td', string=re.compile('Company Name', re.I))
        if name_tag and name_tag.find_next_sibling('td'):
            data['company_name'] = name_tag.find_next_sibling('td').text.strip()
            data['found'] = True

        status_tag = soup.find(string=re.compile('Status', re.I))
        if status_tag:
            match = re.search(r'Status[:\s]+([^\n<]+)', status_tag, re.I)
            if match:
                data['status'] = match.group(1).strip()

        inc_match = re.search(r'(\d{2}-\d{2}-\d{4})', soup.get_text())
        if inc_match:
            data['incorporation_date'] = inc_match.group(1)

        addr_tag = soup.find('td', string=re.compile('Registered Office', re.I))
        if addr_tag and addr_tag.find_next_sibling('td'):
            data['registered_address'] = addr_tag.find_next_sibling('td').text.strip()

    except Exception as e:
        logger.error(f"HTML parse error: {e}")
    return data


# ─── NSE Fetcher ────────────────────────────────────────────────
def fetch_nse_data(company_name: str) -> dict:
    nse_limiter.wait()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': '*/*',
        'Referer': 'https://www.nseindia.com/',
    }
    try:
        url = f"https://www.nseindia.com/api/search/autocomplete?q={company_name}"
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            symbols = data.get('symbols', [])
            if symbols:
                top = symbols[0]
                return {
                    "found": True,
                    "symbol": top.get('symbol', ''),
                    "company_name": top.get('symbol_info', ''),
                    "sector": top.get('meta', {}).get('sector', '') if isinstance(top.get('meta'), dict) else '',
                    "listed": True
                }
        return {"found": False, "listed": False}
    except Exception as e:
        logger.warning(f"NSE fetch failed: {e}")
        return {"found": False, "listed": False, "error": str(e)}


# ─── BSE Fetcher ────────────────────────────────────────────────
def fetch_bse_data(company_name: str) -> dict:
    bse_limiter.wait()
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'application/json',
        'Origin': 'https://www.bseindia.com',
        'Referer': 'https://www.bseindia.com/',
    }
    try:
        url = f"https://api.bseindia.com/BseIndiaAPI/api/fetchComp/w?search={company_name}&type=equity&flag=0"
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            table = data.get('Table', [])
            if table:
                top = table[0]
                return {
                    "found": True,
                    "scrip_code": top.get('SCRIP_CD', ''),
                    "company_name": top.get('Issuer_Name', ''),
                    "listed": True
                }
        return {"found": False, "listed": False}
    except Exception as e:
        logger.warning(f"BSE fetch failed: {e}")
        return {"found": False, "listed": False, "error": str(e)}


# ─── Routes ─────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    return jsonify({"status": "ok", "timestamp": datetime.now().isoformat()})


@app.route('/company', methods=['POST'])
def get_company():
    """
    Main endpoint — called from Make.com HTTP module
    Body: { "cin": "L65920MH1994PLC080618" }
    """
    body = request.get_json()
    if not body:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    cin = body.get('cin', '').strip().upper()

    if not cin:
        return jsonify({"status": "error", "message": "CIN is required"}), 400

    if not validate_cin(cin):
        return jsonify({"status": "error", "message": f"Invalid CIN format: {cin}"}), 400

    logger.info(f"Processing CIN: {cin}")

    # Step 1: MCA data
    mca_data = fetch_mca_data(cin)

    # Step 2: NSE data (only if company found)
    nse_data = {"found": False, "listed": False}
    bse_data = {"found": False, "listed": False}

    if mca_data.get('found') and mca_data.get('company_name'):
        company_name = mca_data['company_name']
        nse_data = fetch_nse_data(company_name)
        time.sleep(1)
        bse_data = fetch_bse_data(company_name)

    result = {
        "status": "success",
        "cin": cin,
        "mca": mca_data,
        "nse": nse_data,
        "bse": bse_data,
        "processed_at": datetime.now().isoformat()
    }

    logger.info(f"Done: {cin} | MCA found: {mca_data.get('found')} | NSE: {nse_data.get('listed')} | BSE: {bse_data.get('listed')}")
    return jsonify(result)


@app.route('/batch', methods=['POST'])
def batch_companies():
    """
    Batch endpoint — process multiple CINs at once
    Body: { "cin_list": ["CIN1", "CIN2", ...] }
    """
    body = request.get_json()
    if not body:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    cin_list = body.get('cin_list', [])
    if not cin_list:
        return jsonify({"status": "error", "message": "cin_list is required"}), 400

    results = []
    for cin in cin_list:
        cin = cin.strip().upper()
        if not validate_cin(cin):
            results.append({"cin": cin, "status": "invalid", "error": "Invalid CIN format"})
            continue

        mca_data = fetch_mca_data(cin)
        nse_data = {"found": False}
        bse_data = {"found": False}

        if mca_data.get('found') and mca_data.get('company_name'):
            nse_data = fetch_nse_data(mca_data['company_name'])
            time.sleep(1)
            bse_data = fetch_bse_data(mca_data['company_name'])

        results.append({
            "cin": cin,
            "status": "success" if mca_data.get('found') else "not_found",
            "mca": mca_data,
            "nse": nse_data,
            "bse": bse_data
        })

        time.sleep(2)  # rate limiting between each CIN

    return jsonify({
        "status": "success",
        "total": len(results),
        "successful": len([r for r in results if r['status'] == 'success']),
        "failed": len([r for r in results if r['status'] != 'success']),
        "results": results,
        "processed_at": datetime.now().isoformat()
    })


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
