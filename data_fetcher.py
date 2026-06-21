"""
Data fetching for NSE Sentiment Analyzer.
Stock data via yfinance + news via RSS + DuckDuckGo fallback.
"""

import yfinance as yf
import requests
import feedparser
import html
import time
import streamlit as st
import re
import random
import math
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from duckduckgo_search import DDGS
from persistence import cache_get, cache_set


# ─── Global rate-limit cooldown ───
# When yfinance returns 429, all yfinance calls skip for this duration
# to let the rate-limit window clear.
# Thread-safe via _rate_limit_lock (briefing mode runs parallel workers).
_RATE_LIMITED_UNTIL = 0.0
_RATE_LIMIT_COOLDOWN = 45  # seconds
_rate_limit_lock = threading.Lock()

# Separate cooldown for DuckDuckGo (known to return 202/captcha under load)
_DDGS_RATE_LIMITED_UNTIL = 0.0
_DDGS_COOLDOWN = 60  # seconds


def _check_rate_limited():
    """Return True if we're in a global rate-limit cooldown.
    Resets automatically after COOLDOWN seconds. Thread-safe."""
    with _rate_limit_lock:
        return time.time() < _RATE_LIMITED_UNTIL


def _mark_rate_limited():
    """Set global cooldown. All yfinance calls skip for COOLDOWN seconds.
    Thread-safe — overlapping calls just extend the window slightly."""
    global _RATE_LIMITED_UNTIL
    with _rate_limit_lock:
        _RATE_LIMITED_UNTIL = time.time() + _RATE_LIMIT_COOLDOWN


def _mark_ddgs_rate_limited():
    """Set DDGS cooldown. Skips DuckDuckGo fallback for _DDGS_COOLDOWN seconds."""
    global _DDGS_RATE_LIMITED_UNTIL
    _DDGS_RATE_LIMITED_UNTIL = time.time() + _DDGS_COOLDOWN


# ─── yfinance: set browser User-Agent to avoid 429 rate limiting ───
_session = requests.Session()
_session.headers["User-Agent"] = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/125.0.0.0 Safari/537.36"
)
yf.utils._session = _session
# Some yfinance versions read from a module-level session
yf._session = _session

