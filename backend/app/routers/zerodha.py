"""
Zerodha Integration Router
==========================
Kite Connect OAuth login URL + CSV holdings upload.
Both return parsed holdings as JSON — the frontend writes them to Supabase.
"""
import os
import io
import pandas as pd
from fastapi import APIRouter, HTTPException, UploadFile, File
from fastapi.responses import RedirectResponse

try:
    from kiteconnect import KiteConnect
except ImportError:
    KiteConnect = None

KITE_API_KEY = os.getenv("KITE_API_KEY")
KITE_API_SECRET = os.getenv("KITE_API_SECRET")
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

router = APIRouter(tags=["zerodha"])


def _get_kite():
    if not KITE_API_KEY or not KiteConnect:
        raise HTTPException(status_code=500, detail="Kite Connect API is not configured on the server.")
    return KiteConnect(api_key=KITE_API_KEY)


@router.get("/api/zerodha/login")
async def get_kite_login_url():
    """Return the Zerodha login URL."""
    kite = _get_kite()
    return {"url": kite.login_url()}


@router.get("/callback")
async def kite_callback(request_token: str | None = None, error: str | None = None):
    """
    Handle the Zerodha callback. Exchange token, fetch holdings, and redirect
    to the frontend with the holdings as a base64-encoded JSON query param.
    The frontend is responsible for writing to Supabase.
    """
    if error:
        return RedirectResponse(f"{FRONTEND_URL}/?nav=portfolio&error={error}")
    if not request_token:
        return RedirectResponse(f"{FRONTEND_URL}/?nav=portfolio&error=No+request+token")

    try:
        import json, base64
        kite = _get_kite()
        data = kite.generate_session(request_token, api_secret=KITE_API_SECRET)
        kite.set_access_token(data["access_token"])
        holdings = kite.holdings()

        positions = []
        for item in holdings:
            qty = item.get("quantity", 0)
            if qty <= 0:
                continue
            positions.append({
                "ticker": item.get("tradingsymbol", "").upper(),
                "quantity": float(qty),
                "buy_price": float(item.get("average_price", 0.0)),
            })

        payload = base64.urlsafe_b64encode(json.dumps(positions).encode()).decode()
        return RedirectResponse(f"{FRONTEND_URL}/?nav=portfolio&zerodha_import={payload}")
    except Exception as e:
        print(f"Kite connect error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/?nav=portfolio&error=Zerodha+integration+failed")


@router.post("/api/zerodha/upload-csv")
async def upload_holdings_csv(file: UploadFile = File(...)):
    """Parse a Zerodha CSV and return holdings as JSON for the frontend to save."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")

    try:
        contents = await file.read()
        try:
            df = pd.read_csv(io.BytesIO(contents))
        except Exception:
            raise HTTPException(status_code=400, detail="Could not parse CSV file.")

        if df.empty:
            raise HTTPException(status_code=400, detail="CSV is empty.")

        col_map = {c.strip().lower(): c for c in df.columns}
        instrument_col = col_map.get("instrument", col_map.get("symbol", col_map.get("tradingsymbol")))
        qty_col = col_map.get("qty.", col_map.get("quantity", col_map.get("qty")))
        price_col = col_map.get("avg. cost", col_map.get("average_price", col_map.get("buy_price")))

        if not (instrument_col and qty_col and price_col):
            raise HTTPException(status_code=400, detail="Missing columns. Expected: Instrument, Qty., Avg. cost.")

        positions = []
        for _, row in df.iterrows():
            ticker = str(row[instrument_col]).strip().upper()
            qty = pd.to_numeric(row[qty_col], errors="coerce")
            price = pd.to_numeric(row[price_col], errors="coerce")
            if pd.isna(qty) or pd.isna(price) or qty <= 0:
                continue
            positions.append({"ticker": ticker, "quantity": float(qty), "buy_price": float(price)})

        return {"message": f"Parsed {len(positions)} positions", "positions": positions}

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to process CSV: {str(e)}")
