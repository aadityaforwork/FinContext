"""
NSE Stock Universe
==================
Curated list of ~150 popular NSE-listed stocks spanning NIFTY 50,
NIFTY Next 50, and popular mid-caps. Each entry maps an internal
ticker to its Yahoo Finance NSE symbol, company name, and sector.

This serves as the browseable stock database for the Screener page.
In production, this would be stored in PostgreSQL and updated via
a scheduled data ingestion job.
"""

NSE_STOCKS = [
    # === NIFTY 50 === (sorted by sector)
    # Banking & Finance
    {"ticker": "HDFCBANK", "yf_symbol": "HDFCBANK.NS", "name": "HDFC Bank Ltd", "sector": "Banking"},
    {"ticker": "ICICIBANK", "yf_symbol": "ICICIBANK.NS", "name": "ICICI Bank Ltd", "sector": "Banking"},
    {"ticker": "KOTAKBANK", "yf_symbol": "KOTAKBANK.NS", "name": "Kotak Mahindra Bank", "sector": "Banking"},
    {"ticker": "SBIN", "yf_symbol": "SBIN.NS", "name": "State Bank of India", "sector": "Banking"},
    {"ticker": "AXISBANK", "yf_symbol": "AXISBANK.NS", "name": "Axis Bank Ltd", "sector": "Banking"},
    {"ticker": "INDUSINDBK", "yf_symbol": "INDUSINDBK.NS", "name": "IndusInd Bank", "sector": "Banking"},
    {"ticker": "BANKBARODA", "yf_symbol": "BANKBARODA.NS", "name": "Bank of Baroda", "sector": "Banking"},
    {"ticker": "PNB", "yf_symbol": "PNB.NS", "name": "Punjab National Bank", "sector": "Banking"},
    {"ticker": "CANBK", "yf_symbol": "CANBK.NS", "name": "Canara Bank", "sector": "Banking"},
    {"ticker": "IDFCFIRSTB", "yf_symbol": "IDFCFIRSTB.NS", "name": "IDFC First Bank", "sector": "Banking"},
    {"ticker": "BAJFINANCE", "yf_symbol": "BAJFINANCE.NS", "name": "Bajaj Finance Ltd", "sector": "Finance"},
    {"ticker": "BAJAJFINSV", "yf_symbol": "BAJAJFINSV.NS", "name": "Bajaj Finserv Ltd", "sector": "Finance"},
    {"ticker": "HDFCLIFE", "yf_symbol": "HDFCLIFE.NS", "name": "HDFC Life Insurance", "sector": "Insurance"},
    {"ticker": "SBILIFE", "yf_symbol": "SBILIFE.NS", "name": "SBI Life Insurance", "sector": "Insurance"},
    {"ticker": "ICICIPRULI", "yf_symbol": "ICICIPRULI.NS", "name": "ICICI Prudential Life", "sector": "Insurance"},

    # IT & Technology
    {"ticker": "TCS", "yf_symbol": "TCS.NS", "name": "Tata Consultancy Services", "sector": "IT"},
    {"ticker": "INFY", "yf_symbol": "INFY.NS", "name": "Infosys Ltd", "sector": "IT"},
    {"ticker": "HCLTECH", "yf_symbol": "HCLTECH.NS", "name": "HCL Technologies", "sector": "IT"},
    {"ticker": "WIPRO", "yf_symbol": "WIPRO.NS", "name": "Wipro Ltd", "sector": "IT"},
    {"ticker": "TECHM", "yf_symbol": "TECHM.NS", "name": "Tech Mahindra", "sector": "IT"},
    # LTIM — Yahoo Finance currently has no working symbol for LTIMindtree
    # (LTIM.NS / LTIMINDTREE.* / LTI.NS all return KeyError as of May 2026).
    # Symbol kept so the universe stays complete; live price will return None
    # and the UI shows "—" until Yahoo restores coverage.
    {"ticker": "LTIM", "yf_symbol": "LTIM.NS", "name": "LTIMindtree Ltd", "sector": "IT"},
    {"ticker": "PERSISTENT", "yf_symbol": "PERSISTENT.NS", "name": "Persistent Systems", "sector": "IT"},
    {"ticker": "COFORGE", "yf_symbol": "COFORGE.NS", "name": "Coforge Ltd", "sector": "IT"},
    {"ticker": "MPHASIS", "yf_symbol": "MPHASIS.NS", "name": "Mphasis Ltd", "sector": "IT"},

    # Automobiles
    # TATAMOTORS demerged in 2024 into TATAMOTORS-PV (TMPV.NS) and
    # TATAMOTORS-CV (TMCV.NS). The unified TATAMOTORS.NS is gone. We point
    # the legacy ticker at TMPV.NS (passenger vehicles — the larger arm) so
    # users with old positions still see a live price; new positions should
    # use TATAMOTORS-TMCV / TATAMOTORS-TMPV explicitly.
    {"ticker": "TATAMOTORS", "yf_symbol": "TMPV.NS", "name": "Tata Motors PV (post-demerger)", "sector": "Automobiles"},
    {"ticker": "MARUTI", "yf_symbol": "MARUTI.NS", "name": "Maruti Suzuki India", "sector": "Automobiles"},
    {"ticker": "M&M", "yf_symbol": "M&M.NS", "name": "Mahindra & Mahindra", "sector": "Automobiles"},
    {"ticker": "BAJAJ-AUTO", "yf_symbol": "BAJAJ-AUTO.NS", "name": "Bajaj Auto Ltd", "sector": "Automobiles"},
    {"ticker": "HEROMOTOCO", "yf_symbol": "HEROMOTOCO.NS", "name": "Hero MotoCorp Ltd", "sector": "Automobiles"},
    {"ticker": "EICHERMOT", "yf_symbol": "EICHERMOT.NS", "name": "Eicher Motors Ltd", "sector": "Automobiles"},
    {"ticker": "TVSMOTOR", "yf_symbol": "TVSMOTOR.NS", "name": "TVS Motor Company", "sector": "Automobiles"},
    {"ticker": "ASHOKLEY", "yf_symbol": "ASHOKLEY.NS", "name": "Ashok Leyland Ltd", "sector": "Automobiles"},

    # Reliance & Conglomerates
    {"ticker": "RELIANCE", "yf_symbol": "RELIANCE.NS", "name": "Reliance Industries", "sector": "Conglomerate"},
    {"ticker": "ITC", "yf_symbol": "ITC.NS", "name": "ITC Ltd", "sector": "Conglomerate"},
    {"ticker": "ADANIENT", "yf_symbol": "ADANIENT.NS", "name": "Adani Enterprises", "sector": "Conglomerate"},
    {"ticker": "ADANIPORTS", "yf_symbol": "ADANIPORTS.NS", "name": "Adani Ports & SEZ", "sector": "Infrastructure"},
    {"ticker": "ADANIGREEN", "yf_symbol": "ADANIGREEN.NS", "name": "Adani Green Energy", "sector": "Energy"},
    {"ticker": "ADANIPOWER", "yf_symbol": "ADANIPOWER.NS", "name": "Adani Power Ltd", "sector": "Energy"},

    # Energy & Power
    {"ticker": "NTPC", "yf_symbol": "NTPC.NS", "name": "NTPC Ltd", "sector": "Power"},
    {"ticker": "POWERGRID", "yf_symbol": "POWERGRID.NS", "name": "Power Grid Corp", "sector": "Power"},
    {"ticker": "TATAPOWER", "yf_symbol": "TATAPOWER.NS", "name": "Tata Power Company", "sector": "Power"},
    {"ticker": "RECLTD", "yf_symbol": "RECLTD.NS", "name": "REC Limited", "sector": "Power & Finance"},
    {"ticker": "PFC", "yf_symbol": "PFC.NS", "name": "Power Finance Corp", "sector": "Power & Finance"},
    {"ticker": "NHPC", "yf_symbol": "NHPC.NS", "name": "NHPC Ltd", "sector": "Power"},
    {"ticker": "ONGC", "yf_symbol": "ONGC.NS", "name": "Oil & Natural Gas Corp", "sector": "Oil & Gas"},
    {"ticker": "IOC", "yf_symbol": "IOC.NS", "name": "Indian Oil Corporation", "sector": "Oil & Gas"},
    {"ticker": "BPCL", "yf_symbol": "BPCL.NS", "name": "Bharat Petroleum", "sector": "Oil & Gas"},
    {"ticker": "GAIL", "yf_symbol": "GAIL.NS", "name": "GAIL India Ltd", "sector": "Oil & Gas"},
    {"ticker": "COALINDIA", "yf_symbol": "COALINDIA.NS", "name": "Coal India Ltd", "sector": "Mining"},

    # Pharma & Healthcare
    {"ticker": "SUNPHARMA", "yf_symbol": "SUNPHARMA.NS", "name": "Sun Pharmaceutical", "sector": "Pharma"},
    {"ticker": "DRREDDY", "yf_symbol": "DRREDDY.NS", "name": "Dr. Reddy's Labs", "sector": "Pharma"},
    {"ticker": "CIPLA", "yf_symbol": "CIPLA.NS", "name": "Cipla Ltd", "sector": "Pharma"},
    {"ticker": "DIVISLAB", "yf_symbol": "DIVISLAB.NS", "name": "Divi's Laboratories", "sector": "Pharma"},
    {"ticker": "APOLLOHOSP", "yf_symbol": "APOLLOHOSP.NS", "name": "Apollo Hospitals", "sector": "Healthcare"},
    {"ticker": "MAXHEALTH", "yf_symbol": "MAXHEALTH.NS", "name": "Max Healthcare", "sector": "Healthcare"},
    {"ticker": "LALPATHLAB", "yf_symbol": "LALPATHLAB.NS", "name": "Dr Lal PathLabs", "sector": "Healthcare"},
    {"ticker": "BIOCON", "yf_symbol": "BIOCON.NS", "name": "Biocon Ltd", "sector": "Pharma"},
    {"ticker": "AUROPHARMA", "yf_symbol": "AUROPHARMA.NS", "name": "Aurobindo Pharma", "sector": "Pharma"},

    # FMCG & Consumer
    {"ticker": "HINDUNILVR", "yf_symbol": "HINDUNILVR.NS", "name": "Hindustan Unilever", "sector": "FMCG"},
    {"ticker": "NESTLEIND", "yf_symbol": "NESTLEIND.NS", "name": "Nestle India Ltd", "sector": "FMCG"},
    {"ticker": "BRITANNIA", "yf_symbol": "BRITANNIA.NS", "name": "Britannia Industries", "sector": "FMCG"},
    {"ticker": "DABUR", "yf_symbol": "DABUR.NS", "name": "Dabur India Ltd", "sector": "FMCG"},
    {"ticker": "MARICO", "yf_symbol": "MARICO.NS", "name": "Marico Ltd", "sector": "FMCG"},
    {"ticker": "GODREJCP", "yf_symbol": "GODREJCP.NS", "name": "Godrej Consumer Products", "sector": "FMCG"},
    {"ticker": "COLPAL", "yf_symbol": "COLPAL.NS", "name": "Colgate-Palmolive India", "sector": "FMCG"},
    {"ticker": "TATACONSUM", "yf_symbol": "TATACONSUM.NS", "name": "Tata Consumer Products", "sector": "FMCG"},
    {"ticker": "VBL", "yf_symbol": "VBL.NS", "name": "Varun Beverages Ltd", "sector": "FMCG"},
    {"ticker": "DMART", "yf_symbol": "DMART.NS", "name": "Avenue Supermarts (DMart)", "sector": "Retail"},

    # Infrastructure & Capital Goods
    {"ticker": "LT", "yf_symbol": "LT.NS", "name": "Larsen & Toubro", "sector": "Infrastructure"},
    {"ticker": "RVNL", "yf_symbol": "RVNL.NS", "name": "Rail Vikas Nigam Ltd", "sector": "Infrastructure"},
    {"ticker": "IRFC", "yf_symbol": "IRFC.NS", "name": "Indian Railway Finance", "sector": "Infrastructure"},
    {"ticker": "IRCTC", "yf_symbol": "IRCTC.NS", "name": "IRCTC Ltd", "sector": "Infrastructure"},
    {"ticker": "BEL", "yf_symbol": "BEL.NS", "name": "Bharat Electronics", "sector": "Defence"},
    {"ticker": "HAL", "yf_symbol": "HAL.NS", "name": "Hindustan Aeronautics", "sector": "Defence"},
    {"ticker": "BHEL", "yf_symbol": "BHEL.NS", "name": "Bharat Heavy Electricals", "sector": "Capital Goods"},
    {"ticker": "SIEMENS", "yf_symbol": "SIEMENS.NS", "name": "Siemens Ltd", "sector": "Capital Goods"},
    {"ticker": "ABB", "yf_symbol": "ABB.NS", "name": "ABB India Ltd", "sector": "Capital Goods"},
    {"ticker": "CUMMINSIND", "yf_symbol": "CUMMINSIND.NS", "name": "Cummins India Ltd", "sector": "Capital Goods"},
    # HBL Power Systems renamed → HBL Engineering. Yahoo lists it as HBLENGINE.NS.
    {"ticker": "HBLPOWER", "yf_symbol": "HBLENGINE.NS", "name": "HBL Engineering Ltd", "sector": "Capital Goods"},

    # Metals & Mining
    {"ticker": "TATASTEEL", "yf_symbol": "TATASTEEL.NS", "name": "Tata Steel Ltd", "sector": "Metals"},
    {"ticker": "JSWSTEEL", "yf_symbol": "JSWSTEEL.NS", "name": "JSW Steel Ltd", "sector": "Metals"},
    {"ticker": "HINDALCO", "yf_symbol": "HINDALCO.NS", "name": "Hindalco Industries", "sector": "Metals"},
    {"ticker": "VEDL", "yf_symbol": "VEDL.NS", "name": "Vedanta Ltd", "sector": "Metals"},
    {"ticker": "NMDC", "yf_symbol": "NMDC.NS", "name": "NMDC Ltd", "sector": "Mining"},
    {"ticker": "SAIL", "yf_symbol": "SAIL.NS", "name": "Steel Authority of India", "sector": "Metals"},

    # Cement & Building Materials
    {"ticker": "ULTRACEMCO", "yf_symbol": "ULTRACEMCO.NS", "name": "UltraTech Cement", "sector": "Cement"},
    {"ticker": "SHREECEM", "yf_symbol": "SHREECEM.NS", "name": "Shree Cement Ltd", "sector": "Cement"},
    {"ticker": "AMBUJACEM", "yf_symbol": "AMBUJACEM.NS", "name": "Ambuja Cements", "sector": "Cement"},
    {"ticker": "ACC", "yf_symbol": "ACC.NS", "name": "ACC Ltd", "sector": "Cement"},
    {"ticker": "DALBHARAT", "yf_symbol": "DALBHARAT.NS", "name": "Dalmia Bharat Ltd", "sector": "Cement"},
    {"ticker": "GRASIM", "yf_symbol": "GRASIM.NS", "name": "Grasim Industries", "sector": "Cement"},

    # Telecom & Media
    {"ticker": "BHARTIARTL", "yf_symbol": "BHARTIARTL.NS", "name": "Bharti Airtel Ltd", "sector": "Telecom"},
    {"ticker": "IDEA", "yf_symbol": "IDEA.NS", "name": "Vodafone Idea Ltd", "sector": "Telecom"},
    {"ticker": "ZEEL", "yf_symbol": "ZEEL.NS", "name": "Zee Entertainment", "sector": "Media"},

    # Real Estate
    {"ticker": "DLF", "yf_symbol": "DLF.NS", "name": "DLF Ltd", "sector": "Real Estate"},
    {"ticker": "GODREJPROP", "yf_symbol": "GODREJPROP.NS", "name": "Godrej Properties", "sector": "Real Estate"},
    {"ticker": "OBEROIRLTY", "yf_symbol": "OBEROIRLTY.NS", "name": "Oberoi Realty", "sector": "Real Estate"},
    {"ticker": "PRESTIGE", "yf_symbol": "PRESTIGE.NS", "name": "Prestige Estates", "sector": "Real Estate"},
    {"ticker": "BRIGADE", "yf_symbol": "BRIGADE.NS", "name": "Brigade Enterprises", "sector": "Real Estate"},

    # Chemicals
    {"ticker": "PIDILITIND", "yf_symbol": "PIDILITIND.NS", "name": "Pidilite Industries", "sector": "Chemicals"},
    {"ticker": "SRF", "yf_symbol": "SRF.NS", "name": "SRF Ltd", "sector": "Chemicals"},
    {"ticker": "ATUL", "yf_symbol": "ATUL.NS", "name": "Atul Ltd", "sector": "Chemicals"},
    {"ticker": "DEEPAKNTR", "yf_symbol": "DEEPAKNTR.NS", "name": "Deepak Nitrite", "sector": "Chemicals"},

    # Textiles & Apparel
    {"ticker": "PAGEIND", "yf_symbol": "PAGEIND.NS", "name": "Page Industries", "sector": "Textiles"},
    {"ticker": "TRENT", "yf_symbol": "TRENT.NS", "name": "Trent Ltd (Westside/Zudio)", "sector": "Retail"},

    # Fintech & New Age
    {"ticker": "PAYTM", "yf_symbol": "PAYTM.NS", "name": "One97 Communications (Paytm)", "sector": "Fintech"},
    # Zomato rebranded to Eternal in May 2025 — NSE symbol changed to ETERNAL.
    # Keep ZOMATO as the internal ticker (matches user portfolios) but route to
    # the new Yahoo symbol.
    {"ticker": "ZOMATO", "yf_symbol": "ETERNAL.NS", "name": "Eternal Ltd (formerly Zomato)", "sector": "Internet"},
    {"ticker": "NYKAA", "yf_symbol": "NYKAA.NS", "name": "FSN E-Commerce (Nykaa)", "sector": "Internet"},
    {"ticker": "POLICYBZR", "yf_symbol": "POLICYBZR.NS", "name": "PB Fintech (Policybazaar)", "sector": "Fintech"},
    {"ticker": "DELHIVERY", "yf_symbol": "DELHIVERY.NS", "name": "Delhivery Ltd", "sector": "Logistics"},

    # PSU & Others
    {"ticker": "LICI", "yf_symbol": "LICI.NS", "name": "Life Insurance Corp", "sector": "Insurance"},
    {"ticker": "INDIANB", "yf_symbol": "INDIANB.NS", "name": "Indian Bank", "sector": "Banking"},
    {"ticker": "CONCOR", "yf_symbol": "CONCOR.NS", "name": "Container Corp of India", "sector": "Logistics"},
    {"ticker": "TITAN", "yf_symbol": "TITAN.NS", "name": "Titan Company Ltd", "sector": "Consumer"},
    {"ticker": "HAVELLS", "yf_symbol": "HAVELLS.NS", "name": "Havells India Ltd", "sector": "Consumer"},
    {"ticker": "VOLTAS", "yf_symbol": "VOLTAS.NS", "name": "Voltas Ltd", "sector": "Consumer"},
    {"ticker": "ASIANPAINT", "yf_symbol": "ASIANPAINT.NS", "name": "Asian Paints Ltd", "sector": "Consumer"},
    {"ticker": "BERGEPAINT", "yf_symbol": "BERGEPAINT.NS", "name": "Berger Paints India", "sector": "Consumer"},
    {"ticker": "INDIGO", "yf_symbol": "INDIGO.NS", "name": "InterGlobe Aviation", "sector": "Aviation"},
    # Yahoo lost SPICEJET.NS coverage; the BSE listing (SPICEJET.BO) still feeds.
    {"ticker": "SPICEJET", "yf_symbol": "SPICEJET.BO", "name": "SpiceJet Ltd", "sector": "Aviation"},
    {"ticker": "JIOFIN", "yf_symbol": "JIOFIN.NS", "name": "Jio Financial Services", "sector": "Finance"},
    {"ticker": "SBICARD", "yf_symbol": "SBICARD.NS", "name": "SBI Cards & Payment", "sector": "Finance"},
    {"ticker": "CHOLAFIN", "yf_symbol": "CHOLAFIN.NS", "name": "Cholamandalam Finance", "sector": "Finance"},
    {"ticker": "MUTHOOTFIN", "yf_symbol": "MUTHOOTFIN.NS", "name": "Muthoot Finance", "sector": "Finance"},
    {"ticker": "MANAPPURAM", "yf_symbol": "MANAPPURAM.NS", "name": "Manappuram Finance", "sector": "Finance"},

    # Capital markets / depositories
    {"ticker": "BSE",        "yf_symbol": "BSE.NS",        "name": "BSE Ltd",                    "sector": "Capital Markets"},
    {"ticker": "CDSL",       "yf_symbol": "CDSL.NS",       "name": "Central Depository Services","sector": "Capital Markets"},
    {"ticker": "IEX",        "yf_symbol": "IEX.NS",        "name": "Indian Energy Exchange",     "sector": "Capital Markets"},

    # Internet — Eternal (the post-rename Zomato; users hold ETERNAL directly)
    {"ticker": "ETERNAL",    "yf_symbol": "ETERNAL.NS",    "name": "Eternal Ltd (formerly Zomato)", "sector": "Internet"},

    # Tata Motors post-demerger entities — held as their own tickers
    {"ticker": "TMPV",       "yf_symbol": "TMPV.NS",       "name": "Tata Motors Passenger Vehicles", "sector": "Automobiles"},
    {"ticker": "TMCV",       "yf_symbol": "TMCV.NS",       "name": "Tata Motors Commercial Vehicles","sector": "Automobiles"},

    # Auto / EV
    {"ticker": "MOTHERSON",  "yf_symbol": "MOTHERSON.NS",  "name": "Samvardhana Motherson",      "sector": "Automobiles"},
    {"ticker": "OLAELEC",    "yf_symbol": "OLAELEC.NS",    "name": "Ola Electric Mobility",      "sector": "Automobiles"},
    {"ticker": "OLECTRA",    "yf_symbol": "OLECTRA.NS",    "name": "Olectra Greentech",          "sector": "Automobiles"},
    {"ticker": "WHEELS",     "yf_symbol": "WHEELS.NS",     "name": "Wheels India",               "sector": "Automobiles"},

    # Renewables
    {"ticker": "INOXWIND",   "yf_symbol": "INOXWIND.NS",   "name": "Inox Wind",                  "sector": "Power"},
    {"ticker": "SUZLON",     "yf_symbol": "SUZLON.NS",     "name": "Suzlon Energy",              "sector": "Power"},

    # Capital goods / defense / railways
    {"ticker": "MAZDOCK",    "yf_symbol": "MAZDOCK.NS",    "name": "Mazagon Dock Shipbuilders",  "sector": "Capital Goods"},
    {"ticker": "TECHNOE",    "yf_symbol": "TECHNOE.NS",    "name": "Techno Electric & Engineering","sector": "Capital Goods"},
    {"ticker": "TITAGARH",   "yf_symbol": "TITAGARH.NS",   "name": "Titagarh Rail Systems",      "sector": "Capital Goods"},

    # Metals / chemicals
    {"ticker": "HINDZINC",   "yf_symbol": "HINDZINC.NS",   "name": "Hindustan Zinc",             "sector": "Metals & Mining"},
    {"ticker": "UPL",        "yf_symbol": "UPL.NS",        "name": "UPL Ltd",                    "sector": "Pharmaceuticals"},

    # Misc
    {"ticker": "AIIL",       "yf_symbol": "AIIL.NS",       "name": "Authum Investment & Infrastructure", "sector": "Finance"},
]

