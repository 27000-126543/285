import uuid
import json
import hashlib
from datetime import datetime, date, timedelta
from decimal import Decimal, ROUND_HALF_UP
from typing import List, Dict, Any, Optional
import pandas as pd

def generate_id(prefix=''):
    return f"{prefix}{uuid.uuid4().hex[:16].upper()}"

def safe_json_dumps(obj):
    def default(o):
        if isinstance(o, (datetime, date)):
            return o.isoformat()
        if isinstance(o, Decimal):
            return float(o)
        return str(o)
    return json.dumps(obj, default=default, ensure_ascii=False)

def safe_json_loads(s):
    if isinstance(s, dict):
        return s
    try:
        return json.loads(s) if s else {}
    except (json.JSONDecodeError, TypeError):
        return {}

def round_currency(amount, currency='CNY'):
    decimal_places = {
        'JPY': 0,
        'KRW': 0,
        'VND': 0,
        'IDR': 0,
    }
    places = decimal_places.get(currency, 2)
    d = Decimal(str(amount))
    return float(d.quantize(Decimal(f'0.{"0"*places}'), rounding=ROUND_HALF_UP))

def date_range(start_date, end_date):
    current = start_date
    while current <= end_date:
        yield current
        current += timedelta(days=1)

def get_business_days(start_date, end_date, holidays=None):
    if holidays is None:
        holidays = []
    business_days = []
    current = start_date
    while current <= end_date:
        if current.weekday() < 5 and current not in holidays:
            business_days.append(current)
        current += timedelta(days=1)
    return business_days

def calculate_moving_average(data, window=7):
    if len(data) < window:
        return sum(data) / len(data) if data else 0
    return pd.Series(data).rolling(window=window).mean().iloc[-1]

def calculate_weighted_moving_average(data, weights=None):
    if not data:
        return 0
    if weights is None:
        weights = [i + 1 for i in range(len(data))]
    if len(weights) != len(data):
        weights = weights[-len(data):] if len(weights) > len(data) else weights + [1] * (len(data) - len(weights))
    total_weight = sum(weights)
    return sum(d * w for d, w in zip(data, weights)) / total_weight if total_weight > 0 else 0

def hash_transaction(txn_data):
    txn_str = '|'.join(str(txn_data.get(k, '')) for k in sorted(txn_data.keys()))
    return hashlib.md5(txn_str.encode('utf-8')).hexdigest()

def chunk_list(lst, chunk_size):
    for i in range(0, len(lst), chunk_size):
        yield lst[i:i + chunk_size]
