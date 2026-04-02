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
    {"ticker": "LTIM", "yf_symbol": "LTIM.NS", "name": "LTIMindtree Ltd", "sector": "IT"},
    {"ticker": "PERSISTENT", "yf_symbol": "PERSISTENT.NS", "name": "Persistent Systems", "sector": "IT"},
    {"ticker": "COFORGE", "yf_symbol": "COFORGE.NS", "name": "Coforge Ltd", "sector": "IT"},
    {"ticker": "MPHASIS", "yf_symbol": "MPHASIS.NS", "name": "Mphasis Ltd", "sector": "IT"},

    # Automobiles
    {"ticker": "TATAMOTORS", "yf_symbol": "TATAMOTORS.NS", "name": "Tata Motors Ltd", "sector": "Automobiles"},
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
    {"ticker": "HBLPOWER", "yf_symbol": "HBLPOWER.NS", "name": "HBL Engineering Ltd", "sector": "Capital Goods"},

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
    {"ticker": "ZOMATO", "yf_symbol": "ZOMATO.NS", "name": "Zomato Ltd", "sector": "Internet"},
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
    {"ticker": "SPICEJET", "yf_symbol": "SPICEJET.NS", "name": "SpiceJet Ltd", "sector": "Aviation"},
    {"ticker": "JIOFIN", "yf_symbol": "JIOFIN.NS", "name": "Jio Financial Services", "sector": "Finance"},
    {"ticker": "SBICARD", "yf_symbol": "SBICARD.NS", "name": "SBI Cards & Payment", "sector": "Finance"},
    {"ticker": "CHOLAFIN", "yf_symbol": "CHOLAFIN.NS", "name": "Cholamandalam Finance", "sector": "Finance"},
    {"ticker": "MUTHOOTFIN", "yf_symbol": "MUTHOOTFIN.NS", "name": "Muthoot Finance", "sector": "Finance"},
    {"ticker": "MANAPPURAM", "yf_symbol": "MANAPPURAM.NS", "name": "Manappuram Finance", "sector": "Finance"},
]

# Build lookup maps
TICKER_TO_YF = {s["ticker"]: s["yf_symbol"] for s in NSE_STOCKS}
TICKER_TO_META = {s["ticker"]: {"name": s["name"], "sector": s["sector"]} for s in NSE_STOCKS}

# All unique sectors for filtering
ALL_SECTORS = sorted(set(s["sector"] for s in NSE_STOCKS))


def search_stocks(query: str, sector: str | None = None, limit: int = 50) -> list[dict]:
    """
    Search the NSE stock universe by ticker or company name.
    Optionally filter by sector.
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
    
    return results[:limit]
