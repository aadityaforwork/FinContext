"""
Company Data Router
====================
Thin HTTP layer over services.fundamentals. All yfinance fetching, caching,
and formatting lives in the service; this file only translates between HTTP
and Python calls and adds disclaimers.
"""

from fastapi import APIRouter, HTTPException

from app.core.compliance import with_disclaimer
from app.services import fundamentals

router = APIRouter(prefix="/api/company", tags=["company"])


@router.get("/{ticker}/overview")
async def get_company_overview(ticker: str):
    try:
        return with_disclaimer(fundamentals.get_overview(ticker))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{ticker}/financials")
async def get_company_financials(ticker: str, period: str = "annual"):
    try:
        return with_disclaimer(fundamentals.get_financials(ticker, period))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{ticker}/ratios")
async def get_company_ratios(ticker: str):
    try:
        return with_disclaimer(fundamentals.get_ratios(ticker))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{ticker}/peers")
async def get_peer_comparison(ticker: str):
    try:
        return with_disclaimer(fundamentals.get_peers(ticker))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/{ticker}/shareholding")
async def get_shareholding(ticker: str):
    try:
        return with_disclaimer(fundamentals.get_shareholding(ticker))
    except LookupError as e:
        raise HTTPException(status_code=404, detail=str(e))
