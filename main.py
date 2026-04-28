from flask import Flask, request, jsonify
from flask_cors import CORS
import requests
import re
import time
import logging
from datetime import datetime

app = Flask(__name__)
CORS(app)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# ─── Sandbox API Config ─────────────────────────────────────────
SANDBOX_API_KEY    = "key_live_03b0987dc6774740a307ca435d605713"
SANDBOX_API_SECRET = "secret_live_ec4e027fbcc44d93bf3cf93724e03174"
SANDBOX_BASE       = "https://api.sandbox.co.in"
SANDBOX_VERSION    = "1.0"

# ─── NIC Code to Sector Mapping ─────────────────────────────────
NIC_SECTOR_MAP = {
    "01": "Agriculture", "02": "Agriculture", "03": "Agriculture",
    "05": "Mining", "06": "Mining", "07": "Mining", "08": "Mining",
    "10": "Manufacturing - Food", "11": "Manufacturing - Beverages",
    "13": "Manufacturing - Textiles", "14": "Manufacturing - Apparel",
    "20": "Manufacturing - Chemicals", "21": "Manufacturing - Pharmaceuticals",
    "26": "Manufacturing - Electronics", "27": "Manufacturing - Electrical",
    "29": "Manufacturing - Automotive",
    "35": "Energy & Utilities", "36": "Water & Waste",
    "41": "Construction", "42": "Construction", "43": "Construction",
    "45": "Trade - Automotive", "46": "Trade - Wholesale", "47": "Trade - Retail",
    "49": "Transportation", "50": "Transportation", "51": "Transportation",
    "55": "Hospitality", "56": "Food Services",
    "58": "Media & Publishing", "59": "Media & Entertainment", "60": "Broadcasting",
    "61": "Telecommunications",
    "62": "Information Technology", "63": "Information Technology",
    "64": "Financial Services", "65": "Insurance", "66": "Financial Services",
    "68": "Real Estate",
    "69": "Professional Services", "70": "Professional Services - Consulting",
    "71": "Professional Services - Engineering", "72": "Information Technology",
    "73": "Advertising & Research", "74": "Professional Services",
    "85": "Education", "86": "Healthcare", "87": "Healthcare",
    "90": "Arts & Entertainment", "93": "Sports & Recreation",
    "96": "Personal Services"
}

NIC_SUBSECTOR_MAP = {
    "62011": "Computer Programming",
    "62012": "Software Publishing",
    "62013": "Web Design & Development",
    "62091": "IT Consulting",
    "62099": "Other IT Services",
    "63111": "Data Processing & Hosting",
    "63120": "Web Portals",
    "64191": "Banking",
    "64200": "Holding Companies",
    "64910": "Financial Leasing",
    "64990": "Other Financial Services / NBFC",
    "66110": "Financial Markets Administration",
    "68100": "Real Estate - Buying & Selling",
    "68200": "Real Estate - Renting",
    "70100": "Activities of Head Offices",
    "70200": "Management Consulting",
    "72900": "Other IT and Computer Services",
    "85410": "Higher Education",
    "86100": "Hospital Activities",
    "86200": "Medical & Dental Practice"
}

def get_sector_from_nic(nic_code: str):
    if not nic_code:
        return "", ""
    code = str(nic_code).strip()
    prefix = code[:2]
    sector = NIC_SECTOR_MAP.get(prefix, "Other")
    subsector = NIC_SUBSECTOR_MAP.get(code[:5], sector)
    return sector, subsector

def get_nic_from_cin(cin: str):
    if not cin or len(cin) < 6:
        return ""
    return cin[1:6]

# ─── CIN Validator ──────────────────────────────────────────────
def validate_cin(cin: str) -> bool:
    pattern = r'^[A-Z]{1}[0-9]{5}[A-Z]{2}[0-9]{4}[A-Z]{3}[0-9]{6}$'
    return bool(re.match(pattern, cin.strip().upper()))

def validate_gstin(gstin: str) -> bool:
    pattern = r'^[0-9]{2}[A-Z]{5}[0-9]{4}[A-Z]{1}[1-9A-Z]{1}Z[0-9A-Z]{1}$'
    return bool(re.match(pattern, gstin.strip().upper()))

