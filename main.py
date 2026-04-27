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

# ─── NIC Code to Sector Mapping ─────────────────────────────────
NIC_TO_SECTOR = {
    "01": "Agriculture", "02": "Agriculture", "03": "Agriculture",
    "05": "Mining", "06": "Mining", "07": "Mining", "08": "Mining",
    "10": "Food & Beverages", "11": "Food & Beverages", "12": "Tobacco",
    "13": "Textiles", "14": "Textiles", "15": "Leather",
    "16": "Wood Products", "17": "Paper", "18": "Printing",
    "19": "Petroleum", "20": "Chemicals", "21": "Pharmaceuticals",
    "22": "Rubber & Plastics", "23": "Non-Metallic Minerals",
    "24": "Basic Metals", "25": "Fabricated Metals",
    "26": "Electronics & IT Hardware", "27": "Electrical Equipment",
    "28": "Machinery", "29": "Automobiles", "30": "Transport Equipment",
    "31": "Furniture", "32": "Manufacturing",
    "35": "Electricity & Gas", "36": "Water Supply",
    "41": "Construction", "42": "Construction", "43": "Construction",
    "45": "Auto Retail", "46": "Wholesale Trade", "47": "Retail Trade",
    "49": "Transport", "50": "Water Transport", "51": "Air Transport",
    "52": "Logistics", "53": "Postal Services",
    "55": "Hotels & Tourism", "56": "Food Services",
    "58": "Publishing", "59": "Media & Entertainment",
    "60": "Broadcasting", "61": "Telecom", "62": "IT Services",
    "63": "IT Services", "64": "Banking & Finance",
    "65": "Insurance & Finance", "66": "Finance",
    "68": "Real Estate", "69": "Legal Services",
    "70": "Management Consulting", "71": "Architecture & Engineering",
    "72": "Research & Development", "73": "Advertising",
    "74": "Professional Services", "75": "Veterinary",
    "77": "Rental Services", "78": "Employment Services",
    "79": "Travel & Tourism", "80": "Security Services",
    "81": "Facility Management", "82": "Business Support",
    "84": "Government", "85": "Education",
    "86": "Healthcare", "87": "Residential Care",
    "88": "Social Work", "90": "Arts & Entertainment",
    "91": "Libraries & Museums", "92": "Gambling",
    "93": "Sports & Recreation", "94": "Membership Organizations",
    "95": "Repair Services", "96": "Personal Services",
    "97": "Household Services", "99": "Other Services"
}

NIC_TO_SUBSECTOR = {
    "62": "Software & IT Services",
    "63": "Data Processing & Hosting",
    "64": "Banking",
    "65": "Insurance",
    "66": "Capital Markets",
    "21": "Pharmaceutical Manufacturing",
    "26": "Electronic Components",
    "29": "Motor Vehicles",
    "41": "Building Construction",
    "45": "Motor Vehicle Trade",
    "46": "Wholesale Distribution",
    "47": "Retail",
    "49": "Land Transport",
    "55": "Hotels & Resorts",
    "61": "Telecommunications",
    "68": "Real Estate Activities",
    "85": "Educational Institutions",
    "86": "Hospitals & Clinics",
}

