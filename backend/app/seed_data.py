"""
Seed Data Module
================
Pre-populated stock data for the MVP. In production, this would be replaced
by real-time feeds from BSE/NSE APIs or data vendors like Refinitiv/Bloomberg.

Tickers: REC, RVNL, HBLENGR, TATAMOTORS-TMCV, TATAMOTORS-TMPV
"""

import random
from datetime import date, timedelta

# ---------------------------------------------------------------------------
# Stock Metadata
# ---------------------------------------------------------------------------

STOCKS = {
    "REC": {
        "name": "REC Limited",
        "sector": "Power & Infrastructure Finance",
        "current_price": 511.35,
        "change_percent": 2.14,
        "market_cap_cr": 134500,
    },
    "RVNL": {
        "name": "Rail Vikas Nigam Ltd",
        "sector": "Infrastructure - Railways",
        "current_price": 267.80,
        "change_percent": -1.32,
        "market_cap_cr": 55800,
    },
    "HBLENGR": {
        "name": "HBL Engineering Ltd",
        "sector": "Capital Goods - Electronics",
        "current_price": 578.45,
        "change_percent": 3.67,
        "market_cap_cr": 16200,
    },
    "TATAMOTORS-TMCV": {
        "name": "Tata Motors - Commercial Vehicles",
        "sector": "Automobiles - CV",
        "current_price": 742.90,
        "change_percent": 0.85,
        "market_cap_cr": 274000,
    },
    "TATAMOTORS-TMPV": {
        "name": "Tata Motors - Passenger Vehicles",
        "sector": "Automobiles - PV & EV",
        "current_price": 698.15,
        "change_percent": -0.47,
        "market_cap_cr": 258000,
    },
}


# ---------------------------------------------------------------------------
# Price History Generator (deterministic per ticker)
# ---------------------------------------------------------------------------

def _generate_price_history(
    base_price: float, volatility: float, days: int, seed: int
) -> list[dict]:
    """Generate realistic-looking OHLCV data for `days` trading days."""
    rng = random.Random(seed)
    history = []
    price = base_price * 0.92  # start ~8% below current for an uptrend feel
    start_date = date(2026, 2, 5)  # ~30 trading days before Mar 17

    for i in range(days):
        d = start_date + timedelta(days=i)
        # Skip weekends
        if d.weekday() >= 5:
            continue

        change = rng.gauss(0.001, volatility)
        open_p = round(price, 2)
        close_p = round(price * (1 + change), 2)
        high_p = round(max(open_p, close_p) * (1 + rng.uniform(0, volatility)), 2)
        low_p = round(min(open_p, close_p) * (1 - rng.uniform(0, volatility)), 2)
        volume = rng.randint(800_000, 12_000_000)

        history.append({
            "date": d.isoformat(),
            "open": open_p,
            "high": high_p,
            "low": low_p,
            "close": close_p,
            "volume": volume,
        })
        price = close_p

    return history


PRICE_HISTORIES = {
    "REC": _generate_price_history(511.35, 0.018, 42, seed=101),
    "RVNL": _generate_price_history(267.80, 0.025, 42, seed=202),
    "HBLENGR": _generate_price_history(578.45, 0.022, 42, seed=303),
    "TATAMOTORS-TMCV": _generate_price_history(742.90, 0.015, 42, seed=404),
    "TATAMOTORS-TMPV": _generate_price_history(698.15, 0.020, 42, seed=505),
}


# ---------------------------------------------------------------------------
# Mock News Corpus (simulates vector-store retrieval results)
# ---------------------------------------------------------------------------

