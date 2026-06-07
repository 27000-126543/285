import logging
from datetime import date, datetime, timedelta
from typing import Dict, List, Optional, Tuple
from sqlalchemy import and_, func

from src.database import get_db, AccountBalance, Transaction, RiskExposure, RiskAlert, Forecast
from src.banking.exchange_rates import ExchangeRateManager
from src.utils.helpers import generate_id, safe_json_dumps, round_currency

logger = logging.getLogger(__name__)

class RiskExposureCalculator:
    def __init__(self, rate_manager: ExchangeRateManager, 
                 currencies: List[str], base_currency: str = 'CNY'):
        self.rate_manager = rate_manager
        self.currencies = currencies
        self.base_currency = base_currency
    
    def calculate_daily_exposure(self, exposure_date: date = None) -> List[Dict]:
        if exposure_date is None:
            exposure_date = date.today()
        
        logger.info(f"Calculating risk exposure for {exposure_date}")
        
        exposures = []
        for currency in self.currencies:
            if currency == self.base_currency:
                continue
            
            exposure = self._calculate_currency_exposure(currency, exposure_date)
            exposures.append(exposure)
        
        self._save_exposures(exposures)
        logger.info(f"Calculated exposure for {len(exposures)} currencies")
        return exposures
    
    def _calculate_currency_exposure(self, currency: str, exposure_date: date) -> Dict:
        net_position = self._calculate_net_position(currency, exposure_date)
        exposure_amount = self.rate_manager.convert(
            abs(net_position), currency, self.base_currency, exposure_date
        )
        
        volatility = self.rate_manager.calculate_volatility(currency, days=30)
        var_95 = exposure_amount * volatility['daily'] * 1.645
        
        return {
            'currency': currency,
            'exposure_date': exposure_date,
            'net_position': round_currency(net_position, currency),
            'exposure_amount': round_currency(exposure_amount, self.base_currency),
            'base_currency': self.base_currency,
            'volatility_3d': volatility['daily'] * 3,
            'var_95': round_currency(var_95, self.base_currency)
        }
    
    def _calculate_net_position(self, currency: str, as_of_date: date) -> float:
        with get_db() as db:
            latest_balance = db.query(AccountBalance).filter(
                and_(
                    AccountBalance.currency == currency,
                    AccountBalance.balance_date <= as_of_date
                )
            ).order_by(AccountBalance.balance_date.desc()).first()
            
            current_balance = latest_balance.balance if latest_balance else 0.0
            
            end_date = as_of_date + timedelta(days=30)
            future_flows = db.query(Forecast).filter(
                and_(
                    Forecast.currency == currency,
                    Forecast.target_date > as_of_date,
                    Forecast.target_date <= end_date
                )
            ).all()
            
            total_net = sum(f.net_flow for f in future_flows)
            
            return current_balance + total_net
    
    def _save_exposures(self, exposures: List[Dict]):
        with get_db() as db:
            for exp_data in exposures:
                existing = db.query(RiskExposure).filter(
                    and_(
                        RiskExposure.currency == exp_data['currency'],
                        RiskExposure.exposure_date == exp_data['exposure_date']
                    )
                ).first()
                
                if existing:
                    existing.net_position = exp_data['net_position']
                    existing.exposure_amount = exp_data['exposure_amount']
                    existing.volatility_3d = exp_data['volatility_3d']
                    existing.var_95 = exp_data['var_95']
                else:
                    exposure = RiskExposure(
                        currency=exp_data['currency'],
                        exposure_date=exp_data['exposure_date'],
                        net_position=exp_data['net_position'],
                        exposure_amount=exp_data['exposure_amount'],
                        base_currency=exp_data['base_currency'],
                        volatility_3d=exp_data['volatility_3d'],
                        var_95=exp_data['var_95']
                    )
                    db.add(exposure)
            
            db.commit()