# ─── NSE Tickers ───
NSE_TICKERS = {
    "AARTIDRUGS": "Aarti Drugs",
    "AARTIIND": "Aarti Industries",
    "AARTIPHARM": "Aarti Pharmalabs",
    "ABB": "ABB India",
    "ABFRL": "Aditya Birla Fashion",
    "ACC": "ACC Ltd",
    "ADANIENT": "Adani Enterprises",
    "ADANIGREEN": "Adani Green Energy",
    "ADANIPORTS": "Adani Ports",
    "ADANIPOWER": "Adani Power",
    "ADANITRANS": "Adani Energy Solutions",
    "AJANTPHARM": "Ajanta Pharma",
    "ALKEM": "Alkem Laboratories",
    "AMARAJABAT": "Amararaja Batteries",
    "AMBUJACEM": "Ambuja Cements",
    "APOLLOHOSP": "Apollo Hospitals",
    "APOLLOTYRE": "Apollo Tyres",
    "ASIANPAINT": "Asian Paints",
    "ASTRAL": "Astral Ltd",
    "AUBANK": "AU Small Finance Bank",
    "AUROPHARMA": "Aurobindo Pharma",
    "AXISBANK": "Axis Bank",
    "BAJAJ-AUTO": "Bajaj Auto",
    "BAJAJFINSV": "Bajaj Finserv",
    "BAJFINANCE": "Bajaj Finance",
    "BALKRISIND": "Balkrishna Industries",
    "BANDHANBNK": "Bandhan Bank",
    "BANKBARODA": "Bank of Baroda",
    "BATAINDIA": "Bata India",
    "BEL": "Bharat Electronics",
    "BERGEPAINT": "Berger Paints",
    "BHARATFORG": "Bharat Forge",
    "BHARTIARTL": "Bharti Airtel",
    "BHEL": "BHEL",
    "BIOCON": "Biocon Ltd",
    "BLUEDART": "Blue Dart Express",
    "BLUESTARCO": "Blue Star",
    "BOSCHLTD": "Bosch India",
    "BPCL": "Bharat Petroleum",
    "BRITANNIA": "Britannia Industries",
    "BSOFT": "Birlasoft",
    "CADILAHC": "Cadila Healthcare",
    "CANBK": "Canara Bank",
    "CENTRALBK": "Central Bank of India",
    "CESC": "CESC Ltd",
    "CHOLAFIN": "Cholamandalam Investment",
    "CIPLA": "Cipla",
    "COALINDIA": "Coal India",
    "COCHINSHIP": "Cochin Shipyard",
    "COFORGE": "Coforge",
    "COLPAL": "Colgate Palmolive",
    "CONCOR": "Container Corp of India",
    "COROMANDEL": "Coromandel International",
    "CRISIL": "CRISIL Ltd",
    "CROMPTON": "Crompton Greaves",
    "CUB": "City Union Bank",
    "CYIENT": "Cyient",
    "DABUR": "Dabur India",
    "DEEPAKNTR": "Deepak Nitrite",
    "DIVISLAB": "Divi's Laboratories",
    "DIXON": "Dixon Technologies",
    "DLF": "DLF Ltd",
    "DMART": "Avenue Supermarts",
    "DRREDDY": "Dr. Reddy's Labs",
    "EICHERMOT": "Eicher Motors",
    "EMAMILTD": "Emami Ltd",
    "ENDURANCE": "Endurance Technologies",
    "ENERGY": "Mirae Asset Energy ETF",
    "EQUITASBNK": "Equitas Small Finance Bank",
    "ESCORTS": "Escorts Kubota",
    "EXIDEIND": "Exide Industries",
    "FEDERALBNK": "Federal Bank",
    "FINPIPE": "Supreme Petrochem",
    "FORTIS": "Fortis Healthcare",
    "GAIL": "GAIL India",
    "GLAXO": "GlaxoSmithKline Pharma",
    "GLENMARK": "Glenmark Pharma",
    "GODREJAGRO": "Godrej Agrovet",
    "GODREJCP": "Godrej Consumer Products",
    "GODREJIND": "Godrej Industries",
    "GODREJPROP": "Godrej Properties",
    "GOLDBEES": "Nippon India ETF Gold BeES",
    "GRANULES": "Granules India",
    "GRASIM": "Grasim Industries",
    "GROWW": "Groww Asset Management",
    "GSFC": "Gujarat State Fertilizers",
    "GUJGASLTD": "Gujarat Gas",
    "HAL": "Hindustan Aeronautics",
    "HAVELLS": "Havells India",
    "HCLTECH": "HCL Technologies",
    "HDFCAMC": "HDFC Asset Management",
    "HDFCBANK": "HDFC Bank",
    "HDFCLIFE": "HDFC Life Insurance",
    "HEROMOTOCO": "Hero MotoCorp",
    "HEXAWARE": "Hexaware Technologies",
    "HINDALCO": "Hindalco Industries",
    "HINDPETRO": "Hindustan Petroleum",
    "HINDUNILVR": "Hindustan Unilever",
    "HINDZINC": "Hindustan Zinc",
    "HUDCO": "HUDCO",
    "ICICIBANK": "ICICI Bank",
    "ICICIGI": "ICICI Lombard General Insurance",
    "ICICIPRULI": "ICICI Prudential Life",
    "IDBI": "IDBI Bank",
    "IDEA": "Vodafone Idea",
    "IDFCFIRSTB": "IDFC First Bank",
    "IEX": "Indian Energy Exchange",
    "IGL": "Indraprastha Gas",
    "IIFL": "IIFL Finance",
    "INDIANB": "Indian Bank",
    "INDIGO": "InterGlobe Aviation",
    "INDUSINDBK": "IndusInd Bank",
    "INFY": "Infosys",
    "INOXWIND": "Inox Wind",
    "INTELLECT": "Intellect Design Arena",
    "IOC": "Indian Oil Corp",
    "IPCALAB": "IPCA Laboratories",
    "IRCON": "Ircon International",
    "IRCTC": "IRCTC",
    "IRFC": "IRFC",
    "ITC": "ITC Ltd",
    "J&KBANK": "Jammu & Kashmir Bank",
    "JINDALSTEL": "Jindal Steel & Power",
    "JKCEMENT": "JK Cement",
    "JKLAKSHMI": "JK Lakshmi Cement",
    "JSL": "Jindal Stainless",
    "JSWENERGY": "JSW Energy",
    "JSWSTEEL": "JSW Steel",
    "JUBLFOOD": "Jubilant FoodWorks",
    "KANSAINER": "Kansai Nerolac Paints",
    "KARURVYSYA": "Karur Vysya Bank",
    "KEC": "KEC International",
    "KELLTONTEC": "Kellton Tech",
    "KIRLOSENG": "Kirloskar Oil Engines",
    "KOTAKBANK": "Kotak Mahindra Bank",
    "KPITTECH": "KPIT Technologies",
    "L&TFH": "L&T Finance Holdings",
    "LAURUSLABS": "Laurus Labs",
    "LICHSGFIN": "LIC Housing Finance",
    "LICI": "LIC India",
    "LT": "Larsen & Toubro",
    "LTIM": "LTIMindtree",
    "LTTS": "L&T Technology Services",
    "LUPIN": "Lupin Ltd",
    "M&M": "Mahindra & Mahindra",
    "MAHABANK": "Bank of Maharashtra",
    "MAKEINDIA": "Mirae Asset Manufacturing ETF",
    "MANAPPURAM": "Manappuram Finance",
    "MARICO": "Marico Ltd",
    "MARUTI": "Maruti Suzuki",
    "MAXHEALTH": "Max Healthcare",
    "MAZDOCK": "Mazagon Dock",
    "MCDOWELL-N": "United Spirits",
    "MCX": "MCX",
    "METALETF": "Mirae Asset Metal ETF",
    "METROBRAND": "Metro Brands",
    "MFSL": "Max Financial Services",
    "MGL": "Mahanagar Gas",
    "MIDCAPETF": "Nippon India ETF Midcap 150",
    "MINDACORP": "Minda Corporation",
    "MINDTREE": "Mindtree",
    "MODEFENCE": "Mirae Asset Defence ETF",
    "MOIL": "MOIL Ltd",
    "MOTHERSON": "Motherson Sumi",
    "MPHASIS": "Mphasis",
    "MRF": "MRF Tyres",
    "MUTHOOTFIN": "Muthoot Finance",
    "NATCOPHARM": "Natco Pharma",
    "NATIONALUM": "National Aluminium",
    "NAVINFLUOR": "Navin Fluorine",
    "NBCC": "NBCC India",
    "NCC": "NCC Ltd",
    "NESTLEIND": "Nestlé India",
    "NEXT50IETF": "Nippon India ETF Junior BeES",
    "NHPC": "NHPC Ltd",
    "NIFTYBEES": "Nippon India ETF Nifty 50",
    "NMDC": "NMDC Ltd",
    "NTPC": "NTPC Ltd",
    "OBEROIRLTY": "Oberoi Realty",
    "ONGC": "Oil & Natural Gas Corp",
    "PAGEIND": "Page Industries",
    "PERSISTENT": "Persistent Systems",
    "PFC": "Power Finance Corp",
    "PFIZER": "Pfizer India",
    "PHOENIXLTD": "Phoenix Mills",
    "PIDILITIND": "Pidilite Industries",
    "PIIND": "PI Industries",
    "PNB": "Punjab National Bank",
    "PNBHOUSING": "PNB Housing Finance",
    "POLYCAB": "Polycab India",
    "POWERGRID": "Power Grid Corp",
    "PRAJIND": "Praj Industries",
    "PRESTIGE": "Prestige Estates",
    "PTC": "PTC India",
    "PVRINOX": "PVR INOX",
    "PWL": "PW Lakshmi AI & Tech Fund",
    "QUESS": "Quess Corp",
    "RADICO": "Radico Khaitan",
    "RAILTEL": "Railtel Corp",
    "RALLIS": "Rallis India",
    "RAMCOCEM": "Ramco Cements",
    "RATNAMANI": "Ratnamani Metals",
    "RAYMOND": "Raymond Ltd",
    "RBLBANK": "RBL Bank",
    "RCF": "Rashtriya Chemicals",
    "RECLTD": "REC Ltd",
    "RELIANCE": "Reliance Industries",
    "RITES": "RITES Ltd",
    "RVNL": "RVNL",
    "SAIL": "Steel Authority of India",
    "SANOFI": "Sanofi India",
    "SBILIFE": "SBI Life Insurance",
    "SBIN": "State Bank of India",
    "SCHAEFFLER": "Schaeffler India",
    "SHILPAMED": "Shilpa Medicare",
    "SHREECEM": "Shree Cement",
    "SIEMENS": "Siemens India",
    "SKFINDIA": "SKF India",
    "SOBHA": "Sobha Ltd",
    "SOLARINDS": "Solar Industries",
    "SONACOMS": "Sona BLW Precision",
    "SOUTHBANK": "South Indian Bank",
    "SRF": "SRF Ltd",
    "SRTRANSFIN": "Shriram Transport Finance",
    "STARCEMENT": "Star Cement",
    "STLTECH": "Sterlite Technologies",
    "SUNPHARMA": "Sun Pharmaceutical",
    "SUPREMEIND": "Supreme Industries",
    "SUZLON": "Suzlon Energy",
    "SYMPHONY": "Symphony Ltd",
    "SYNGENE": "Syngene International",
    "TATACHEM": "Tata Chemicals",
    "TATACOMM": "Tata Communications",
    "TATACONSUM": "Tata Consumer",
    "TATAELXSI": "Tata Elxsi",
    "TATAMOTORS": "Tata Motors",
    "TATAPOWER": "Tata Power",
    "TATASTEEL": "Tata Steel",
    "TCI": "Transport Corp of India",
    "TCIEXP": "TCI Express",
    "TCS": "Tata Consultancy Services",
    "TEAMLEASE": "TeamLease Services",
    "TECHM": "Tech Mahindra",
    "THERMAX": "Thermax Ltd",
    "TIMKEN": "Timken India",
    "TITAN": "Titan Company",
    "TORNTPHARM": "Torrent Pharmaceuticals",
    "TORNTPOWER": "Torrent Power",
    "TRENT": "Trent Ltd",
    "TRIDENT": "Trident Ltd",
    "TV18BRDCST": "TV18 Broadcast",
    "TVSMOTOR": "TVS Motor Company",
    "UBL": "United Breweries",
    "UCOBANK": "UCO Bank",
    "ULTRACEMCO": "UltraTech Cement",
    "UNIONBANK": "Union Bank of India",
    "UPL": "UPL Ltd",
    "UTIAMC": "UTI Asset Management",
    "VBL": "Varun Beverages",
    "VEDL": "Vedanta Ltd",
    "VMART": "V-Mart Retail",
    "VOLTAS": "Voltas Ltd",
    "VRLLOG": "VRL Logistics",
    "WELCORP": "Welspun Corp",
    "WESTLIFE": "Westlife Foodworld",
    "WIPRO": "Wipro Ltd",
    "YESBANK": "Yes Bank",
    "ZEEL": "Zee Entertainment",
    "ZENSARTECH": "Zensar Technologies",
    "ZOMATO": "Zomato Ltd",
    "ZYDUSLIFE": "Zydus Lifesciences",
}