# ─── Sandbox Authentication ─────────────────────────────────────
def get_sandbox_token() -> str:
    try:
        headers = {
            'x-api-key': SANDBOX_API_KEY,
            'x-api-secret': SANDBOX_API_SECRET,
            'x-api-version': SANDBOX_VERSION,
            'accept': 'application/json'
        }
        r = requests.post(
            f"{SANDBOX_BASE}/authenticate",
            headers=headers,
            timeout=15
        )
        if r.status_code == 200:
            data = r.json()
            token = data.get('data', {}).get('access_token') or data.get('access_token')
            if token:
                logger.info("Sandbox auth successful")
                return token
        logger.error(f"Sandbox auth failed: {r.status_code} {r.text}")
        return ""
    except Exception as e:
        logger.error(f"Sandbox auth error: {e}")
        return ""

# ─── Fetch Company by CIN ───────────────────────────────────────
def fetch_company_by_cin(cin: str, token: str) -> dict:
    try:
        headers = {
            'Authorization': token,
            'x-api-key': SANDBOX_API_KEY,
            'x-api-version': SANDBOX_VERSION,
            'accept': 'application/json'
        }
        r = requests.get(
            f"{SANDBOX_BASE}/mca/companies/{cin}",
            headers=headers,
            timeout=20
        )
        if r.status_code == 200:
            data = r.json()
            company = data.get('data', data)

            # Get NIC and sector
            nic_code = get_nic_from_cin(cin)
            sector, subsector = get_sector_from_nic(nic_code)

            # Override with API industrial class if available
            if company.get('industrial_class'):
                industrial = company['industrial_class']
                api_nic = industrial.split('-')[0].strip() if '-' in industrial else nic_code
                api_sector, api_subsector = get_sector_from_nic(api_nic)
                if api_sector and api_sector != "Other":
                    sector = api_sector
                    subsector = api_subsector

            logger.info(f"Sandbox CIN success: {cin}")
            return {
                "found": True,
                "source": "sandbox_mca",
                "cin": company.get('cin', cin),
                "company_name": company.get('company_name', ''),
                "status": company.get('company_status', ''),
                "incorporation_date": company.get('date_of_incorporation', ''),
                "registered_address": company.get('registered_address', ''),
                "paid_up_capital": company.get('paid_up_capital', ''),
                "authorised_capital": company.get('authorised_capital', ''),
                "email": company.get('email', ''),
                "roc": company.get('roc_code', ''),
                "category": company.get('company_category', ''),
                "subcategory": company.get('company_subcategory', ''),
                "company_class": company.get('class_of_company', ''),
                "industrial_class": company.get('industrial_class', ''),
                "nic_code": nic_code,
                "sector": sector,
                "sub_sector": subsector,
                "directors": company.get('directors', []),
                "directors_count": len(company.get('directors', [])),
                "listed": company.get('listed_in_stock_exchange', ''),
                "pan": company.get('pan', ''),
                "age": calculate_age(company.get('date_of_incorporation', '')),
            }
        else:
            logger.error(f"Sandbox CIN failed: {r.status_code} {r.text}")
            return {
                "found": False,
                "error": f"API returned {r.status_code}: {r.text}"
            }
    except Exception as e:
        logger.error(f"Sandbox CIN error: {e}")
        return {"found": False, "error": str(e)}

# ─── Fetch Taxpayer by GSTIN ────────────────────────────────────
def fetch_taxpayer_by_gstin(gstin: str, token: str) -> dict:
    try:
        headers = {
            'Authorization': token,
            'x-api-key': SANDBOX_API_KEY,
            'x-api-version': SANDBOX_VERSION,
            'accept': 'application/json'
        }
        r = requests.get(
            f"{SANDBOX_BASE}/gst/taxpayers/{gstin}/search",
            headers=headers,
            timeout=20
        )
        if r.status_code == 200:
            data = r.json()
            taxpayer = data.get('data', data)
            logger.info(f"Sandbox GSTIN success: {gstin}")
            return {
                "found": True,
                "source": "sandbox_gst",
                "gstin": gstin,
                "company_name": taxpayer.get('legal_name', taxpayer.get('trade_name', '')),
                "trade_name": taxpayer.get('trade_name', ''),
                "status": taxpayer.get('status', ''),
                "registration_date": taxpayer.get('registration_date', ''),
                "address": taxpayer.get('principal_place_of_business', ''),
                "category": taxpayer.get('constitution_of_business', ''),
                "business_activities": taxpayer.get('nature_of_business_activities', []),
                "core_activity": taxpayer.get('nature_of_core_business_activity_description', ''),
                "state_jurisdiction": taxpayer.get('state_jurisdiction', ''),
                "centre_jurisdiction": taxpayer.get('centre_jurisdiction', ''),
            }
        else:
            return {"found": False, "error": f"API returned {r.status_code}"}
    except Exception as e:
        return {"found": False, "error": str(e)}