# Build lookup maps
TICKER_TO_YF = {s["ticker"]: s["yf_symbol"] for s in NSE_STOCKS}
TICKER_TO_META = {s["ticker"]: {"name": s["name"], "sector": s["sector"]} for s in NSE_STOCKS}

# All unique sectors for filtering
ALL_SECTORS = sorted(set(s["sector"] for s in NSE_STOCKS))


def resolve_yf_symbol(ticker: str) -> str | None:
    """Resolve any ticker to a yfinance symbol.

    Strategy:
      1. Curated TICKER_TO_YF map (handles renames/demergers like ZOMATO→ETERNAL)
      2. Fallback: append `.NS` to the uppercased ticker — works for ~95% of
         NSE-listed names that aren't in our curated universe.

    Always returns a string. The caller invokes yfinance and handles the case
    where the symbol returns no data (rate limit, delisted, Yahoo coverage gap).
    Use this everywhere instead of `TICKER_TO_YF.get(ticker)` so users with
    holdings outside the curated 140 still get live prices.
    """
    if not ticker:
        return None
    t = ticker.upper().strip()
    if not t:
        return None
    return TICKER_TO_YF.get(t) or f"{t}.NS"


def search_stocks(query: str, sector: str | None = None, limit: int = 50) -> list[dict]:
    """
    Search the NSE stock universe by ticker or company name.

    Two-tier strategy:
      1. Curated NSE_STOCKS (~143 entries, full sector metadata).
      2. Yahoo Search API fallback — if curated returns nothing, call Yahoo's
         autocomplete endpoint. Does FUZZY matching on both symbol and company
         name, so "waaree" surfaces WAAREEENER.NS (Waaree Energies), "indigo"
         finds INDIGO.NS, etc. Works for any of the ~1,800 NSE-listed equities.

    Sector filter only applies to curated results (search-API path has no
    curated sector data; we use Yahoo's US-NAICS classification as best-effort).
    """
    results = NSE_STOCKS

    if sector:
        results = [s for s in results if s["sector"].lower() == sector.lower()]

    if query:
        q = query.lower()
        results = [
            s for s in results
            if q in s["ticker"].lower() or q in s["name"].lower()
        ]

    # Fallback — fires ONLY when curated came up empty, no sector filter was
    # applied, and the query has enough characters to be meaningful (≥2). Two
    # sub-paths, tried in order: Yahoo Search API (fuzzy name+symbol), then a
    # direct {QUERY}.NS probe (for users who type the exact symbol of a stock
    # Yahoo Search misses, which happens for newly listed names sometimes).
    if not results and not sector and query and len(query.strip()) >= 2:
        results = _yahoo_search_ns(query.strip(), limit=limit) or []
        if not results:
            probe = _probe_yf_ticker(query)
            if probe:
                results = [probe]

    return results[:limit]


