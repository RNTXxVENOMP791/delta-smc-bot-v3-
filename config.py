import os
from dotenv import load_dotenv
load_dotenv()

DEMO_BASE_URL = os.getenv("DELTA_DEMO_BASE_URL", "https://cdn-ind.testnet.deltaex.org").rstrip("/")
API_KEY = os.getenv("DELTA_API_KEY", "")
API_SECRET = os.getenv("DELTA_API_SECRET", "")
TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN", "")
TELEGRAM_CHAT_ID = os.getenv("TELEGRAM_CHAT_ID", "")
DEFAULT_VIRTUAL_BALANCE = float(os.getenv("DEFAULT_VIRTUAL_BALANCE", "1000"))
RISK_PER_TRADE = 0.005
MAX_DAILY_LOSS = 0.02
SYMBOLS = ["BTCUSD", "ETHUSD"]