# ─── Company name aliases for RSS headline matching ───
# Maps common names/abbreviations → ticker symbols.
# RSS headlines rarely use official company names ("SBI" not "State Bank of India").
ALIASES = {
    "HCL TECH": "HCLTECH", "HCL TECHNOLOGIES": "HCLTECH", "HDFC": "HDFCBANK",
    "SBI": "SBIN", "STATE BANK": "SBIN", "HUL": "HINDUNILVR",
    "HINDUSTAN UNILEVER": "HINDUNILVR", "L&T": "LT", "LARSEN": "LT",
    "NESTLE": "NESTLEIND", "DMART": "DMART", "HERO": "HEROMOTOCO",
    "HERO HONDA": "HEROMOTOCO", "DIVIS": "DIVISLAB", "DIVI": "DIVISLAB",
    "JSW STEEL": "JSWSTEEL", "TATA MOTORS": "TATAMOTORS",
    "TATA STEEL": "TATASTEEL", "TATA CONSUMER": "TATACONSUM",
    "BHARTI": "BHARTIARTL", "AIRTEL": "BHARTIARTL", "MARUTI SUZUKI": "MARUTI",
    "TECH MAHINDRA": "TECHM", "INDUSIND": "INDUSINDBK",
    "POWER GRID": "POWERGRID", "COAL INDIA": "COALINDIA",
    "HIND UNILEVER": "HINDUNILVR", "SUN PHARMA": "SUNPHARMA",
    "DR REDDY": "DRREDDY", "DR. REDDY": "DRREDDY",
    "BAJAJ FINANCE": "BAJFINANCE", "ADANI ENTERPRISES": "ADANIENT",
    "ADANI PORTS": "ADANIPORTS", "ADANI GREEN": "ADANIGREEN",
    "ADANI POWER": "ADANIPOWER", "ADANI TRANS": "ADANITRANS",
    "ULTRATECH": "ULTRACEMCO", "ASIAN PAINTS": "ASIANPAINT",
    "APOLLO HOSPITALS": "APOLLOHOSP", "APOLLO": "APOLLOHOSP",
    "TORRENT PHARMA": "TORNTPHARM", "JUBILANT": "JUBLFOOD",
    "TVS": "TVSMOTOR", "VARUN BEVERAGES": "VBL", "YES BANK": "YESBANK",
    "BANK OF BARODA": "BANKBARODA", "MAHINDRA": "M&M",
    "INDIAN OIL": "IOC", "BHARAT PETROLEUM": "BPCL",
    "HINDUSTAN AERONAUTICS": "HAL", "BHARAT ELECTRONICS": "BEL",
    "POWER FINANCE": "PFC", "SOLAR INDUSTRIES": "SOLARINDS",
    "BALKRISHNA": "BALKRISIND", "PW LAKSHMI": "PWL", "VEDANTA": "VEDL",
    "REC": "RECLTD", "Pidilite": "PIDILITIND", "HAVELLS": "HAVELLS",
    "SIEMENS": "SIEMENS", "POLYCAB": "POLYCAB", "DIXON": "DIXON",
    "ASTRAL": "ASTRAL", "IDFC": "IDFCFIRSTB", "EICHER": "EICHERMOT",
    "MARICO": "MARICO", "DABUR": "DABUR", "GODREJ": "GODREJCP",
    "CIPLA": "CIPLA", "LUPIN": "LUPIN", "BIOCON": "BIOCON",
    # ── Banking ──
    "HDFC BANK": "HDFCBANK", "HDFC LTD": "HDFCBANK", "HDFC LIMITED": "HDFCBANK", "HDFC CORP": "HDFCBANK",
    "ICICI": "ICICIBANK", "ICICI BANK": "ICICIBANK", "KOTAK": "KOTAKBANK",
    "KOTAK MAHINDRA": "KOTAKBANK", "AXIS": "AXISBANK", "INDUSIND BANK": "INDUSINDBK",
    "BANK OF INDIA": "BANKINDIA", "CANARA": "CANBK", "CANARA BANK": "CANBK",
    "PUNJAB NATIONAL": "PNB", "UNION BANK": "UNIONBANK",
    "ALLAHABAD BANK": "INDIANB", "INDIAN BANK": "INDIANB",
    "MAHARASHTRA BANK": "MAHABANK", "BANK OF MAHARASHTRA": "MAHABANK",
    "FEDERAL": "FEDERALBNK", "FEDERAL BANK": "FEDERALBNK",
    "SOUTH INDIAN BANK": "SOUTHBANK", "RBL": "RBLBANK",
    "BANDHAN": "BANDHANBNK", "BANDHAN BANK": "BANDHANBNK",
    "AU BANK": "AUBANK", "AU SMALL FINANCE": "AUBANK",
    "CITY UNION": "CUB", "KARUR": "KARURVYSYA", "KARUR VYSYA": "KARURVYSYA",
    "IDBI": "IDBI", "JAMMU KASHMIR BANK": "J&KBANK", "J AND K BANK": "J&KBANK",
    "UCO": "UCOBANK", "EQUITAS": "EQUITASBNK", "EQUITAS BANK": "EQUITASBNK",
    "CENTRAL BANK": "CENTRALBK", "KARNATAKA BANK": "KTKBANK",
    "DCB BANK": "DCBBANK", "DHANLAXMI BANK": "DHANBANK",
    "SBI CARD": "SBICARD", "IOB": "IOB", "INDIAN OVERSEAS BANK": "IOB",
    "PSB": "PSB", "PUNJAB SIND": "PSB",
    # ── Financial Services ──
    "BAJAJ FINSERV": "BAJAJFINSV", "SBI LIFE": "SBILIFE", "SBI LIFE INSURANCE": "SBILIFE",
    "HDFC LIFE": "HDFCLIFE", "HDFC LIFE INSURANCE": "HDFCLIFE",
    "ICICI PRUDENTIAL": "ICICIPRULI", "ICICI LOMBARD": "ICICIGI", "ICICI GENERAL": "ICICIGI",
    "HDFC AMC": "HDFCAMC", "HDFC ASSET MANAGEMENT": "HDFCAMC", "UTI AMC": "UTIAMC",
    "SHRIRAM TRANSPORT": "SRTRANSFIN", "SHRIRAM FINANCE": "SRTRANSFIN",
    "CHOLA": "CHOLAFIN", "CHOLAMANDALAM": "CHOLAFIN",
    "MUTHOOT": "MUTHOOTFIN", "MUTHOOT FINANCE": "MUTHOOTFIN",
    "MANAPPURAM": "MANAPPURAM", "PNB HOUSING": "PNBHOUSING",
    "L AND T FINANCE": "L&TFH", "LT FINANCE": "L&TFH",
    "LIC HOUSING": "LICHSGFIN", "MAX LIFE": "MFSL", "MAX FINANCIAL": "MFSL",
    "STAR HEALTH": "STARHEALTH", "STAR HEALTH INSURANCE": "STARHEALTH",
    "NEW INDIA ASSURANCE": "NIACL",
    # ── IT ──
    "HCL": "HCLTECH", "INFOSYS": "INFY", "TATA CONSULTANCY": "TCS",
    "WIPRO": "WIPRO", "LTI": "LTIM", "LTI MIND TREE": "LTIM", "LTIMINDTREE": "LTIM",
    "MIND TREE": "MINDTREE", "COFORGE": "COFORGE", "PERSISTENT": "PERSISTENT",
    "PERSISTENT SYSTEMS": "PERSISTENT", "MPHASIS": "MPHASIS",
    "BIRLASOFT": "BSOFT", "KPIT": "KPITTECH", "K PIT TECH": "KPITTECH",
    "LT TECHNOLOGY": "LTTS", "L&T TECHNOLOGY": "LTTS", "TATA ELXSI": "TATAELXSI",
    "ZENSAR": "ZENSARTECH", "HEXAWARE": "HEXAWARE", "CYIENT": "CYIENT",
    "INTELLECT DESIGN": "INTELLECT", "TATA COMMUNICATIONS": "TATACOMM",
    "VODAFONE IDEA": "IDEA", "BHARTI": "BHARTIARTL",
    "SONATA": "SONATSOFTW", "SONATA SOFTWARE": "SONATSOFTW",
    "NIIT TECH": "NIITTECH", "ORACLE FIN": "OFSS", "ORACLE FINANCIAL": "OFSS",
    "TECHM": "TECHM",
    # ── Pharma ──
    "SUN PHARMA": "SUNPHARMA", "DR REDDYS": "DRREDDY", "DR REDDY": "DRREDDY",
    "DIVIS": "DIVISLAB", "DIVI LAB": "DIVISLAB", "AUROBINDO": "AUROPHARMA",
    "AUROBINDO PHARMA": "AUROPHARMA", "CADILA": "CADILAHC",
    "ZYDUS": "ZYDUSLIFE", "ZYDUS LIFESCIENCES": "ZYDUSLIFE",
    "ALKEM": "ALKEM", "ALKEM LABS": "ALKEM", "GLENMARK": "GLENMARK",
    "NATCO": "NATCOPHARM", "NATCO PHARMA": "NATCOPHARM",
    "LAURUS": "LAURUSLABS", "LAURUS LABS": "LAURUSLABS",
    "IPCA": "IPCALAB", "GRANULES": "GRANULES", "GRANULES INDIA": "GRANULES",
    "AJANTA": "AJANTPHARM", "AJANTA PHARMA": "AJANTPHARM",
    "SHILPA": "SHILPAMED", "SHILPA MEDICARE": "SHILPAMED",
    "FORTIS HEALTHCARE": "FORTIS", "MAX HEALTHCARE": "MAXHEALTH",
    "MAX HOSPITAL": "MAXHEALTH", "APOLLO HOSPITAL": "APOLLOHOSP",
    "GLAXO": "GLAXO", "GLAXOSMITHKLINE": "GLAXO", "GLAXO INDIA": "GLAXO",
    "SANOFI": "SANOFI", "SANOFI INDIA": "SANOFI", "PFIZER": "PFIZER",
    "ABBOTT": "ABBOTINDIA", "ABBOTT INDIA": "ABBOTINDIA",
    "SYNGENE": "SYNGENE", "ASTER DM": "ASTERDM",
    "J B CHEMICALS": "JBCHEPHARM", "JB CHEMICALS": "JBCHEPHARM",
    "JYOTHY LABS": "JYOTHYLAB", "JYOTHY LABORATORIES": "JYOTHYLAB",
    "HALDIRAM": "HALDIRAM", "HALDIRAM FOOD": "HALDIRAM",
    "HERITAGE FOODS": "HERITGEFOOD",
    # ── Auto ──
    "TATA MOTOR": "TATAMOTORS", "MAHINDRA AND MAHINDRA": "M&M",
    "M AND M": "M&M", "MAHINDRA AUTO": "M&M",
    "BAJAJ AUTO": "BAJAJ-AUTO", "EICHER": "EICHERMOT",
    "HERO MOTOCORP": "HEROMOTOCO", "TVS MOTOR": "TVSMOTOR",
    "APOLLO TYRE": "APOLLOTYRE", "APOLLO TYRES": "APOLLOTYRE",
    "MRF TYRES": "MRF", "MRF": "MRF", "BOSCH": "BOSCHLTD",
    "BHARAT FORGE": "BHARATFORG", "EXIDE": "EXIDEIND",
    "EXIDE INDUSTRIES": "EXIDEIND", "AMARAJA": "AMARAJABAT",
    "AMAR RAJA": "AMARAJABAT", "AMARAJABAT": "AMARAJABAT",
    "SONA BLW": "SONACOMS", "MOTHERSON": "MOTHERSON",
    "MOTHERSUMI": "MOTHERSON", "MOTHER SUMI": "MOTHERSON",
    "SAMVARDHANA MOTHERSON": "MOTHERSON",
    "ESCORTS": "ESCORTS", "ESCORTS KUBOTA": "ESCORTS",
    "ENDURANCE TECH": "ENDURANCE",
    "BALKRISHNA INDUSTRIES": "BALKRISIND",
    # ── FMCG ──
    "HUL": "HINDUNILVR", "HIND UNILEVER": "HINDUNILVR",
    "NESTLE": "NESTLEIND", "BRITANNIA": "BRITANNIA",
    "DABUR INDIA": "DABUR", "GODREJ CONSUMER": "GODREJCP",
    "COLGATE": "COLPAL", "COLPAL": "COLPAL", "EMAMI": "EMAMILTD",
    "BATA": "BATAINDIA", "BATA INDIA": "BATAINDIA",
    "PAGE INDUSTRIES": "PAGEIND", "ADITYA BIRLA FASHION": "ABFRL",
    "ABFRL": "ABFRL", "PANTALOONS": "ABFRL",
    "METRO BRAND": "METROBRAND", "VMART": "VMART", "V MART": "VMART",
    "WESTLIFE": "WESTLIFE", "WESTLIFE FOOD": "WESTLIFE",
    "UNITED SPIRITS": "MCDOWELL-N", "MCDOWELL": "MCDOWELL-N",
    "UNITED BREWERIES": "UBL", "RADICO": "RADICO", "RADICO KHAITAN": "RADICO",
    "TRENT": "TRENT", "ZOMATO": "ZOMATO",
    "AVENUE SUPERMARTS": "DMART",
    "TATA TEA": "TATACONSUM", "TATA COFFEE": "TATACONSUM",
    "JUBILANT FOOD": "JUBLFOOD",
    "KRBL": "KRBL", "KRBL LTD": "KRBL",
    "MOTHER DAIRY": "MOTHERDAIRY",
    "CAMPUS": "CAMPUS", "CAMPUS ACTIVEWEAR": "CAMPUS",
    "SHOPPER STOP": "SHOPERSTOP", "SHOPPERS STOP": "SHOPERSTOP",
    "TATA CHEMICALS": "TATACHEM",
    # ── Energy ──
    "OIL AND NATURAL GAS": "ONGC", "INDIAN OIL": "IOC",
    "HINDUSTAN PETROLEUM": "HINDPETRO", "HPCL": "HINDPETRO",
    "GAIL": "GAIL", "GUJARAT GAS": "GUJGASLTD",
    "IGL": "IGL", "INDRAPRASTHA GAS": "IGL",
    "MAHANAGAR GAS": "MGL", "MGL GAS": "MGL",
    "POWER GRID": "POWERGRID", "COAL INDIA": "COALINDIA",
    "JSW ENERGY": "JSWENERGY", "TORRENT POWER": "TORNTPOWER",
    "SUZLON": "SUZLON", "SUZLON ENERGY": "SUZLON", "INOX WIND": "INOXWIND",
    "ADANI TOTAL GAS": "ATGL", "ADANI GAS": "ATGL",
    "PETRONET": "PETRONET", "PETRONET LNG": "PETRONET",
    "OIL INDIA": "OIL", "OIL INDIA LTD": "OIL",
    # ── Metals ──
    "JINDAL STEEL": "JINDALSTEL", "JINDAL": "JINDALSTEL",
    "STEEL AUTHORITY": "SAIL", "NATIONAL ALUMINIUM": "NATIONALUM",
    "NALCO": "NATIONALUM", "HINDUSTAN ZINC": "HINDZINC",
    "RATNAMANI": "RATNAMANI", "RATNAMANI METAL": "RATNAMANI",
    "WELSPUN": "WELCORP", "WELSPUN CORP": "WELCORP",
    "JINDAL STAINLESS": "JSL", "JSL": "JSL",
    "MAHARASHTRA SEAMLESS": "MAHSEAMLES", "MAHINDRA METAL": "MAHSEAMLES",
    "APL APOLLO": "APLAPOLLO", "APL APOLLO TUBES": "APLAPOLLO",
    # ── Cement & Construction ──
    "ULTRA TECH": "ULTRACEMCO", "AMBUJA": "AMBUJACEM", "AMBUJA CEMENT": "AMBUJACEM",
    "SHREE CEMENT": "SHREECEM", "RAMCO CEMENT": "RAMCOCEM",
    "JK CEMENT": "JKCEMENT", "JK LAKSHMI": "JKLAKSHMI", "JK LAKSHMI CEMENT": "JKLAKSHMI",
    "STAR CEMENT": "STARCEMENT", "BERGER": "BERGEPAINT", "BERGER PAINTS": "BERGEPAINT",
    "KANSAI": "KANSAINER", "NEROLAC": "KANSAINER",
    "SUPREME INDUSTRIES": "SUPREMEIND",
    "ASTRAL PIPES": "ASTRAL",
    "HEIDELBERG": "HEIDELBERG", "HEIDELBERG CEMENT": "HEIDELBERG",
    "DALMIA BHARAT": "DALBHARAT", "DALMIA CEMENT": "DALBHARAT",
    # ── Capital Goods ──
    "BHARAT HEAVY": "BHEL", "BHEL": "BHEL",
    "KIRLOSKAR OIL": "KIRLOSENG", "BLUE STAR": "BLUESTARCO",
    "CROMPTON GREAVES": "CROMPTON", "PRAJ": "PRAJIND", "PRAJ INDUSTRIES": "PRAJIND",
    "KEC INTERNATIONAL": "KEC", "SKF": "SKFINDIA", "CUMMINS": "CUMMINSIND",
    "CARBORUNDUM": "CARBORUNIV", "CARBORUNDUM UNIVERSAL": "CARBORUNIV",
    "GRAPHITE INDIA": "GRAPHITE",
    # ── Chemicals ──
    "PIDILITE": "PIDILITIND", "SRF": "SRF", "DEEPAK NITRITE": "DEEPAKNTR",
    "NAVIN FLUORINE": "NAVINFLUOR", "AARTI": "AARTIIND", "AARTI INDUSTRIES": "AARTIIND",
    "AARTI DRUGS": "AARTIDRUGS", "AARTI PHARMA": "AARTIPHARM",
    "PI INDUSTRIES": "PIIND", "GUJARAT STATE FERT": "GSFC", "GSFC": "GSFC",
    "UPL": "UPL", "RALLIS": "RALLIS", "RCF": "RCF", "RASHTRIYA CHEMICAL": "RCF",
    "COROMANDEL": "COROMANDEL", "COROMANDEL INTERNATIONAL": "COROMANDEL",
    "GUJARAT STATE PETRO": "GSPL", "GUJARAT ALKALIES": "GUJALKALI",
    "GUJARAT FLUORO": "GUJFLUORO", "GUJARAT FLUOROCHEMICALS": "GUJFLUORO",
    # ── Infrastructure ──
    "LARSEN AND TOUBRO": "LT", "L AND T": "LT", "LARSEN": "LT", "L&T": "LT",
    "OBEROI": "OBEROIRLTY", "OBEROI REALTY": "OBEROIRLTY",
    "GODREJ PROPERTIES": "GODREJPROP", "GODREJ PROPERTY": "GODREJPROP",
    "PRESTIGE ESTATES": "PRESTIGE", "SOBHA": "SOBHA", "SOBHA LTD": "SOBHA",
    "PHOENIX MILLS": "PHOENIXLTD", "CONTAINER CORP": "CONCOR", "CONCOR": "CONCOR",
    "RAIL VIKAS": "RVNL", "INDIAN RAILWAYS FINANCE": "IRFC",
    "INDIAN RAILWAY CATERING": "IRCTC", "L AND T FINANCE": "L&TFH",
    "MAHINDRA LIFESPACE": "MAHLIFE", "MAHINDRA LIFESPACES": "MAHLIFE",
    "SUNTECK": "SUNTECK", "SUNTEK REALTY": "SUNTECK",
    "SIGNATURE GLOBAL": "SIGNATURE", "BRIGADE": "BRIGADE", "BRIGADE ENTERPRISES": "BRIGADE",
    "PNC INFRA": "PNCINFRA", "PNC INFRASTRUCTURE": "PNCINFRA",
    "ASHOKA BUILD": "ASHOKA", "ASHOKA BUILDCON": "ASHOKA",
    "JMC PROJECTS": "JMC", "HG INFRA": "HGINFRA",
    "MAZAGON": "MAZDOCK", "MAZAGON DOCK": "MAZDOCK",
    "COCHIN SHIP": "COCHINSHIP", "COCHIN SHIPYARD": "COCHINSHIP",
    "GARDEN REACH": "GRSE", "SHIP BUILDING": "GRSE",
    # ── Media & Telecom ──
    "ZEE": "ZEEL", "ZEE ENTERTAINMENT": "ZEEL", "PVR": "PVRINOX", "PVR INOX": "PVRINOX",
    "TV18": "TV18BRDCST", "STERLITE TECH": "STLTECH",
    "SUN TV": "SUNTV", "SUN TV NETWORK": "SUNTV",
    "NETWORK 18": "NETWORK18", "NETWORK18": "NETWORK18",
    "HMVL": "HMVL", "HT MEDIA": "HTMEDIA",
    # ── Logistics ──
    "TRANSPORT CORP": "TCI", "TCI": "TCI", "TCI EXPRESS": "TCIEXP",
    "VRL LOGISTICS": "VRLLOG", "BLUE DART": "BLUEDART",
    "ALL CARGO": "ALLCARGO", "ALLCARGO": "ALLCARGO",
    "MAHINDRA LOGISTIC": "MAHLOG", "MAHINDRA LOGISTICS": "MAHLOG",
    "DELHIVERY": "DELHIVERY", "DELIVERY": "ZOMATO",
    # ── Textiles ──
    "TRIDENT": "TRIDENT", "TRIDENT LTD": "TRIDENT",
    "VARDHMAN": "VARDHMAN", "VARDHMAN TEXTILES": "VARDHMAN",
    "ALOK INDUSTRIES": "ALOKINDS", "CENTURY TEXTILE": "CENTURYTEX", "CENTURY": "CENTURYTEX",
    # ── Godrej Group ──
    "GODREJ INDUSTRIES": "GODREJIND", "GODREJ AGROVET": "GODREJAGRO",
    # ── Other ──
    "CRISIL": "CRISIL", "MCX": "MCX", "MULTI COMMODITY": "MCX",
    "MFSL": "MFSL", "SCHAEFFLER": "SCHAEFFLER", "MINDACORP": "MINDACORP",
    "SYMPHONY": "SYMPHONY", "QUESS": "QUESS", "TEAMLEASE": "TEAMLEASE",
    "LT FOODS": "LTFOODS", "LT OVERSEAS": "LTFOODS",
    "BEML": "BEML", "BEML LTD": "BEML",
    # ── ETFs ──
    "NIFTY BEES": "NIFTYBEES", "GOLD BEES": "GOLDBEES", "JUNIOR BEES": "NEXT50IETF",
    "NEXT 50": "NEXT50IETF", "MIDCAP 150": "MIDCAPETF", "MID CAP ETF": "MIDCAPETF",
    "DEFENCE ETF": "MODEFENCE", "MANUFACTURING ETF": "MAKEINDIA",
    "ENERGY ETF": "ENERGY", "METAL ETF": "METALETF",
    "LAKSHMI AI": "PWL", "GROWW": "GROWW",
}

