import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
import random
import requests
from sqlalchemy import and_, desc

from src.database import get_db, ExchangeRate
from src.utils.helpers import round_currency

logger = logging.getLogger(__name__)

class ExchangeRateManager:
    def __init__(self, base_currency: str = 'CNY', supported_currencies: List[str] = None):
        self.base_currency = base_currency
        self.supported_currencies = supported_currencies or ['CNY', 'USD', 'EUR', 'HKD', 'JPY', 'GBP']
        self._rate_cache: Dict[Tuple[str, str, date], float] = {}
    
    def fetch_live_rates(self, api_url: str = None) -> Dict[str, float]:
        logger.info("Fetching live exchange rates")
        rates = {}
        
        try:
            if api_url:
                response = requests.get(api_url, timeout=30)
                if response.status_code == 200:
                    data = response.json()
                    rates = data.get('rates', {})
            else:
                rates = self._generate_mock_rates()
        except Exception as e:
            logger.warning(f"Failed to fetch live rates, using mock: {e}")
            rates = self._generate_mock_rates()
        
        rates[self.base_currency] = 1.0
        self._save_rates(rates, date.today())
        logger.info(f"Fetched rates for {len(rates)} currencies")
        return rates
    
    def _generate_mock_rates(self) -> Dict[str, float]:
        base_rates = {
            'USD': 0.14,
            'EUR': 0.13,
            'HKD': 1.09,
            'JPY': 21.5,
            'GBP': 0.11,
            'CNY': 1.0,
        }
        
        rates = {}
        for curr in self.supported_currencies:
            if curr == self.base_currency:
                continue
            base = base_rates.get(curr, 0.1)
            variation = random.uniform(-0.005, 0.005)
            rates[curr] = round(base + variation, 6)
        
        return rates
    
    def _save_rates(self, rates: Dict[str, float], rate_date: date):
        with get_db() as db:
            for target_currency, rate in rates.items():
                if target_currency == self.base_currency:
                    continue
                
                existing = db.query(ExchangeRate).filter(
                    and_(
                        ExchangeRate.base_currency == self.base_currency,
                        ExchangeRate.target_currency == target_currency,
                        ExchangeRate.rate_date == rate_date
                    )
                ).first()
                
                if existing:
                    existing.rate = rate
                    existing.fetched_at = datetime.now()
                else:
                    rate_record = ExchangeRate(
                        base_currency=self.base_currency,
                        target_currency=target_currency,
                        rate=rate,
                        rate_date=rate_date,
                        source='api'
                    )
                    db.add(rate_record)
            
            db.commit()
    
    def get_rate(self, source_currency: str, target_currency: str, 
                 rate_date: date = None) -> float:
        if rate_date is None:
            rate_date = date.today()
        
        cache_key = (source_currency, target_currency, rate_date)
        if cache_key in self._rate_cache:
            return self._rate_cache[cache_key]
        
        if source_currency == target_currency:
            return 1.0
        
        with get_db() as db:
            if source_currency == self.base_currency:
                rate_record = db.query(ExchangeRate).filter(
                    and_(
                        ExchangeRate.base_currency == self.base_currency,
                        ExchangeRate.target_currency == target_currency,
                        ExchangeRate.rate_date <= rate_date
                    )
                ).order_by(desc(ExchangeRate.rate_date)).first()
                
                if rate_record:
                    rate = rate_record.rate
                else:
                    rate = self._get_fallback_rate(source_currency, target_currency)
            elif target_currency == self.base_currency:
                rate_record = db.query(ExchangeRate).filter(
                    and_(
                        ExchangeRate.base_currency == self.base_currency,
                        ExchangeRate.target_currency == source_currency,
                        ExchangeRate.rate_date <= rate_date
                    )
                ).order_by(desc(ExchangeRate.rate_date)).first()
                
                if rate_record:
                    rate = 1.0 / rate_record.rate
                else:
                    rate = self._get_fallback_rate(source_currency, target_currency)
            else:
                source_to_base = self.get_rate(source_currency, self.base_currency, rate_date)
                base_to_target = self.get_rate(self.base_currency, target_currency, rate_date)
                rate = source_to_base * base_to_target
        
        self._rate_cache[cache_key] = rate
        return rate
    
    def _get_fallback_rate(self, source: str, target: str) -> float:
        fallback = {
            ('USD', 'CNY'): 7.2,
            ('CNY', 'USD'): 0.1389,
            ('EUR', 'CNY'): 7.8,
            ('CNY', 'EUR'): 0.1282,
            ('HKD', 'CNY'): 0.92,
            ('CNY', 'HKD'): 1.087,
            ('JPY', 'CNY'): 0.048,
            ('CNY', 'JPY'): 20.83,
            ('GBP', 'CNY'): 9.1,
            ('CNY', 'GBP'): 0.1099,
            ('USD', 'EUR'): 0.92,
            ('EUR', 'USD'): 1.087,
            ('USD', 'HKD'): 7.8,
            ('HKD', 'USD'): 0.1282,
        }
        return fallback.get((source, target), 1.0)
    
    def convert(self, amount: float, source_currency: str, 
                target_currency: str, rate_date: date = None) -> float:
        rate = self.get_rate(source_currency, target_currency, rate_date)
        return round_currency(amount * rate, target_currency)
    
    def get_historical_rates(self, source_currency: str, target_currency: str,
                             start_date: date, end_date: date) -> List[Tuple[date, float]]:
        rates = []
        current = start_date
        while current <= end_date:
            rate = self.get_rate(source_currency, target_currency, current)
            rates.append((current, rate))
            current += timedelta(days=1)
        return rates
    
    def calculate_volatility(self, currency: str, days: int = 30, 
                             base_currency: str = None) -> Dict[str, float]:
        if base_currency is None:
            base_currency = self.base_currency
        
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        
        rates = [
            rate for _, rate in self.get_historical_rates(
                currency, base_currency, start_date, end_date
            )
        ]
        
        if len(rates) < 2:
            return {'daily': 0, 'weekly': 0, 'monthly': 0}
        
        returns = []
        for i in range(1, len(rates)):
            if rates[i-1] != 0:
                returns.append((rates[i] - rates[i-1]) / rates[i-1])
        
        if not returns:
            return {'daily': 0, 'weekly': 0, 'monthly': 0}
        
        import statistics
        daily_vol = statistics.stdev(returns) if len(returns) > 1 else 0
        
        return {
            'daily': daily_vol,
            'weekly': daily_vol * (7 ** 0.5),
            'monthly': daily_vol * (30 ** 0.5),
        }
    
    def backfill_historical_rates(self, days: int = 90):
        logger.info(f"Backfilling historical rates for {days} days")
        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        current = start_date
        
        while current <= end_date:
            rates = self._generate_mock_rates()
            rates[self.base_currency] = 1.0
            self._save_rates(rates, current)
            current += timedelta(days=1)
        
        logger.info("Historical rates backfill completed")
