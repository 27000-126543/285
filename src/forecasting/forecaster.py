import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from sqlalchemy import and_, func

from src.database import get_db, Transaction, AccountBalance, Forecast, FundGap, ManualAdjustment
from src.utils.helpers import calculate_weighted_moving_average, date_range, round_currency

logger = logging.getLogger(__name__)

class FundForecaster:
    def __init__(self, currencies: List[str], days_ahead: int = 7, 
                 history_days: int = 90, base_currency: str = 'CNY'):
        self.currencies = currencies
        self.days_ahead = days_ahead
        self.history_days = history_days
        self.base_currency = base_currency
    
    def generate_forecast(self, forecast_date: date = None) -> Dict[str, List[Dict]]:
        if forecast_date is None:
            forecast_date = date.today()
        
        logger.info(f"Generating {self.days_ahead}-day forecast as of {forecast_date}")
        
        forecasts = {}
        for currency in self.currencies:
            forecasts[currency] = self._generate_currency_forecast(currency, forecast_date)
        
        self._save_forecasts(forecasts, forecast_date)
        return forecasts
    
    def _generate_currency_forecast(self, currency: str, forecast_date: date) -> List[Dict]:
        history = self._get_historical_flows(currency, forecast_date)
        manual_adjustments = self._get_manual_adjustments(currency, forecast_date)
        current_balance = self._get_current_balance(currency, forecast_date)
        
        forecasts = []
        running_balance = current_balance
        
        for day_offset in range(1, self.days_ahead + 1):
            target_date = forecast_date + timedelta(days=day_offset)
            
            inflow = self._predict_flow(history, 'inflow', target_date)
            outflow = self._predict_flow(history, 'outflow', target_date)
            
            for adj in manual_adjustments:
                if adj['effective_date'] == target_date:
                    if adj['adjustment_type'] == 'inflow':
                        inflow += adj['amount']
                    elif adj['adjustment_type'] == 'outflow':
                        outflow += adj['amount']
            
            net_flow = inflow - outflow
            running_balance += net_flow
            
            forecast = {
                'currency': currency,
                'forecast_date': forecast_date,
                'target_date': target_date,
                'inflow': round_currency(inflow, currency),
                'outflow': round_currency(outflow, currency),
                'net_flow': round_currency(net_flow, currency),
                'projected_balance': round_currency(running_balance, currency),
                'confidence': self._calculate_confidence(history, day_offset),
                'model_version': 'wma_v1.0'
            }
            forecasts.append(forecast)
        
        return forecasts
    
    def _get_historical_flows(self, currency: str, end_date: date) -> Dict:
        start_date = end_date - timedelta(days=self.history_days)
        
        with get_db() as db:
            results = db.query(
                Transaction.txn_date,
                Transaction.txn_type,
                func.sum(Transaction.amount).label('total')
            ).filter(
                and_(
                    Transaction.currency == currency,
                    Transaction.txn_date >= start_date,
                    Transaction.txn_date <= end_date,
                    Transaction.is_manual == False
                )
            ).group_by(
                Transaction.txn_date,
                Transaction.txn_type
            ).all()
        
        inflows = defaultdict(float)
        outflows = defaultdict(float)
        
        for row in results:
            if row.txn_type == 'in':
                inflows[row.txn_date] += abs(row.total)
            elif row.txn_type == 'out':
                outflows[row.txn_date] += abs(row.total)
        
        daily_inflows = []
        daily_outflows = []
        current = start_date
        while current <= end_date:
            daily_inflows.append(inflows.get(current, 0))
            daily_outflows.append(outflows.get(current, 0))
            current += timedelta(days=1)
        
        return {
            'inflows': daily_inflows,
            'outflows': daily_outflows,
            'start_date': start_date,
            'end_date': end_date
        }
    
    def _predict_flow(self, history: Dict, flow_type: str, target_date: date) -> float:
        flows = history['inflows'] if flow_type == 'inflow' else history['outflows']
        weekday = target_date.weekday()
        
        window_size = 14
        recent_flows = flows[-window_size:] if len(flows) >= window_size else flows
        
        weekday_flows = []
        for i, flow in enumerate(recent_flows):
            hist_date = history['end_date'] - timedelta(days=len(recent_flows) - 1 - i)
            if hist_date.weekday() == weekday:
                weekday_flows.append(flow)
        
        if weekday_flows:
            return calculate_weighted_moving_average(weekday_flows)
        
        return calculate_weighted_moving_average(recent_flows)
    
    def _calculate_confidence(self, history: Dict, day_offset: int) -> float:
        base_confidence = 0.95
        decay = 0.02
        confidence = base_confidence - (day_offset - 1) * decay
        return max(0.7, confidence)
    
    def _get_current_balance(self, currency: str, as_of_date: date) -> float:
        with get_db() as db:
            latest_balance = db.query(AccountBalance).filter(
                and_(
                    AccountBalance.currency == currency,
                    AccountBalance.balance_date <= as_of_date
                )
            ).order_by(AccountBalance.balance_date.desc()).first()
            
            if latest_balance:
                return latest_balance.balance
        
        return 0.0
    
    def _get_manual_adjustments(self, currency: str, forecast_date: date) -> List[Dict]:
        end_date = forecast_date + timedelta(days=self.days_ahead)
        
        with get_db() as db:
            adjustments = db.query(ManualAdjustment).filter(
                and_(
                    ManualAdjustment.currency == currency,
                    ManualAdjustment.effective_date > forecast_date,
                    ManualAdjustment.effective_date <= end_date,
                    ManualAdjustment.is_applied == True
                )
            ).all()
            
            return [
                {
                    'id': adj.id,
                    'adjustment_type': adj.adjustment_type,
                    'amount': adj.amount,
                    'effective_date': adj.effective_date,
                    'description': adj.description
                }
                for adj in adjustments
            ]
    
    def _save_forecasts(self, forecasts: Dict[str, List[Dict]], forecast_date: date):
        with get_db() as db:
            db.query(Forecast).filter(Forecast.forecast_date == forecast_date).delete()
            
            for currency, currency_forecasts in forecasts.items():
                for fc in currency_forecasts:
                    forecast = Forecast(
                        currency=fc['currency'],
                        forecast_date=fc['forecast_date'],
                        target_date=fc['target_date'],
                        inflow=fc['inflow'],
                        outflow=fc['outflow'],
                        net_flow=fc['net_flow'],
                        projected_balance=fc['projected_balance'],
                        confidence=fc['confidence'],
                        model_version=fc['model_version']
                    )
                    db.add(forecast)
            
            db.commit()
            logger.info(f"Saved forecasts for {len(forecasts)} currencies")
    
    def detect_fund_gaps(self, forecast_date: date = None, 
                         thresholds: Dict[str, float] = None) -> List[Dict]:
        if forecast_date is None:
            forecast_date = date.today()
        
        if thresholds is None:
            thresholds = {curr: 100000 for curr in self.currencies}
        
        logger.info(f"Detecting fund gaps as of {forecast_date}")
        
        gaps = []
        with get_db() as db:
            forecasts = db.query(Forecast).filter(
                Forecast.forecast_date == forecast_date
            ).all()
            
            for fc in forecasts:
                threshold = thresholds.get(fc.currency, 100000)
                if fc.projected_balance < threshold:
                    gap_amount = threshold - fc.projected_balance
                    severity = 'low'
                    if gap_amount > threshold * 0.5:
                        severity = 'high'
                    elif gap_amount > threshold * 0.2:
                        severity = 'medium'
                    
                    gap = {
                        'currency': fc.currency,
                        'gap_date': fc.target_date,
                        'gap_amount': round_currency(gap_amount, fc.currency),
                        'projected_balance': fc.projected_balance,
                        'threshold': threshold,
                        'severity': severity
                    }
                    gaps.append(gap)
        
        self._save_gaps(gaps)
        logger.info(f"Detected {len(gaps)} fund gaps")
        return gaps
    
    def _save_gaps(self, gaps: List[Dict]):
        with get_db() as db:
            for gap_data in gaps:
                existing = db.query(FundGap).filter(
                    and_(
                        FundGap.currency == gap_data['currency'],
                        FundGap.gap_date == gap_data['gap_date'],
                        FundGap.status == 'open'
                    )
                ).first()
                
                if not existing:
                    gap = FundGap(
                        currency=gap_data['currency'],
                        gap_date=gap_data['gap_date'],
                        gap_amount=gap_data['gap_amount'],
                        projected_balance=gap_data['projected_balance'],
                        threshold=gap_data['threshold'],
                        severity=gap_data['severity'],
                        status='open'
                    )
                    db.add(gap)
                else:
                    existing.gap_amount = gap_data['gap_amount']
                    existing.projected_balance = gap_data['projected_balance']
                    existing.severity = gap_data['severity']
            
            db.commit()