# ponytail: in-memory 1y price history cache, populated by get_stock_info,
# consumed by get_technical_indicators to avoid duplicate yfinance calls
_hist_cache = {}


def get_cached_history(ticker):
    """Return the in-memory cached 1y price history for a ticker, if available.

    Populated by get_stock_info() to share the yfinance 1y OHLCV fetch with
    get_technical_indicators() and compute_pivot_levels() — avoids duplicate
    API calls that increase rate-limit exposure.
    """
    return _hist_cache.get(ticker)


def _strip_html(text):
    """Strip HTML tags + unescape entities for clean text analysis & display."""
    if not text:
        return ""
    text = re.sub(r"<[^>]+>", " ", text)
    text = html.unescape(text)
    return " ".join(text.split())


def get_stock_info(ticker):
    """Fetch stock data from yfinance with retry and backoff.

    Two-phase approach:
      1. info (metadata: name, sector, PE, 52w) — best-effort, not blocking.
         If it fails, defaults are used.
      2. history (price data: close, change, volume) — required.
         Falls back to .BO suffix if .NS fails, then bare ticker.
    """
    cached = cache_get(f"stock_{ticker}")
    if cached:
        return cached

    # Global rate-limit cooldown — if yfinance recently 429'd us, skip early
    if _check_rate_limited():
        st.warning(
            f"Yahoo Finance rate-limited. Waiting {_RATE_LIMIT_COOLDOWN}s "
            "before retrying. Try again shortly."
        )
        return None

    def _retry_fetch(max_attempts=3, base_wait=1, backoff=2):
        """Generator that yields (attempt_num, wait_seconds) for retry loops.
        Uses exponential backoff with full jitter (AWS retry style).
        If _check_rate_limited() is True, skips sleep and yields immediately.
        """
        for attempt in range(max_attempts):
            yield attempt
            if attempt < max_attempts - 1:
                # If we're in a global cooldown, skip the sleep and try again
                if _check_rate_limited():
                    continue
                sleep = base_wait * (backoff ** attempt)
                jitter = sleep * 0.5 * random.random()
                time.sleep(sleep + jitter)

    suffixes = [".NS", ".BO", ""]
    info = None
    hist = None
    name_fallback = ticker

    try:
        # ── Phase 1: info (best-effort metadata) ──
        for suffix in suffixes:
            stock = yf.Ticker(f"{ticker}{suffix}")
            for attempt in _retry_fetch(max_attempts=3, base_wait=1):
                try:
                    raw = stock.info
                    if raw and isinstance(raw, dict) and len(raw) > 10:
                        info = raw
                        name_fallback = info.get("longName", info.get("shortName", ticker))
                        break
                except Exception as e:
                    # ponytail: any yfinance error could be rate-limiting
                    if "429" in str(e) or "Too Many" in str(e) or "Rate Limit" in str(e):
                        _mark_rate_limited()
                    continue  # retry same suffix with backoff before trying next
            if info:
                break  # found valid info, stop trying suffixes

        # ── Phase 2: history (required price data) ──
        for suffix in suffixes if not hist else []:
            stock = yf.Ticker(f"{ticker}{suffix}")
            for attempt in _retry_fetch(max_attempts=3, base_wait=2):
                try:
                    raw = stock.history(period="1y")
                    if raw is not None and not raw.empty:
                        hist = raw
                        break
                except Exception:
                    continue  # retry with backoff
            if hist is not None:
                break  # found valid history

        # ── Phase 2b: retry info if it failed (rate-limit may have cleared
        #    during the history phase which took ~3-6s) ──
        if info is None and hist is not None:
            for suffix in suffixes:
                stock = yf.Ticker(f"{ticker}{suffix}")
                try:
                    raw = stock.info
                    if raw and isinstance(raw, dict) and len(raw) > 10:
                        info = raw
                        name_fallback = info.get("longName", info.get("shortName", ticker))
                        break
                except Exception:
                    continue

        # ── Build result dict ──
        # ponytail: _nf = NaN-safe float extractor — returns None for NaN/None
        def _nf(v):
            if v is None:
                return None
            f = float(v)
            return None if math.isnan(f) else f

        if hist is not None and not hist.empty:
            _hist_cache[ticker] = hist
            current_price = _nf(hist["Close"].iloc[-1])
            prev_close = _nf(hist["Close"].iloc[-2]) if len(hist) > 1 else current_price
            if current_price is not None and prev_close is not None:
                change = float(current_price - prev_close)
                change_pct = float((change / prev_close) * 100) if prev_close != 0 else 0.0
            else:
                change = None
                change_pct = None
            day_high = _nf(hist["High"].iloc[-1])
            day_low = _nf(hist["Low"].iloc[-1])
            vol_raw = hist["Volume"].iloc[-1]
            volume = int(vol_raw) if not math.isnan(vol_raw) else 0
        elif info:
            # No history but info is available — use info fields for price
            current_price = _nf(info.get("currentPrice")) or _nf(info.get("regularMarketPrice"))
            change = _nf(info.get("regularMarketChange"))
            change_pct = _nf(info.get("regularMarketChangePercent"))
            day_high = _nf(info.get("dayHigh"))
            day_low = _nf(info.get("dayLow"))
            vol_raw = info.get("volume")
            volume = int(vol_raw) if vol_raw is not None and not math.isnan(float(vol_raw)) else 0
        else:
            # Neither info nor history — give up
            st.error(
                f"Could not fetch data for {ticker}. "
                "Yahoo Finance may be rate-limited — wait a moment and try again."
            )
            return None

        result = {
            "name": info.get("longName", info.get("shortName", name_fallback)) if info else name_fallback,
            "sector": info.get("sector", "N/A") if info else "N/A",
            "industry": info.get("industry", "N/A") if info else "N/A",
            "market_cap": info.get("marketCap") if info else None,
            "pe_ratio": info.get("trailingPE") if info else None,
            "current_price": current_price,
            "change": change,
            "change_pct": change_pct,
            "day_high": day_high,
            "day_low": day_low,
            "volume": volume,
            "52w_high": info.get("fiftyTwoWeekHigh") if info else None,
            "52w_low": info.get("fiftyTwoWeekLow") if info else None,
        }
        if info:
            cache_set(f"stock_{ticker}", result)
        else:
            cache_set(f"stock_{ticker}", result, ttl=120)  # 2 min
        return result

    except Exception as e:
        st.error(f"Could not fetch data for {ticker}: {e}")
        return None


