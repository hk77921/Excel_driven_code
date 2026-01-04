import sys
import os

# Ensure project root is on sys.path so `src` can be imported
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from src.broker.zerodha import ZerodhaBroker

class K:
    def __init__(self, quote):
        self._q = quote
    def quote(self, arg):
        return self._q


def test_quote(q):
    b = ZerodhaBroker(mode="LIVE")
    b.is_connected = True
    b.kite = K(q)
    print("INPUT:", q)
    print("OUTPUT:", b._fetch_live_price("IDEA"))
    print('-' * 40)


test_quote({'NSE:IDEA': {'last_price': '123.45'}})

test_quote({'NSE:IDEA': {'ltp': 200}})

test_quote({'last_price': 150})

test_quote({'some_other': {'last_traded_price': '99.9'}})

test_quote({})

test_quote({'NSE:IDEA': None})

test_quote({'NSE:IDEA': {'last_price': None, 'ltp': '0'}})