class RiskAlertGenerator:
    def __init__(self, rate_manager: ExchangeRateManager, currencies: List[str],
                 volatility_threshold: float = 0.02, volatility_days: int = 3,
                 base_currency: str = 'CNY'):
        self.rate_manager = rate_manager
        self.currencies = currencies
        self.volatility_threshold = volatility_threshold
        self.volatility_days = volatility_days
        self.base_currency = base_currency
    
    def generate_alerts(self, check_date: date = None) -> List[Dict]:
        if check_date is None:
            check_date = date.today()
        
        logger.info(f"Generating risk alerts for {check_date}")
        
        alerts = []
        
        for currency in self.currencies:
            if currency == self.base_currency:
                continue
            
            if self._check_volatility_alert(currency, check_date):
                alert = self._create_volatility_alert(currency, check_date)
                alerts.append(alert)
            
            exposure_alert = self._check_exposure_alert(currency, check_date)
            if exposure_alert:
                alerts.append(exposure_alert)
        
        self._save_alerts(alerts)
        logger.info(f"Generated {len(alerts)} risk alerts")
        return alerts
    
    def _check_volatility_alert(self, currency: str, check_date: date) -> bool:
        end_date = check_date
        start_date = end_date - timedelta(days=self.volatility_days)
        
        rates = self.rate_manager.get_historical_rates(
            currency, self.base_currency, start_date, end_date
        )
        
        if len(rates) < self.volatility_days + 1:
            return False
        
        rate_values = [r for _, r in rates]
        if rate_values[0] == 0:
            return False
        
        total_change = abs(rate_values[-1] - rate_values[0]) / rate_values[0]
        
        consecutive_days = 0
        for i in range(1, len(rate_values)):
            if rate_values[i-1] != 0:
                daily_change = abs(rate_values[i] - rate_values[i-1]) / rate_values[i-1]
                if daily_change > self.volatility_threshold / 3:
                    consecutive_days += 1
                else:
                    consecutive_days = 0
        
        return total_change > self.volatility_threshold or consecutive_days >= self.volatility_days
    
    def _create_volatility_alert(self, currency: str, check_date: date) -> Dict:
        end_date = check_date
        start_date = end_date - timedelta(days=30)
        
        rates = self.rate_manager.get_historical_rates(
            currency, self.base_currency, start_date, end_date
        )
        rate_values = [r for _, r in rates]
        
        if len(rate_values) >= 3:
            change_3d = abs(rate_values[-1] - rate_values[-4]) / rate_values[-4] if rate_values[-4] != 0 else 0
        else:
            change_3d = 0
        
        severity = 'high' if change_3d > 0.05 else 'medium' if change_3d > 0.02 else 'low'
        
        hedge_recommendation = self._generate_hedge_recommendation(currency, change_3d)
        
        return {
            'alert_id': generate_id('ALT'),
            'currency': currency,
            'alert_type': 'volatility',
            'severity': severity,
            'message': f'{currency} 汇率波动异常，近3日波动幅度达{change_3d*100:.2f}%',
            'metrics': safe_json_dumps({
                'change_3d': change_3d,
                'current_rate': rate_values[-1] if rate_values else 0,
                'volatility_threshold': self.volatility_threshold
            }),
            'hedge_recommendation': safe_json_dumps(hedge_recommendation),
            'status': 'active',
            'created_at': datetime.now()
        }
    
    def _check_exposure_alert(self, currency: str, check_date: date) -> Optional[Dict]:
        with get_db() as db:
            exposure = db.query(RiskExposure).filter(
                and_(
                    RiskExposure.currency == currency,
                    RiskExposure.exposure_date == check_date
                )
            ).first()
            
            if not exposure:
                return None
            
            total_exposure = db.query(
                func.sum(RiskExposure.exposure_amount)
            ).filter(RiskExposure.exposure_date == check_date).scalar() or 1
            
            exposure_ratio = exposure.exposure_amount / total_exposure if total_exposure > 0 else 0
            
            if exposure_ratio > 0.3:
                severity = 'high' if exposure_ratio > 0.5 else 'medium'
                return {
                    'alert_id': generate_id('ALT'),
                    'currency': currency,
                    'alert_type': 'exposure_concentration',
                    'severity': severity,
                    'message': f'{currency} 风险敞口占比过高，达{exposure_ratio*100:.1f}%',
                    'metrics': safe_json_dumps({
                        'exposure_amount': exposure.exposure_amount,
                        'exposure_ratio': exposure_ratio,
                        'net_position': exposure.net_position
                    }),
                    'hedge_recommendation': safe_json_dumps(
                        self._generate_exposure_hedge_recommendation(currency, exposure)
                    ),
                    'status': 'active',
                    'created_at': datetime.now()
                }
        
        return None
    
    def _generate_hedge_recommendation(self, currency: str, volatility: float) -> Dict:
        recommendations = []
        
        if volatility > 0.05:
            recommendations.append('建议立即启动汇率对冲程序')
            recommendations.append(f'考虑使用远期结售汇锁定{currency}汇率风险')
            recommendations.append('建议调整外汇资产负债结构，降低敞口')
        elif volatility > 0.02:
            recommendations.append('建议密切关注汇率走势')
            recommendations.append('可考虑部分对冲以降低风险')
            recommendations.append('考虑使用期权工具进行保护性对冲')
        else:
            recommendations.append('风险在可控范围内')
            recommendations.append('维持现有对冲策略')
        
        return {
            'recommendations': recommendations,
            'suggested_hedge_ratio': min(0.8, volatility * 10),
            'suggested_instruments': ['forward', 'option', 'swap']
        }
    
    def _generate_exposure_hedge_recommendation(self, currency: str, exposure) -> Dict:
        return {
            'recommendations': [
                f'建议将{currency}敞口比例控制在30%以内',
                '考虑通过换汇分散币种配置',
                '增加其他币种资产以平衡风险'
            ],
            'target_exposure_ratio': 0.3,
            'suggested_actions': ['rebalance', 'diversify']
        }
    
    def _save_alerts(self, alerts: List[Dict]):
        with get_db() as db:
            for alert_data in alerts:
                existing = db.query(RiskAlert).filter_by(
                    alert_id=alert_data['alert_id']
                ).first()
                
                if not existing:
                    alert = RiskAlert(
                        alert_id=alert_data['alert_id'],
                        currency=alert_data['currency'],
                        alert_type=alert_data['alert_type'],
                        severity=alert_data['severity'],
                        message=alert_data['message'],
                        metrics=alert_data['metrics'],
                        hedge_recommendation=alert_data['hedge_recommendation'],
                        status=alert_data['status']
                    )
                    db.add(alert)
            
            db.commit()