def _parse_date(d):
    """Parse RSS date tuple to ISO date string."""
    try:
        return datetime(*d[:6]).isoformat()[:10]
    except Exception:
        return ""


def _alias_terms(ticker):
    """Get additional search terms from ALIASES dict for a ticker.

    E.g., for ticker='SBIN', returns {'sbi', 'state', 'bank'}
    since ALIASES has 'SBI' -> 'SBIN' and 'STATE BANK' -> 'SBIN'.
    """
    terms = set()
    for alias_key, alias_ticker in ALIASES.items():
        if alias_ticker == ticker:
            terms.update(alias_key.lower().split())
    return terms


def _relevant(ticker, company_name, title, body):
    """Check if a headline is relevant to the given ticker/company.

    Searches ticker name, company name, AND known aliases.
    """
    text = (title + " " + (body or "")).lower()
    words = set(ticker.lower().split()) | set(company_name.lower().split())
    words.update(_alias_terms(ticker))
    return any(re.search(r'\b' + re.escape(w) + r'\b', text) for w in words if len(w) > 2)


# ─── RSS Feeds ───
# Yahoo Finance RSS removed (returns 429 / rate-limited on cloud IPs)
# LiveMint and Business Standard tested; BS returns 403

TICKER_RSS_FEEDS = [
    # Google News RSS for ticker-specific results
    lambda t, c: f"https://news.google.com/rss/search?q={t}+NSE+stock&hl=en-IN&gl=IN&ceid=IN:en",
    lambda t, c: f"https://news.google.com/rss/search?q={c}+NSE&hl=en-IN&gl=IN&ceid=IN:en" if c != t else None,
]

