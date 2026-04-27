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

mca_limiter = RateLimiter(rpm=30)
nse_limiter = RateLimiter(rpm=60)
bse_limiter = RateLimiter(rpm=30)

# ─── CIN Validator ──────────────────────────────────────────────
def validate_cin(cin: str) -> bool:
    pattern = r'^[A-Z]{1}[0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$'
    return bool(re.match(pattern, cin.strip().upper()))

# ─── MCA Fetcher ────────────────────────────────────────────────
def fetch_mca_data(cin: str) -> dict:
    mca_limiter.wait()

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
        'Accept': 'application/json',
        'Referer': 'https://www.mca.gov.in/',
        'Origin': 'https://www.mca.gov.in',
        'X-Requested-With': 'XMLHttpRequest'
    }

    # ── Attempt 1: MCA V3 API ──────────────────────────────────
    try:
        url = "https://www.mca.gov.in/MCAGovServices/mca/ds/getCompanyDetailsBySearch"
        payload = {"cin": cin}
        r = requests.post(url, json=payload, headers=headers, timeout=20)
        if r.status_code == 200:
            data = r.json()
            if data:
                company = data[0] if isinstance(data, list) else data
                if company.get('companyName'):
                    logger.info(f"MCA V3 success for {cin}")
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
                        "email": company.get('email', ''),
                        "directors_count": company.get('numberOfDirectors', 0),
                    }
    except Exception as e:
        logger.warning(f"MCA V3 failed for {cin}: {e}")

    time.sleep(2)

    # ── Attempt 2: MCA Public Master Data ─────────────────────
    try:
        url2 = f"https://www.mca.gov.in/mcaservices/data/public/getCompanyMasterData/{cin}"
        r2 = requests.get(url2, headers=headers, timeout=20)
        if r2.status_code == 200:
            data2 = r2.json()
            company2 = data2.get('companyBasicDetail', {})
            if company2 and company2.get('companyName'):
                logger.info(f"MCA Public success for {cin}")
                return {
                    "found": True,
                    "source": "mca_public",
                    "company_name": company2.get('companyName', ''),
                    "status": company2.get('companyStatus', ''),
                    "incorporation_date": company2.get('dateOfIncorporation', ''),
                    "registered_address": company2.get('registeredOfficeAddress', ''),
                    "paid_up_capital": company2.get('paidUpCapital', ''),
                    "roc": company2.get('roc', ''),
                    "category": company2.get('companyCategory', ''),
                    "email": company2.get('email', ''),
                    "directors_count": company2.get('numberOfDirectors', 0),
                }
    except Exception as e:
        logger.warning(f"MCA Public failed for {cin}: {e}")

    time.sleep(2)

    # ── Attempt 3: MCA Signup Search ──────────────────────────
    try:
        url3 = "https://www.mca.gov.in/mcaservices/data/advanced_search/getCompanyDetailsSignup"
        payload3 = {
            "companyName": "",
            "cin": cin,
            "listOfStates": "",
            "registrationNumber": ""
        }
        r3 = requests.post(url3, json=payload3, headers=headers, timeout=20)
        if r3.status_code == 200:
            data3 = r3.json()
            company3 = data3.get('companyBasicDetail') or data3.get('data') or {}
            if company3 and company3.get('companyName'):
                logger.info(f"MCA Signup success for {cin}")
                return {
                    "found": True,
                    "source": "mca_signup",
                    "company_name": company3.get('companyName', ''),
                    "status": company3.get('companyStatus', ''),
                    "incorporation_date": company3.get('dateOfIncorporation', ''),
                    "registered_address": company3.get('registeredOfficeAddress', ''),
                    "paid_up_capital": company3.get('paidUpCapital', ''),
                    "roc": company3.get('roc', ''),
                    "category": company3.get('companyCategory', ''),
                    "email": company3.get('email', ''),
                    "directors_count": company3.get('numberOfDirectors', 0),
                }
    except Exception as e:
        logger.warning(f"MCA Signup failed for {cin}: {e}")

    time.sleep(2)

    # ── Attempt 4: Zaubacorp Fallback ─────────────────────────
    try:
        url4 = f"https://www.zaubacorp.com/company/x/{cin}"
        headers4 = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept': 'text/html,application/xhtml+xml',
        }
        r4 = requests.get(url4, headers=headers4, timeout=20)
        if r4.status_code == 200:
            soup = BeautifulSoup(r4.text, 'html.parser')

            name_tag = soup.find('h1')
            company_name = name_tag.text.strip() if name_tag else ''

            status = ''
            status_tag = soup.find(string=re.compile(r'Active|Inactive|Dissolved|Struck', re.I))
            if status_tag:
                status = status_tag.strip()

            inc_date = ''
            address = ''
            capital = ''
            roc = ''
            category = ''

            tables = soup.find_all('table')
            for table in tables:
                rows = table.find_all('tr')
                for row in rows:
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        label = cols[0].text.strip().lower()
                        value = cols[1].text.strip()
                        if 'incorporation' in label or 'date of inc' in label:
                            inc_date = value
                        elif 'address' in label or 'registered office' in label:
                            address = value
                        elif 'capital' in label:
                            capital = value
                        elif 'roc' in label or 'registrar' in label:
                            roc = value
                        elif 'category' in label:
                            category = value
                        elif 'status' in label:
                            status = value

            if company_name:
                logger.info(f"Zaubacorp success for {cin}")
                return {
                    "found": True,
                    "source": "zaubacorp",
                    "company_name": company_name,
                    "status": status,
                    "incorporation_date": inc_date,
                    "registered_address": address,
                    "paid_up_capital": capital,
                    "roc": roc,
                    "category": category,
                    "email": "",
                    "directors_count": 0,
                }
    except Exception as e:
        logger.warning(f"Zaubacorp failed for {cin}: {e}")

    time.sleep(2)

    # ── Attempt 5: Tofler Fallback ────────────────────────────
    try:
        url5 = f"https://www.tofler.in/company/{cin}"
        headers5 = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)',
            'Accept': 'text/html,application/xhtml+xml',
        }
        r5 = requests.get(url5, headers=headers5, timeout=20)
        if r5.status_code == 200:
            soup5 = BeautifulSoup(r5.text, 'html.parser')

            name_tag5 = soup5.find('h1')
            company_name5 = name_tag5.text.strip() if name_tag5 else ''

            inc_date5 = ''
            address5 = ''
            capital5 = ''
            status5 = ''

            for tag in soup5.find_all(['td', 'span', 'div']):
                text = tag.text.strip().lower()
                if 'incorporation' in text:
                    next_tag = tag.find_next_sibling()
                    if next_tag:
                        inc_date5 = next_tag.text.strip()
                elif 'registered' in text and 'address' in text:
                    next_tag = tag.find_next_sibling()
                    if next_tag:
                        address5 = next_tag.text.strip()
                elif 'paid up' in text or 'capital' in text:
                    next_tag = tag.find_next_sibling()
                    if next_tag:
                        capital5 = next_tag.text.strip()
                elif 'status' in text:
                    next_tag = tag.find_next_sibling()
                    if next_tag:
                        status5 = next_tag.text.strip()

            if company_name5:
                logger.info(f"Tofler success for {cin}")
                return {
                    "found": True,
                    "source": "tofler",
                    "company_name": company_name5,
                    "status": status5,
                    "incorporation_date": inc_date5,
                    "registered_address": address5,
                    "paid_up_capital": capital5,
                    "roc": "",
                    "category": "",
                    "email": "",
                    "directors_count": 0,
                }
    except Exception as e:
        logger.warning(f"Tofler failed for {cin}: {e}")

    logger.error(f"All sources failed for {cin}")
    return {
        "found": False,
        "cin": cin,
        "company_name": "",
        "status": "",
        "incorporation_date": "",
        "registered_address": "",
        "paid_up_capital": "",
        "error": "Data not found after 5 attempts"
    }


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
    body = request.get_json()
    if not body:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    cin = body.get('cin', '').strip().upper()

    if not cin:
        return jsonify({"status": "error", "message": "CIN is required"}), 400

    if not validate_cin(cin):
        return jsonify({"status": "error", "message": f"Invalid CIN format: {cin}"}), 400

    logger.info(f"Processing CIN: {cin}")

    mca_data = fetch_mca_data(cin)

    nse_data = {"found": False, "listed": False}
    bse_data = {"found": False, "listed": False}

    if mca_data.get('company_name'):
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

    logger.info(f"Done: {cin} | MCA: {mca_data.get('found')} | Source: {mca_data.get('source')} | NSE: {nse_data.get('listed')} | BSE: {bse_data.get('listed')}")
    return jsonify(result)


@app.route('/batch', methods=['POST'])
def batch_companies():
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
            results.append({"cin": cin, "status": "invalid"})
            continue

        mca_data = fetch_mca_data(cin)
        nse_data = {"found": False}
        bse_data = {"found": False}

        if mca_data.get('company_name'):
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

        time.sleep(2)

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
