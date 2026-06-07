import logging
import time
import traceback
from datetime import date, datetime
from typing import Dict, List, Optional
from concurrent.futures import ThreadPoolExecutor, as_completed
import schedule
import threading

from src.config import CONFIG
from src.database import initialize_database, get_db
from src.banking.fetcher import BankDataFetcher
from src.banking.exchange_rates import ExchangeRateManager
from src.forecasting.forecaster import FundForecaster
from src.forecasting.manual_adjustments import ManualAdjustmentManager
from src.exchange.proposal_generator import ExchangeProposalGenerator
from src.approval.workflow import ApprovalWorkflow, ExchangeExecutor
from src.risk.calculator import RiskExposureCalculator, RiskAlertGenerator
from src.reports.generator import ReportGenerator
from src.query.transaction_query import TransactionQuery
from src.notifications.sender import NotificationSender, SystemLogger

logger = logging.getLogger(__name__)

class FundPoolSystem:
    def __init__(self):
        self.config = CONFIG
        self._initialized = False
        self._components = {}
        self._lock = threading.Lock()
    
    def initialize(self):
        if self._initialized:
            return
        
        logger.info("Initializing Fund Pool Management System...")
        
        initialize_database(self.config['database']['path'])
        
        self._components['rate_manager'] = ExchangeRateManager(
            base_currency=self.config['currencies']['base'],
            supported_currencies=self.config['currencies']['supported']
        )
        
        self._components['fetcher'] = BankDataFetcher(
            accounts_config=self.config['bank_accounts'],
            max_workers=self.config['system']['max_concurrent_tasks']
        )
        
        self._components['forecaster'] = FundForecaster(
            currencies=self.config['currencies']['supported'],
            days_ahead=self.config['forecasting']['days_ahead'],
            history_days=self.config['forecasting']['history_days'],
            base_currency=self.config['currencies']['base']
        )
        
        self._components['manual_adjustments'] = ManualAdjustmentManager(
            currencies=self.config['currencies']['supported']
        )
        
        self._components['proposal_generator'] = ExchangeProposalGenerator(
            rate_manager=self._components['rate_manager'],
            currencies=self.config['currencies']['supported'],
            base_currency=self.config['currencies']['base']
        )
        
        self._components['approval_workflow'] = ApprovalWorkflow(
            approval_levels=self.config['approval']['levels'],
            base_currency=self.config['approval']['base_currency'],
            auto_approve_below=self.config['approval']['auto_approve_below'],
            rate_manager=self._components['rate_manager']
        )
        
        self._components['exchange_executor'] = ExchangeExecutor(
            rate_manager=self._components['rate_manager'],
            accounts_config=self.config['bank_accounts']
        )
        
        self._components['risk_calculator'] = RiskExposureCalculator(
            rate_manager=self._components['rate_manager'],
            currencies=self.config['currencies']['supported'],
            base_currency=self.config['currencies']['base']
        )
        
        self._components['risk_alert'] = RiskAlertGenerator(
            rate_manager=self._components['rate_manager'],
            currencies=self.config['currencies']['supported'],
            volatility_threshold=self.config['risk']['volatility_threshold'],
            volatility_days=self.config['risk']['volatility_days'],
            base_currency=self.config['currencies']['base']
        )
        
        self._components['report_generator'] = ReportGenerator(
            rate_manager=self._components['rate_manager'],
            currencies=self.config['currencies']['supported'],
            base_currency=self.config['currencies']['base']
        )
        
        self._components['transaction_query'] = TransactionQuery(
            batch_size=self.config['system']['batch_size']
        )
        
        self._components['notification_sender'] = NotificationSender(
            wechat_webhook_url=self.config['notifications']['enterprise_wechat'].get('webhook_url'),
            email_config=self.config['notifications']['email']
        )
        
        self._initialized = True
        logger.info("System initialized successfully")
    
    def _get(self, name):
        if not self._initialized:
            self.initialize()
        return self._components.get(name)
    
    def daily_data_fetch(self):
        logger.info("=== Starting daily data fetch ===")
        try:
            fetcher = self._get('fetcher')
            rate_manager = self._get('rate_manager')
            
            with ThreadPoolExecutor(max_workers=4) as executor:
                future_balances = executor.submit(fetcher.fetch_all_balances)
                future_txns = executor.submit(fetcher.fetch_all_transactions, days=1)
                future_rates = executor.submit(rate_manager.fetch_live_rates)
                
                balances = future_balances.result()
                txns = future_txns.result()
                rates = future_rates.result()
            
            SystemLogger.log_action(
                'scheduled_task', 'system', 'daily_data_fetch', 'success',
                f"抓取完成: {len(balances)}个账户余额, {sum(len(t) for t in txns.values())}条交易, {len(rates)}个汇率"
            )
            
            logger.info("=== Daily data fetch completed ===")
            
        except Exception as e:
            logger.error(f"Daily data fetch failed: {e}")
            logger.error(traceback.format_exc())
            SystemLogger.log_action(
                'scheduled_task', 'system', 'daily_data_fetch', 'error', str(e)
            )
            self._send_alert('数据抓取异常', f"每日数据抓取失败: {e}")
    
    def daily_forecast(self):
        logger.info("=== Starting daily forecast ===")
        try:
            forecaster = self._get('forecaster')
            notifier = self._get('notification_sender')
            
            forecasts = forecaster.generate_forecast()
            gaps = forecaster.detect_fund_gaps()
            
            for gap in gaps:
                if gap['severity'] in ('medium', 'high'):
                    notifier.send_gap_alert(gap)
            
            SystemLogger.log_action(
                'scheduled_task', 'forecasting', 'daily_forecast', 'success',
                f"预测完成: {len(gaps)}个资金缺口"
            )
            
            if gaps:
                self._generate_proposals_for_gaps(gaps)
            
            logger.info("=== Daily forecast completed ===")
            
        except Exception as e:
            logger.error(f"Daily forecast failed: {e}")
            logger.error(traceback.format_exc())
            SystemLogger.log_action(
                'scheduled_task', 'forecasting', 'daily_forecast', 'error', str(e)
            )
            self._send_alert('预测计算异常', f"每日资金预测失败: {e}")
    
    def _generate_proposals_for_gaps(self, gaps: List[Dict]):
        try:
            generator = self._get('proposal_generator')
            proposals = generator.generate_proposals_for_gaps(gaps)
            
            for prop in proposals:
                self._get('approval_workflow').initiate_approvals(prop['proposal_id'])
            
            logger.info(f"Generated {len(proposals)} exchange proposals")
            
        except Exception as e:
            logger.error(f"Proposal generation failed: {e}")
    
    def daily_risk_check(self):
        logger.info("=== Starting daily risk check ===")
        try:
            calculator = self._get('risk_calculator')
            alert_gen = self._get('risk_alert')
            notifier = self._get('notification_sender')
            
            exposures = calculator.calculate_daily_exposure()
            alerts = alert_gen.generate_alerts()
            
            for alert in alerts:
                if alert['severity'] in ('medium', 'high'):
                    notifier.send_risk_alert(alert)
            
            SystemLogger.log_action(
                'scheduled_task', 'risk', 'daily_risk_check', 'success',
                f"风险检查完成: {len(exposures)}个敞口计算, {len(alerts)}个风险预警"
            )
            
            logger.info("=== Daily risk check completed ===")
            
        except Exception as e:
            logger.error(f"Daily risk check failed: {e}")
            logger.error(traceback.format_exc())
            SystemLogger.log_action(
                'scheduled_task', 'risk', 'daily_risk_check', 'error', str(e)
            )
            self._send_alert('风险检查异常', f"每日风险检查失败: {e}")
    
    def monthly_report(self):
        logger.info("=== Starting monthly report generation ===")
        try:
            today = date.today()
            if today.day != 1:
                logger.info("Not the 1st day of month, skipping report generation")
                return
            
            last_month = today.replace(day=1)
            if last_month.month == 1:
                last_month = last_month.replace(year=last_month.year - 1, month=12)
            else:
                last_month = last_month.replace(month=last_month.month - 1)
            
            generator = self._get('report_generator')
            report = generator.generate_monthly_report(
                year=last_month.year,
                month=last_month.month
            )
            
            SystemLogger.log_action(
                'scheduled_task', 'reports', 'monthly_report', 'success',
                f"月度报告生成完成: {report['report_id']}"
            )
            
            self._send_alert(
                '月度报告已生成',
                f"{report['report_month']} 资金池分析报告已生成\nExcel: {report['excel_path']}\nPDF: {report['pdf_path']}"
            )
            
            logger.info("=== Monthly report generation completed ===")
            
        except Exception as e:
            logger.error(f"Monthly report generation failed: {e}")
            logger.error(traceback.format_exc())
            SystemLogger.log_action(
                'scheduled_task', 'reports', 'monthly_report', 'error', str(e)
            )
            self._send_alert('报告生成异常', f"月度报告生成失败: {e}")
    
    def _send_alert(self, title: str, content: str):
        try:
            notifier = self._get('notification_sender')
            notifier.send_alert(title, content, priority='high')
        except Exception as e:
            logger.error(f"Failed to send alert: {e}")
    
    def execute_exchange(self, proposal_id: str, source_account_id: str,
                         target_account_id: str) -> Optional[Dict]:
        logger.info(f"Executing exchange for proposal {proposal_id}")
        
        with self._lock:
            executor = self._get('exchange_executor')
            result = executor.execute_exchange(proposal_id, source_account_id, target_account_id)
            
            if result:
                SystemLogger.log_exchange(
                    proposal_id=proposal_id,
                    status='completed',
                    details=result
                )
            else:
                SystemLogger.log_exchange(
                    proposal_id=proposal_id,
                    status='failed',
                    details={'error': 'Execution failed'}
                )
            
            return result
    
    def approve_proposal(self, proposal_id: str, level: int, approver: str,
                         comments: str = None) -> bool:
        workflow = self._get('approval_workflow')
        result = workflow.approve(proposal_id, level, approver, comments)
        
        if result:
            SystemLogger.log_approval(proposal_id, level, approver, 'approved')
        
        return result
    
    def reject_proposal(self, proposal_id: str, level: int, approver: str,
                        comments: str = None) -> bool:
        workflow = self._get('approval_workflow')
        result = workflow.reject(proposal_id, level, approver, comments)
        
        if result:
            SystemLogger.log_approval(proposal_id, level, approver, 'rejected')
        
        return result
    
    def add_manual_adjustment(self, currency: str, adjustment_type: str,
                              amount: float, effective_date: date,
                              description: str, **kwargs) -> Dict:
        manager = self._get('manual_adjustments')
        adjustment = manager.create_adjustment(
            currency=currency,
            adjustment_type=adjustment_type,
            amount=amount,
            effective_date=effective_date,
            description=description,
            **kwargs
        )
        manager.apply_adjustment(adjustment['adjustment_id'])
        return adjustment
    
    def query_transactions(self, **kwargs) -> Dict:
        query = self._get('transaction_query')
        return query.query_transactions(**kwargs)
    
    def export_transactions(self, start_date: date, end_date: date,
                            export_format: str = 'excel', **kwargs) -> str:
        query = self._get('transaction_query')
        transactions = query.query_full_lifecycle(start_date, end_date, **kwargs)
        
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"transactions_{timestamp}"
        
        if export_format == 'excel':
            path = f"exports/excel/{filename}.xlsx"
            return query.batch_export_to_excel(transactions, path)
        elif export_format == 'csv':
            path = f"exports/excel/{filename}.csv"
            return query.batch_export_to_csv(transactions, path)
        elif export_format == 'json':
            path = f"exports/excel/{filename}.json"
            return query.batch_export_to_json(transactions, path)
        else:
            raise ValueError(f"Unsupported export format: {export_format}")
    
    def backfill_historical_data(self, days: int = 90):
        logger.info(f"Starting historical data backfill for {days} days")
        
        fetcher = self._get('fetcher')
        rate_manager = self._get('rate_manager')
        
        with ThreadPoolExecutor(max_workers=2) as executor:
            executor.submit(fetcher.backfill_historical_data, days)
            executor.submit(rate_manager.backfill_historical_rates, days)
        
        logger.info("Historical data backfill initiated")
    
    def start_scheduler(self):
        logger.info("Starting task scheduler...")
        
        schedule.every().day.at("06:00").do(self.daily_data_fetch)
        schedule.every().day.at("07:00").do(self.daily_forecast)
        schedule.every().day.at("09:00").do(self.daily_risk_check)
        schedule.every().day.at("08:00").do(self.monthly_report)
        
        scheduler_thread = threading.Thread(target=self._run_scheduler, daemon=True)
        scheduler_thread.start()
        
        logger.info("Scheduler started")
        return scheduler_thread
    
    def _run_scheduler(self):
        while True:
            schedule.run_pending()
            time.sleep(60)
    
    def run_daily_tasks(self):
        logger.info("Running all daily tasks...")
        self.daily_data_fetch()
        time.sleep(5)
        self.daily_forecast()
        time.sleep(5)
        self.daily_risk_check()
        logger.info("All daily tasks completed")

_system_instance = None

def get_system() -> FundPoolSystem:
    global _system_instance
    if _system_instance is None:
        _system_instance = FundPoolSystem()
        _system_instance.initialize()
    return _system_instance