def get_sector_from_nic(nic_code: str):
    if not nic_code:
        return "", ""
    code = str(nic_code).strip()[:2]
    sector = NIC_TO_SECTOR.get(code, "Other")
    subsector = NIC_TO_SUBSECTOR.get(code, sector)
    return sector, subsector

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

    # ── Attempt 1: MCA V3 API ─────────────────────────────────
    try:
        url = "https://www.mca.gov.in/MCAGovServices/mca/ds/getCompanyDetailsBySearch"
        r = requests.post(url, json={"cin": cin}, headers=headers, timeout=20)
        if r.status_code == 200:
            data = r.json()
            if data:
                company = data[0] if isinstance(data, list) else data
                if company.get('companyName'):
                    nic = company.get('nicCode', '')
                    sector, subsector = get_sector_from_nic(nic)
                    logger.info(f"MCA V3 success for {cin}")
                    return {
                        "found": True,
                        "source": "mca_v3",
                        "company_name": company.get('companyName', ''),
                        "status": company.get('companyStatus', ''),
                        "incorporation_date": company.get('dateOfIncorporation', ''),
                        "registered_address": company.get('registeredOfficeAddress', ''),
                        "paid_up_capital": company.get('paidUpCapital', ''),
                        "authorised_capital": company.get('authorisedCapital', ''),
                        "roc": company.get('roc', ''),
                        "category": company.get('companyCategory', ''),
                        "subcategory": company.get('companySubcategory', ''),
                        "company_class": company.get('classOfCompany', ''),
                        "email": company.get('email', ''),
                        "pan": company.get('pan', ''),
                        "nic_code": nic,
                        "sector": sector,
                        "sub_sector": subsector,
                        "directors_count": company.get('numberOfDirectors', 0),
                        "listed": company.get('whetherListed', ''),
                        "active_compliance": company.get('activeCompliance', ''),
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
                nic = company2.get('nicCode', '')
                sector, subsector = get_sector_from_nic(nic)
                logger.info(f"MCA Public success for {cin}")
                return {
                    "found": True,
                    "source": "mca_public",
                    "company_name": company2.get('companyName', ''),
                    "status": company2.get('companyStatus', ''),
                    "incorporation_date": company2.get('dateOfIncorporation', ''),
                    "registered_address": company2.get('registeredOfficeAddress', ''),
                    "paid_up_capital": company2.get('paidUpCapital', ''),
                    "authorised_capital": company2.get('authorisedCapital', ''),
                    "roc": company2.get('roc', ''),
                    "category": company2.get('companyCategory', ''),
                    "subcategory": company2.get('companySubcategory', ''),
                    "company_class": company2.get('classOfCompany', ''),
                    "email": company2.get('email', ''),
                    "pan": company2.get('pan', ''),
                    "nic_code": nic,
                    "sector": sector,
                    "sub_sector": subsector,
                    "directors_count": company2.get('numberOfDirectors', 0),
                    "listed": company2.get('whetherListed', ''),
                    "active_compliance": company2.get('activeCompliance', ''),
                }
    except Exception as e:
        logger.warning(f"MCA Public failed for {cin}: {e}")

    time.sleep(2)

    # ── Attempt 3: MCA Signup Search ──────────────────────────
    try:
        url3 = "https://www.mca.gov.in/mcaservices/data/advanced_search/getCompanyDetailsSignup"
        payload3 = {"companyName": "", "cin": cin, "listOfStates": "", "registrationNumber": ""}
        r3 = requests.post(url3, json=payload3, headers=headers, timeout=20)
        if r3.status_code == 200:
            data3 = r3.json()
            company3 = data3.get('companyBasicDetail') or data3.get('data') or {}
            if company3 and company3.get('companyName'):
                nic = company3.get('nicCode', '')
                sector, subsector = get_sector_from_nic(nic)
                logger.info(f"MCA Signup success for {cin}")
                return {
                    "found": True,
                    "source": "mca_signup",
                    "company_name": company3.get('companyName', ''),
                    "status": company3.get('companyStatus', ''),
                    "incorporation_date": company3.get('dateOfIncorporation', ''),
                    "registered_address": company3.get('registeredOfficeAddress', ''),
                    "paid_up_capital": company3.get('paidUpCapital', ''),
                    "authorised_capital": company3.get('authorisedCapital', ''),
                    "roc": company3.get('roc', ''),
                    "category": company3.get('companyCategory', ''),
                    "subcategory": company3.get('companySubcategory', ''),
                    "company_class": company3.get('classOfCompany', ''),
                    "email": company3.get('email', ''),
                    "pan": company3.get('pan', ''),
                    "nic_code": nic,
                    "sector": sector,
                    "sub_sector": subsector,
                    "directors_count": company3.get('numberOfDirectors', 0),
                    "listed": company3.get('whetherListed', ''),
                    "active_compliance": company3.get('activeCompliance', ''),
                }
    except Exception as e:
        logger.warning(f"MCA Signup failed for {cin}: {e}")

    time.sleep(2)

    # ── Attempt 4: Zaubacorp Fallback ─────────────────────────
    try:
        url4 = f"https://www.zaubacorp.com/company/x/{cin}"
        headers4 = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Accept': 'text/html'}
        r4 = requests.get(url4, headers=headers4, timeout=20)
        if r4.status_code == 200:
            soup = BeautifulSoup(r4.text, 'html.parser')
            name_tag = soup.find('h1')
            company_name = name_tag.text.strip() if name_tag else ''

            inc_date = address = capital = status = pan = email = roc = category = nic = ''

            tables = soup.find_all('table')
            for table in tables:
                for row in table.find_all('tr'):
                    cols = row.find_all('td')
                    if len(cols) >= 2:
                        label = cols[0].text.strip().lower()
                        value = cols[1].text.strip()
                        if 'incorporation' in label:
                            inc_date = value
                        elif 'address' in label or 'registered office' in label:
                            address = value
                        elif 'capital' in label and 'paid' in label:
                            capital = value
                        elif 'status' in label:
                            status = value
                        elif 'pan' in label:
                            pan = value
                        elif 'email' in label:
                            email = value
                        elif 'roc' in label or 'registrar' in label:
                            roc = value
                        elif 'category' in label:
                            category = value
                        elif 'nic' in label:
                            nic = value

            sector, subsector = get_sector_from_nic(nic)

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
                    "authorised_capital": "",
                    "roc": roc,
                    "category": category,
                    "subcategory": "",
                    "company_class": "",
                    "email": email,
                    "pan": pan,
                    "nic_code": nic,
                    "sector": sector,
                    "sub_sector": subsector,
                    "directors_count": 0,
                    "listed": "",
                    "active_compliance": "",
                }
    except Exception as e:
        logger.warning(f"Zaubacorp failed for {cin}: {e}")

    time.sleep(2)

    # ── Attempt 5: Tofler Fallback ────────────────────────────
    try:
        url5 = f"https://www.tofler.in/company/{cin}"
        headers5 = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)', 'Accept': 'text/html'}
        r5 = requests.get(url5, headers=headers5, timeout=20)
        if r5.status_code == 200:
            soup5 = BeautifulSoup(r5.text, 'html.parser')
            name_tag5 = soup5.find('h1')
            company_name5 = name_tag5.text.strip() if name_tag5 else ''

            inc_date5 = address5 = capital5 = status5 = pan5 = nic5 = ''

            for tag in soup5.find_all(['td', 'span', 'div']):
                text = tag.text.strip().lower()
                next_tag = tag.find_next_sibling()
                if not next_tag:
                    continue
                val = next_tag.text.strip()
                if 'incorporation' in text:
                    inc_date5 = val
                elif 'registered' in text and 'address' in text:
                    address5 = val
                elif 'paid up' in text:
                    capital5 = val
                elif 'status' in text:
                    status5 = val
                elif 'pan' in text:
                    pan5 = val
                elif 'nic' in text:
                    nic5 = val

            sector5, subsector5 = get_sector_from_nic(nic5)

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
                    "authorised_capital": "",
                    "roc": "",
                    "category": "",
                    "subcategory": "",
                    "company_class": "",
                    "email": "",
                    "pan": pan5,
                    "nic_code": nic5,
                    "sector": sector5,
                    "sub_sector": subsector5,
                    "directors_count": 0,
                    "listed": "",
                    "active_compliance": "",
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
        "authorised_capital": "",
        "roc": "",
        "category": "",
        "subcategory": "",
        "company_class": "",
        "email": "",
        "pan": "",
        "nic_code": "",
        "sector": "",
        "sub_sector": "",
        "directors_count": 0,
        "listed": "",
        "active_compliance": "",
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
        # Step 1: Get symbol from autocomplete
        url = f"https://www.nseindia.com/api/search/autocomplete?q={company_name}"
        r = requests.get(url, headers=headers, timeout=15)
        if r.status_code == 200:
            data = r.json()
            symbols = data.get('symbols', [])
            if symbols:
                top = symbols[0]
                symbol = top.get('symbol', '')

                # Step 2: Get detailed company info including sector
                time.sleep(1)
                url2 = f"https://www.nseindia.com/api/quote-equity?symbol={symbol}"
                r2 = requests.get(url2, headers=headers, timeout=15)
                sector = ''
                subsector = ''
                industry = ''

                if r2.status_code == 200:
                    data2 = r2.json()
                    info = data2.get('info', {})
                    sector = info.get('sector', '')
                    subsector = info.get('industry', '')
                    industry = info.get('basicIndustry', '')

                return {
                    "found": True,
                    "symbol": symbol,
                    "company_name": top.get('symbol_info', ''),
                    "sector": sector,
                    "sub_sector": subsector,
                    "industry": industry,
                    "listed": True
                }
        return {"found": False, "listed": False, "sector": "", "sub_sector": ""}
    except Exception as e:
        logger.warning(f"NSE fetch failed: {e}")
        return {"found": False, "listed": False, "sector": "", "sub_sector": "", "error": str(e)}


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
                scrip_code = top.get('SCRIP_CD', '')

                # Get detailed BSE info including sector
                time.sleep(1)
                url2 = f"https://api.bseindia.com/BseIndiaAPI/api/ComHeader/w?quotetype=EQ&scripcode={scrip_code}"
                r2 = requests.get(url2, headers=headers, timeout=15)
                sector = ''
                subsector = ''
                pan = ''

                if r2.status_code == 200:
                    data2 = r2.json()
                    sector = data2.get('Sector', '')
                    subsector = data2.get('Industry', '')
                    pan = data2.get('PAN', '')

                return {
                    "found": True,
                    "scrip_code": scrip_code,
                    "company_name": top.get('Issuer_Name', ''),
                    "sector": sector,
                    "sub_sector": subsector,
                    "pan": pan,
                    "listed": True
                }
        return {"found": False, "listed": False, "sector": "", "sub_sector": ""}
    except Exception as e:
        logger.warning(f"BSE fetch failed: {e}")
        return {"found": False, "listed": False, "sector": "", "sub_sector": "", "error": str(e)}


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

    nse_data = {"found": False, "listed": False, "sector": "", "sub_sector": ""}
    bse_data = {"found": False, "listed": False, "sector": "", "sub_sector": ""}

    if mca_data.get('company_name'):
        company_name = mca_data['company_name']
        nse_data = fetch_nse_data(company_name)
        time.sleep(1)
        bse_data = fetch_bse_data(company_name)

    # Use NSE sector if MCA sector is empty
    if not mca_data.get('sector') and nse_data.get('sector'):
        mca_data['sector'] = nse_data['sector']
        mca_data['sub_sector'] = nse_data.get('sub_sector', '')

    # Use BSE sector as last resort
    if not mca_data.get('sector') and bse_data.get('sector'):
        mca_data['sector'] = bse_data['sector']
        mca_data['sub_sector'] = bse_data.get('sub_sector', '')

    # Use BSE PAN if MCA PAN is empty
    if not mca_data.get('pan') and bse_data.get('pan'):
        mca_data['pan'] = bse_data['pan']

    result = {
        "status": "success",
        "cin": cin,
        "mca": mca_data,
        "nse": nse_data,
        "bse": bse_data,
        "processed_at": datetime.now().isoformat()
    }

    logger.info(f"Done: {cin} | Source: {mca_data.get('source')} | Sector: {mca_data.get('sector')} | NSE: {nse_data.get('listed')} | BSE: {bse_data.get('listed')}")
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

        if not mca_data.get('sector') and nse_data.get('sector'):
            mca_data['sector'] = nse_data['sector']
            mca_data['sub_sector'] = nse_data.get('sub_sector', '')

        if not mca_data.get('pan') and bse_data.get('pan'):
            mca_data['pan'] = bse_data['pan']

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