# ---------------------------------------------------------------------------
# yfinance probe — resolves uncurated NSE tickers (the ~1,650 stocks we don't
# carry in NSE_STOCKS but ARE listed on NSE). Cached aggressively so search
# autocompletes don't slam Yahoo.
# ---------------------------------------------------------------------------
import re as _re
import logging as _logging
from cachetools import TTLCache as _TTLCache

_probe_log = _logging.getLogger(__name__)

# Hit cache: 6 hours — ticker metadata doesn't change intraday.
_probe_cache: _TTLCache = _TTLCache(maxsize=2000, ttl=6 * 60 * 60)
# Miss cache: 30 min — short enough that a Yahoo blip recovers, long enough that
# typos don't keep paying the network round-trip.
_probe_neg_cache: _TTLCache = _TTLCache(maxsize=2000, ttl=30 * 60)

# Yahoo Search API cache. Key is the lowercased query string. Hit TTL is 1h
# (search results are stable but new listings happen) and miss TTL is short
# so a transient Yahoo hiccup doesn't lock the query out for long.
_search_cache:     _TTLCache = _TTLCache(maxsize=2000, ttl=60 * 60)
_search_neg_cache: _TTLCache = _TTLCache(maxsize=2000, ttl=5 * 60)

_TICKER_PATTERN = _re.compile(r"^[A-Z][A-Z0-9&-]{1,11}$")