NEWS_CORPUS = {
    "REC": [
        {
            "source": "Economic Times",
            "headline": "REC Ltd secures ₹15,000 Cr green energy financing mandate",
            "snippet": "REC Limited has been awarded a massive green energy financing mandate worth ₹15,000 crore to fund solar and wind projects across Rajasthan and Gujarat. The move aligns with India's 2030 renewable energy targets and positions REC as a key financier in the energy transition.",
            "relevance_score": 0.94,
            "published_date": "2026-03-15",
        },
        {
            "source": "Mint",
            "headline": "Power sector NBFCs rally as RBI holds rates steady",
            "snippet": "Power-sector focused NBFCs including REC and PFC saw buying interest after the RBI's monetary policy committee kept the repo rate unchanged at 6.25%. Analysts note that stable rates benefit infrastructure lenders with large loan books.",
            "relevance_score": 0.89,
            "published_date": "2026-03-14",
        },
        {
            "source": "Reuters",
            "headline": "India's infrastructure capex on track despite global slowdown",
            "snippet": "Despite global recession fears, India's infrastructure capital expenditure remains robust at ₹11.1 lakh crore for FY26. Government-backed entities like REC and IRFC continue to see strong disbursement growth.",
            "relevance_score": 0.82,
            "published_date": "2026-03-12",
        },
        {
            "source": "Bloomberg Quint",
            "headline": "FII flows into Indian power financiers hit 6-month high",
            "snippet": "Foreign institutional investors have increased their holdings in Indian power financing companies, with REC seeing the highest net inflows among peers. The trend reflects growing global confidence in India's energy infrastructure story.",
            "relevance_score": 0.78,
            "published_date": "2026-03-10",
        },
        {
            "source": "CNBC-TV18",
            "headline": "Union Budget 2026 allocates record ₹2.5L Cr for green energy",
            "snippet": "The Union Budget has allocated a record ₹2.5 lakh crore for green energy initiatives, directly benefiting REC's pipeline of renewable energy project financing. Management expects loan growth of 18-20% in FY27.",
            "relevance_score": 0.75,
            "published_date": "2026-03-08",
        },
    ],
    "RVNL": [
        {
            "source": "Economic Times",
            "headline": "RVNL bags ₹3,200 Cr railway electrification contract",
            "snippet": "Rail Vikas Nigam Ltd has secured a ₹3,200 crore contract for railway electrification across the Northern and Eastern corridors. This is RVNL's largest single contract win in FY26, boosting its order book to over ₹72,000 crore.",
            "relevance_score": 0.96,
            "published_date": "2026-03-16",
        },
        {
            "source": "Mint",
            "headline": "Railway capex sees 22% YoY jump in Q3 FY26",
            "snippet": "Indian Railways' capital expenditure jumped 22% year-on-year in Q3 FY26, driven by electrification and new line construction. RVNL, as a key execution partner, is expected to see accelerated revenue recognition in Q4.",
            "relevance_score": 0.91,
            "published_date": "2026-03-14",
        },
        {
            "source": "Business Standard",
            "headline": "Vande Bharat expansion creates ₹50,000 Cr opportunity for rail PSUs",
            "snippet": "The government's plan to deploy 400 Vande Bharat trains by 2027 is creating a massive order pipeline for rail PSUs. RVNL is positioned to capture track-laying and station modernization contracts worth ₹8,000-10,000 crore.",
            "relevance_score": 0.87,
            "published_date": "2026-03-11",
        },
        {
            "source": "Reuters",
            "headline": "India's rail freight corridor nears completion, boosting infra stocks",
            "snippet": "The dedicated freight corridor project is 94% complete, with commissioning expected by mid-2026. Rail infrastructure companies including RVNL and IRCON are seeing renewed investor interest on the back of this development.",
            "relevance_score": 0.83,
            "published_date": "2026-03-09",
        },
        {
            "source": "CNBC-TV18",
            "headline": "Defence corridor rail connectivity project awarded to RVNL",
            "snippet": "RVNL has been selected to develop rail connectivity for two of India's defence industrial corridors in UP and Tamil Nadu. The project, valued at ₹1,800 crore, further diversifies RVNL's order book beyond conventional railway projects.",
            "relevance_score": 0.79,
            "published_date": "2026-03-07",
        },
    ],
    "HBLENGR": [
        {
            "source": "Economic Times",
            "headline": "HBL Engineering wins ₹950 Cr defence electronics order",
            "snippet": "HBL Engineering has secured a ₹950 crore order from the Indian Defence Ministry for specialized battery systems and railway electronics. The order reinforces HBL's position as a niche defence electronics supplier.",
            "relevance_score": 0.93,
            "published_date": "2026-03-15",
        },
        {
            "source": "Mint",
            "headline": "Railway signalling upgrade creates opportunities for HBL, Medha",
            "snippet": "Indian Railways' ₹12,000 crore signalling upgrade program under the Kavach initiative is creating significant opportunities for companies like HBL Engineering and Medha Servo Drives. HBL's railway electronics division is expected to see 35% revenue growth.",
            "relevance_score": 0.88,
            "published_date": "2026-03-13",
        },
        {
            "source": "Business Standard",
            "headline": "Small-cap capital goods stocks rally on order book visibility",
            "snippet": "Small and mid-cap capital goods companies with strong order books rallied in today's session. HBL Engineering, with an order book of ₹4,200 crore (3x revenue), was among the top gainers in the segment.",
            "relevance_score": 0.84,
            "published_date": "2026-03-11",
        },
        {
            "source": "CNBC-TV18",
            "headline": "Make in India push boosts domestic electronics manufacturers",
            "snippet": "The government's revised electronics manufacturing policy is expected to benefit domestic players like HBL Engineering, BEL, and Data Patterns. Import substitution in defence electronics alone could add ₹500 crore to HBL's annual addressable market.",
            "relevance_score": 0.80,
            "published_date": "2026-03-08",
        },
        {
            "source": "Moneycontrol",
            "headline": "HBL Engineering Q3 results beat estimates, margins expand 200bps",
            "snippet": "HBL Engineering reported Q3 FY26 revenue of ₹420 crore (+28% YoY) with EBITDA margins expanding 200 basis points to 14.2%. Management guided for continued margin improvement driven by a favorable product mix.",
            "relevance_score": 0.76,
            "published_date": "2026-03-05",
        },
    ],
    "TATAMOTORS-TMCV": [
        {
            "source": "Economic Times",
            "headline": "Tata Motors CV division posts 15% volume growth in February",
            "snippet": "Tata Motors' commercial vehicle division reported 15% year-on-year volume growth in February 2026, driven by strong demand in the M&HCV (Medium & Heavy Commercial Vehicle) segment. Fleet replacement and infrastructure activity are key demand drivers.",
            "relevance_score": 0.95,
            "published_date": "2026-03-16",
        },
        {
            "source": "Mint",
            "headline": "Infrastructure boom drives CV demand to 5-year high",
            "snippet": "Commercial vehicle demand in India has hit a 5-year high, fueled by the infrastructure construction boom and last-mile logistics growth. Tata Motors maintains a 44% market share in the M&HCV segment.",
            "relevance_score": 0.90,
            "published_date": "2026-03-14",
        },
        {
            "source": "Reuters",
            "headline": "BS-VII emission norms deadline may trigger pre-buying in CV sector",
            "snippet": "With BS-VII emission norms expected to be announced for 2028, analysts anticipate a pre-buying cycle in the commercial vehicle segment starting late 2026. Tata Motors and Ashok Leyland are expected to be primary beneficiaries.",
            "relevance_score": 0.85,
            "published_date": "2026-03-12",
        },
        {
            "source": "Business Standard",
            "headline": "Tata Motors launches hydrogen fuel cell truck prototype",
            "snippet": "Tata Motors unveiled its hydrogen fuel cell truck prototype at the Auto Expo, signaling its commitment to zero-emission commercial vehicles. The company plans to begin fleet trials by Q2 FY27.",
            "relevance_score": 0.81,
            "published_date": "2026-03-09",
        },
        {
            "source": "CNBC-TV18",
            "headline": "GST rate cut on electric trucks proposed in budget session",
            "snippet": "A proposal to reduce GST on electric and alternative-fuel trucks from 28% to 12% is being discussed in Parliament. If approved, it could significantly benefit Tata Motors' electric CV lineup including the Ace EV.",
            "relevance_score": 0.77,
            "published_date": "2026-03-06",
        },
    ],
    "TATAMOTORS-TMPV": [
        {
            "source": "Economic Times",
            "headline": "Tata Motors PV market share crosses 15% on EV and SUV strength",
            "snippet": "Tata Motors' passenger vehicle division has crossed 15% domestic market share for the first time, driven by strong demand for the Nexon, Harrier, and Curvv EVs. The company sold 52,000 units in February 2026.",
            "relevance_score": 0.94,
            "published_date": "2026-03-16",
        },
        {
            "source": "Mint",
            "headline": "EV penetration in India reaches 8% in passenger vehicle segment",
            "snippet": "Electric vehicle penetration in India's passenger vehicle market has reached 8% in February 2026, up from 4.5% a year ago. Tata Motors leads with a 62% EV market share, followed by MG Motor and Mahindra.",
            "relevance_score": 0.91,
            "published_date": "2026-03-15",
        },
        {
            "source": "Bloomberg",
            "headline": "Tata Motors to invest ₹15,000 Cr in EV battery gigafactory",
            "snippet": "Tata Motors, through its subsidiary Agratas Energy, has announced a ₹15,000 crore investment in a lithium-ion battery gigafactory in Gujarat. The facility will supply cells for Tata's EV lineup starting FY28.",
            "relevance_score": 0.88,
            "published_date": "2026-03-13",
        },
        {
            "source": "Business Standard",
            "headline": "SUV segment grows 25% YoY, Tata Curvv leads sales charts",
            "snippet": "The Indian SUV segment grew 25% year-on-year in February, with the Tata Curvv emerging as the best-selling model in the compact SUV category. Pricing strategy and EV variant availability are cited as key differentiators.",
            "relevance_score": 0.84,
            "published_date": "2026-03-11",
        },
        {
            "source": "Reuters",
            "headline": "Global lithium prices crash 60%, reducing EV manufacturing costs",
            "snippet": "Global lithium carbonate prices have dropped 60% from their 2024 peak, significantly reducing battery costs for EV manufacturers. Tata Motors is expected to benefit with improved margins on its EV lineup and potential price cuts to stimulate demand.",
            "relevance_score": 0.80,
            "published_date": "2026-03-08",
        },
    ],
}