# ─── Age Calculator ─────────────────────────────────────────────
def calculate_age(doi_string: str) -> str:
    if not doi_string:
        return ""
    try:
        from dateutil import parser
        doi = parser.parse(doi_string)
        now = datetime.now()
        years = now.year - doi.year
        months = now.month - doi.month
        if months < 0:
            years -= 1
            months += 12
        return f"{years} years, {months} months"
    except:
        return ""

# ─── Routes ─────────────────────────────────────────────────────

@app.route('/health', methods=['GET'])
def health():
    return jsonify({
        "status": "ok",
        "timestamp": datetime.now().isoformat(),
        "sandbox_key": SANDBOX_API_KEY[:20] + "..."
    })

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

    # Get Sandbox token
    token = get_sandbox_token()
    if not token:
        return jsonify({
            "status": "error",
            "message": "Failed to authenticate with Sandbox API"
        }), 500

    # Fetch company data
    mca_data = fetch_company_by_cin(cin, token)

    result = {
        "status": "success",
        "cin": cin,
        "data": mca_data,
        "mca": mca_data,
        "processed_at": datetime.now().isoformat()
    }

    logger.info(f"Done: {cin} | Found: {mca_data.get('found')} | Company: {mca_data.get('company_name')}")
    return jsonify(result)

@app.route('/gstin', methods=['POST'])
def get_gstin():
    """
    GST endpoint
    Body: { "gstin": "29AABCI1681G1ZE" }
    """
    body = request.get_json()
    if not body:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    gstin = body.get('gstin', '').strip().upper()

    if not gstin:
        return jsonify({"status": "error", "message": "GSTIN is required"}), 400

    logger.info(f"Processing GSTIN: {gstin}")

    token = get_sandbox_token()
    if not token:
        return jsonify({"status": "error", "message": "Auth failed"}), 500

    gst_data = fetch_taxpayer_by_gstin(gstin, token)

    return jsonify({
        "status": "success",
        "gstin": gstin,
        "data": gst_data,
        "processed_at": datetime.now().isoformat()
    })

@app.route('/lookup', methods=['POST'])
def lookup():
    """
    Auto-detect CIN or GSTIN
    Body: { "identifier": "L65920MH1994PLC080618" }
    """
    body = request.get_json()
    if not body:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    identifier = body.get('identifier', '').strip().upper()

    if not identifier:
        return jsonify({"status": "error", "message": "identifier is required"}), 400

    token = get_sandbox_token()
    if not token:
        return jsonify({"status": "error", "message": "Auth failed"}), 500

    if len(identifier) == 21:
        # CIN
        if not validate_cin(identifier):
            return jsonify({"status": "error", "message": "Invalid CIN format"}), 400
        data = fetch_company_by_cin(identifier, token)
        return jsonify({"status": "success", "type": "CIN", "data": data})

    elif len(identifier) == 15:
        # GSTIN
        data = fetch_taxpayer_by_gstin(identifier, token)
        return jsonify({"status": "success", "type": "GSTIN", "data": data})

    else:
        return jsonify({
            "status": "error",
            "message": f"Invalid length {len(identifier)}. CIN=21 chars, GSTIN=15 chars"
        }), 400

@app.route('/batch', methods=['POST'])
def batch_companies():
    """
    Batch endpoint
    Body: { "cin_list": ["CIN1", "CIN2"] }
    """
    body = request.get_json()
    if not body:
        return jsonify({"status": "error", "message": "No JSON body"}), 400

    cin_list = body.get('cin_list', [])
    if not cin_list:
        return jsonify({"status": "error", "message": "cin_list required"}), 400

    # Get token once for all
    token = get_sandbox_token()
    if not token:
        return jsonify({"status": "error", "message": "Auth failed"}), 500

    results = []
    for cin in cin_list:
        cin = cin.strip().upper()
        if not validate_cin(cin):
            results.append({"cin": cin, "status": "invalid"})
            continue

        data = fetch_company_by_cin(cin, token)
        results.append({
            "cin": cin,
            "status": "success" if data.get('found') else "not_found",
            "data": data
        })
        time.sleep(1)

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