def _yahoo_search_ns(query: str, limit: int = 8) -> list[dict]:
    """Yahoo Finance autocomplete API — fuzzy name+symbol search.

    Endpoint: https://query1.finance.yahoo.com/v1/finance/search

    Filters results to `.NS` symbols (NSE-listed) and returns NSE_STOCKS-shape
    dicts. Handles the case the ticker-probe path can't: queries that don't
    match the exact symbol of the stock, like "waaree" → WAAREEENER.NS.

    Cached aggressively so typing autocomplete doesn't slam Yahoo. Returns []
    on any failure; the caller falls back further.
    """
    q = (query or "").strip().lower()
    if not q:
        return []
    if q in _search_cache:
        return _search_cache[q]
    if q in _search_neg_cache:
        return []
    try:
        import requests as _rq
        url = "https://query1.finance.yahoo.com/v1/finance/search"
        params = {
            "q": q,
            "quotesCount": 15,
            "newsCount": 0,
            "enableFuzzyQuery": "true",
        }
        # Yahoo's search rejects bot UAs. Use a browser-realistic one.
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json, text/plain, */*",
        }
        r = _rq.get(url, params=params, headers=headers, timeout=3.0)
        r.raise_for_status()
        payload = r.json() or {}
        quotes = payload.get("quotes") or []

        # Keep only NSE-listed equities. Yahoo tags Indian NSE symbols with the
        # ".NS" suffix and exchange code "NSI"; BSE is ".BO" / "BSE".
        out: list[dict] = []
        for item in quotes:
            symbol = item.get("symbol") or ""
            if not symbol.endswith(".NS"):
                continue
            if (item.get("quoteType") or "").upper() not in ("EQUITY", ""):
                continue
            ticker = symbol[:-3]  # strip the ".NS"
            name = item.get("longname") or item.get("shortname") or ticker
            # Prefer the curated sector if we happen to have one for this ticker.
            curated = TICKER_TO_META.get(ticker)
            sector = (curated or {}).get("sector") or item.get("sector") or "—"
            out.append({
                "ticker":    ticker,
                "yf_symbol": symbol,
                "name":      name,
                "sector":    sector,
            })
            if len(out) >= limit:
                break

        if out:
            _search_cache[q] = out
            return out
        else:
            _search_neg_cache[q] = True
            return []
    except Exception as e:
        _probe_log.debug("yahoo search failed for %s: %s", q, type(e).__name__)
        _search_neg_cache[q] = True
        return []


def _probe_yf_ticker(query: str) -> dict | None:
    """Try `{query.upper()}.NS` on yfinance. Returns NSE_STOCKS-shape dict on
    success, None otherwise. Cached. Sub-second when cached, ~2s on a miss."""
    q = (query or "").upper().strip()
    if not q:
        return None
    # Only attempt for things that look like tickers. Full-name searches
    # ("Reliance Industries") and typos ("infor") are skipped — those are
    # the curated path's job.
    if not _TICKER_PATTERN.match(q):
        return None
    if q in _probe_cache:
        return _probe_cache[q]
    if q in _probe_neg_cache:
        return None
    try:
        # Lazy import — yfinance import is heavy; we don't want module-load
        # cost just to define this function.
        import yfinance as yf
        from app.services import yf_safe

        def _inner():
            t = yf.Ticker(f"{q}.NS")
            info = t.info or {}
            # `longName` / `shortName` indicate Yahoo has the symbol on file.
            # We also require a price OR a market cap to filter out delisted
            # stubs that still return metadata.
            name = info.get("longName") or info.get("shortName")
            has_data = (
                (info.get("regularMarketPrice") is not None and info["regularMarketPrice"] > 0)
                or (info.get("marketCap") is not None)
                or (info.get("trailingPE") is not None)
            )
            if not name or not has_data:
                return None
            return {
                "ticker":    q,
                "yf_symbol": f"{q}.NS",
                "name":      name,
                # Yahoo's `sector` is US-NAICS flavour but better than nothing.
                "sector":    info.get("sector") or "—",
            }

        result, ok = yf_safe.run_with_timeout(_inner, timeout_s=3.0)
        if not ok or result is None:
            _probe_neg_cache[q] = True
            return None
        _probe_cache[q] = result
        return result
    except Exception as e:
        _probe_log.debug("yf probe failed for %s: %s", q, type(e).__name__)
        _probe_neg_cache[q] = True
        return None
