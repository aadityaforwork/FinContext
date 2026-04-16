"""
Zerodha Integration Router
==========================
Endpoints for official Kite Connect OAuth flow and CSV upload.
"""
import os
import io
import pandas as pd
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
from fastapi.responses import RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timezone
try:
    from kiteconnect import KiteConnect
except ImportError:
    KiteConnect = None

from app.db import get_db
from app.db.models import PortfolioPosition, User
from app.core.deps import get_current_user, get_current_user_optional
from app.nse_universe import TICKER_TO_YF

# Load environment variables (they should be loaded in main.py, but we use os.getenv directly)
KITE_API_KEY = os.getenv("KITE_API_KEY")
KITE_API_SECRET = os.getenv("KITE_API_SECRET")

# Base redirect URL (Next.js frontend)
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:3000")

router = APIRouter(tags=["zerodha"])

def _get_kite():
    if not KITE_API_KEY or not KiteConnect:
        raise HTTPException(status_code=500, detail="Kite Connect API is not configured on the server.")
    return KiteConnect(api_key=KITE_API_KEY)


@router.get("/api/zerodha/login")
async def get_kite_login_url(current_user: User = Depends(get_current_user)):
    """Get the URL to redirect the user to Zerodha's login page."""
    kite = _get_kite()
    return {"url": kite.login_url()}


@router.get("/callback")
async def kite_callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: User | None = Depends(get_current_user_optional),
):
    """
    Handle the callback from Zerodha after successful login.
    Zerodha redirects to http://127.0.0.1:8000/callback?request_token=...
    The user's auth cookie is sent along since this is a top-level navigation.
    """
    if not current_user:
        return RedirectResponse(f"{FRONTEND_URL}/login?error=Not+authenticated")

    request_token = request.query_params.get("request_token")
    if not request_token:
        # Redirect back with error if no token
        return RedirectResponse(f"{FRONTEND_URL}/?nav=portfolio&error=No+request+token")

    try:
        kite = _get_kite()
        # Exchange request token for access token
        data = kite.generate_session(request_token, api_secret=KITE_API_SECRET)
        kite.set_access_token(data["access_token"])

        # Fetch holdings
        holdings = kite.holdings()

        # Process holdings iteratively
        for item in holdings:
            ticker = item.get("tradingsymbol", "")
            quantity = item.get("quantity", 0)
            avg_price = item.get("average_price", 0.0)

            if quantity <= 0:
                continue

            # Optionally validate against TICKER_TO_YF, but Zerodha symbols usually match NSE symbols

            # Upsert into DB (overwrite with actual broker truth)
            result = await db.execute(
                select(PortfolioPosition).where(
                    PortfolioPosition.user_id == current_user.id,
                    PortfolioPosition.ticker == ticker,
                )
            )
            existing = result.scalar_one_or_none()

            if existing:
                existing.quantity = quantity
                existing.buy_price = avg_price
                existing.updated_at = datetime.now(timezone.utc)
            else:
                new_pos = PortfolioPosition(
                    user_id=current_user.id,
                    ticker=ticker,
                    quantity=quantity,
                    buy_price=avg_price
                )
                db.add(new_pos)
        
        await db.commit()
        return RedirectResponse(f"{FRONTEND_URL}/?nav=portfolio&success=1")
        
    except Exception as e:
        print(f"Kite connect error: {e}")
        return RedirectResponse(f"{FRONTEND_URL}/?nav=portfolio&error=Zerodha+integration+failed")


@router.post("/api/zerodha/upload-csv")
async def upload_holdings_csv(
    file: UploadFile = File(...),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db),
):
    """Upload a CSV downloaded from Zerodha Console (Holdings)."""
    if not file.filename.endswith(".csv"):
        raise HTTPException(status_code=400, detail="Only CSV files are allowed.")
    
    try:
        contents = await file.read()
        
        # Determine CSV encoding and separator (Zerodha exports are usually comma-separated)
        try:
            df = pd.read_csv(io.BytesIO(contents))
        except Exception:
            raise HTTPException(status_code=400, detail="Could not parse CSV file.")
            
        if df.empty:
            raise HTTPException(status_code=400, detail="CSV is empty.")
            
        # Zerodha Console Holdings CSV typical columns:
        # "Instrument", "Qty.", "Avg. cost", "LTP", ...
        # Standardize columns to lower case to make finding easier
        col_map = {c.strip().lower(): c for c in df.columns}
        
        # Find required columns
        instrument_col = col_map.get("instrument", col_map.get("symbol", col_map.get("tradingsymbol")))
        qty_col = col_map.get("qty.", col_map.get("quantity", col_map.get("qty")))
        price_col = col_map.get("avg. cost", col_map.get("average_price", col_map.get("buy_price")))
        
        if not (instrument_col and qty_col and price_col):
            raise HTTPException(status_code=400, detail="Missing required columns in CSV. Ensure 'Instrument', 'Qty.', and 'Avg. cost' exist.")
            
        imported_count = 0
        for _, row in df.iterrows():
            ticker = str(row[instrument_col]).strip().upper()
            qty = pd.to_numeric(row[qty_col], errors='coerce')
            price = pd.to_numeric(row[price_col], errors='coerce')
            
            if pd.isna(qty) or pd.isna(price) or qty <= 0:
                continue
                
            result = await db.execute(
                select(PortfolioPosition).where(
                    PortfolioPosition.user_id == current_user.id,
                    PortfolioPosition.ticker == ticker,
                )
            )
            existing = result.scalar_one_or_none()
            if existing:
                existing.quantity = float(qty)
                existing.buy_price = float(price)
                existing.updated_at = datetime.now(timezone.utc)
            else:
                new_pos = PortfolioPosition(
                    user_id=current_user.id,
                    ticker=ticker,
                    quantity=float(qty),
                    buy_price=float(price)
                )
                db.add(new_pos)
            imported_count += 1
            
        await db.commit()
        return {"message": f"Successfully imported {imported_count} positions from CSV.", "count": imported_count}
        
    except Exception as e:
        print(f"CSV Parse error: {e}")
        raise HTTPException(status_code=500, detail=f"Failed to process CSV: {str(e)}")
