from database import SessionLocal, engine
from fastapi import BackgroundTasks, Depends, FastAPI, Request
from fastapi.templating import Jinja2Templates
from models.Stock import Base, Stock
from pydantic import BaseModel
from sqlalchemy.orm import Session
from typing import List
import yfinance as yf

app = FastAPI()

Base.metadata.create_all(bind=engine)
templates = Jinja2Templates(directory="templates")


class StockTickerRequest(BaseModel):
    tickers: List[str]


# Dependency for add_stocks
def ensure_db_connection() -> Session:
    try:
        db = SessionLocal()
        yield db
    finally:
        db.close()


# Background Task
def fetch_stock_data(_id: int):
    db = SessionLocal()
    stock: Stock = db.query(Stock).filter(Stock.id == _id).first()

    yfinance_data = yf.Ticker(stock.symbol)
    if yfinance_data.info['dividendYield'] is not None:
        stock.dividend_yield = yfinance_data.info['dividendYield'] * 100

    stock.forward_eps = yfinance_data.info['forwardEps']
    stock.forward_pe = yfinance_data.info['forwardPE']
    stock.price = yfinance_data.info['previousClose']
    stock.ma50 = yfinance_data.info['fiftyDayAverage']
    stock.ma200 = yfinance_data.info['twoHundredDayAverage']

    db.add(stock)
    db.commit()


@app.get('/', status_code=200)
def dashboard(request: Request, db: Session = Depends(ensure_db_connection), forward_pe=None, dividend_yield=None, ma50=None, ma200=None):
    """
    Displays the Stock Screener Dashboard
    """
    stocks = db.query(Stock)

    if forward_pe:
        stocks = stocks.filter(Stock.forward_pe < forward_pe)

    if dividend_yield:
        stocks = stocks.filter(Stock.dividend_yield > dividend_yield)

    if ma50:
        stocks = stocks.filter(Stock.price > Stock.ma50)

    if ma200:
        stocks = stocks.filter(Stock.price > Stock.ma200)

    return templates.TemplateResponse('dashboard.html', {
        "request": request,
        "stocks": stocks,
        "dividend_yield": dividend_yield,
        "forward_pe": forward_pe,
        "ma200": ma200,
        "ma50": ma50,
    })


@app.post('/stocks', status_code=200)
async def add_stocks(
        request: StockTickerRequest,
        backgroud_tasks: BackgroundTasks,
        db: Session = Depends(ensure_db_connection)):
    """
    Add new stock(s) to saved watchlist
    """
    for ticker in request.tickers:
        new_stock = Stock()
        new_stock.symbol = ticker
        db.add(new_stock)
        db.commit()
        backgroud_tasks.add_task(fetch_stock_data, new_stock.id)

    return {
        "data": request.tickers,
        "message": "New stocks added to watchlist",
        "status": 200,
    }