INDIA_RSS_FEEDS = [
    ("Moneycontrol Buzzing", "https://www.moneycontrol.com/rss/buzzingstocks.xml"),
    ("Moneycontrol News", "https://www.moneycontrol.com/rss/latestnews.xml"),
    ("Moneycontrol Reports", "https://www.moneycontrol.com/rss/marketreports.xml"),
    ("Economic Times Markets", "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"),
    ("Economic Times Company", "https://economictimes.indiatimes.com/news/company/rssfeeds/2143429.cms"),
    ("LiveMint Markets", "https://www.livemint.com/rss/markets"),
    ("NDTV Profit", "https://feeds.feedburner.com/ndtvprofit-latest"),
]

SOURCE_LABELS = {
    "google news": "Google News",
    "moneycontrol buzzing": "Moneycontrol",
    "moneycontrol news": "Moneycontrol",
    "moneycontrol reports": "Moneycontrol",
    "economic times markets": "Economic Times",
    "economic times company": "Economic Times",
    "livemint markets": "LiveMint",
    "ndtv profit": "NDTV Profit",
    "duckduckgo": "DuckDuckGo",
}



def search_news(ticker, company_name, max_results=10):
    """Fetch news from RSS feeds (primary), fallback to DuckDuckGo.
    Returns (articles, source_health) where source_health tracks which sources returned results.
    """
    cached = cache_get(f"news_{ticker}")
    if cached:
        news, health = cached
        return news[:max_results], health

    seen_urls = set()
    all_results = []
    source_stats = {}  # source_name -> hit_count

    # Ticker-specific RSS feeds
    for rss_fn in TICKER_RSS_FEEDS:
        url = rss_fn(ticker, company_name)
        if url is None:
            continue
        try:
            feed = feedparser.parse(url, timeout=10)
            for entry in feed.entries[:5]:
                link = entry.get("link", "")
                if link and link not in seen_urls:
                    seen_urls.add(link)
                    all_results.append({
                        "title": entry.get("title", ""),
                        "body": _strip_html(entry.get("summary", "")),
                        "date": _parse_date(entry.get("published_parsed")),
                        "url": link,
                        "source": "Google News",
                    })
                    source_stats["Google News"] = source_stats.get("Google News", 0) + 1
        except Exception:
            continue

    # Indian market RSS feeds (filtered by relevance) — fetched concurrently
    def _parse_rss_feed(source_name, url):
        """Parse one RSS feed in a worker thread — no shared state mutation."""
        label = SOURCE_LABELS.get(source_name.lower().replace("_", " "), source_name)
        items = []
        try:
            feed = feedparser.parse(url, timeout=10)
            for entry in feed.entries[:7]:
                link = entry.get("link", "")
                title = entry.get("title", "")
                body = _strip_html(entry.get("summary", ""))
                if link and _relevant(ticker, company_name, title, body):
                    items.append({
                        "title": title,
                        "body": body,
                        "date": _parse_date(entry.get("published_parsed")),
                        "url": link,
                        "source": label,
                    })
        except Exception:
            pass
        return items, label

    with ThreadPoolExecutor(max_workers=5) as pool:
        futures = {pool.submit(_parse_rss_feed, name, url): name for name, url in INDIA_RSS_FEEDS}
        for future in as_completed(futures):
            items, label = future.result()
            for item in items:
                link = item["url"]
                if link not in seen_urls:
                    seen_urls.add(link)
                    all_results.append(item)
                    source_stats[label] = source_stats.get(label, 0) + 1

    # Fallback: DuckDuckGo when RSS returns little — skip if DDGS rate-limited
    if len(all_results) < 3 and time.time() >= _DDGS_RATE_LIMITED_UNTIL:
        try:
            with DDGS() as ddgs:
                for query in [f"{ticker} NSE", f"{company_name} stock"]:
                    try:
                        results = list(ddgs.news(query, max_results=3, timelimit="w"))
                    except Exception:
                        results = []
                    if not results:
                        try:
                            results = list(ddgs.text(query, max_results=3))
                        except Exception:
                            results = []
                    for r in results:
                        url = r.get("url", "") or r.get("link", "")
                        if url and url not in seen_urls:
                            seen_urls.add(url)
                            all_results.append({
                                "title": r.get("title", ""),
                                "body": r.get("body", ""),
                                "date": r.get("date", ""),
                                "url": url,
                                "source": "DuckDuckGo",
                            })
                            source_stats["DuckDuckGo"] = source_stats.get("DuckDuckGo", 0) + 1
                    time.sleep(0.3)
                    if len(all_results) >= max_results:
                        break
        except Exception:
            _mark_ddgs_rate_limited()

    all_results.sort(key=lambda x: x["date"], reverse=True)
    if all_results:
        cache_set(f"news_{ticker}", (all_results, source_stats))
    if not all_results:
        st.info("ℹ️ News feed unavailable. Showing price data only.")
    return all_results[:max_results], source_stats
