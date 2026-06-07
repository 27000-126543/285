from datetime import datetime, date
from sqlalchemy import create_engine, Column, String, Float, Integer, DateTime, Date, Boolean, Text, ForeignKey, Index
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, relationship
import os

Base = declarative_base()

class BankAccount(Base):
    __tablename__ = 'bank_accounts'
    
    id = Column(String(50), primary_key=True)
    name = Column(String(200), nullable=False)
    bank = Column(String(100), nullable=False)
    currency = Column(String(10), nullable=False)
    status = Column(String(20), default='active')
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)

class AccountBalance(Base):
    __tablename__ = 'account_balances'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    account_id = Column(String(50), ForeignKey('bank_accounts.id'), nullable=False)
    currency = Column(String(10), nullable=False)
    balance = Column(Float, nullable=False)
    available_balance = Column(Float, nullable=False)
    balance_date = Column(Date, nullable=False)
    fetched_at = Column(DateTime, default=datetime.now)
    
    __table_args__ = (
        Index('idx_balance_account_date', 'account_id', 'balance_date'),
    )

class Transaction(Base):
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    txn_id = Column(String(100), unique=True, nullable=False)
    account_id = Column(String(50), ForeignKey('bank_accounts.id'), nullable=False)
    currency = Column(String(10), nullable=False)
    amount = Column(Float, nullable=False)
    txn_type = Column(String(20), nullable=False)
    counterparty = Column(String(200))
    description = Column(String(500))
    txn_date = Column(Date, nullable=False)
    txn_time = Column(DateTime)
    status = Column(String(20), default='completed')
    category = Column(String(100))
    is_manual = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)
    
    __table_args__ = (
        Index('idx_txn_account_date', 'account_id', 'txn_date'),
        Index('idx_txn_currency_date', 'currency', 'txn_date'),
        Index('idx_txn_date', 'txn_date'),
    )

class ExchangeRate(Base):
    __tablename__ = 'exchange_rates'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    base_currency = Column(String(10), nullable=False)
    target_currency = Column(String(10), nullable=False)
    rate = Column(Float, nullable=False)
    rate_date = Column(Date, nullable=False)
    source = Column(String(50))
    fetched_at = Column(DateTime, default=datetime.now)
    
    __table_args__ = (
        Index('idx_rate_pair_date', 'base_currency', 'target_currency', 'rate_date', unique=True),
    )

class Forecast(Base):
    __tablename__ = 'forecasts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    currency = Column(String(10), nullable=False)
    forecast_date = Column(Date, nullable=False)
    target_date = Column(Date, nullable=False)
    inflow = Column(Float, default=0)
    outflow = Column(Float, default=0)
    net_flow = Column(Float, default=0)
    projected_balance = Column(Float)
    confidence = Column(Float)
    model_version = Column(String(50))
    created_at = Column(DateTime, default=datetime.now)
    
    __table_args__ = (
        Index('idx_forecast_currency_target', 'currency', 'target_date'),
    )

class FundGap(Base):
    __tablename__ = 'fund_gaps'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    currency = Column(String(10), nullable=False)
    gap_date = Column(Date, nullable=False)
    gap_amount = Column(Float, nullable=False)
    projected_balance = Column(Float)
    threshold = Column(Float)
    severity = Column(String(20))
    status = Column(String(20), default='open')
    created_at = Column(DateTime, default=datetime.now)
    resolved_at = Column(DateTime)

class ExchangeProposal(Base):
    __tablename__ = 'exchange_proposals'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    proposal_id = Column(String(50), unique=True, nullable=False)
    source_currency = Column(String(10), nullable=False)
    target_currency = Column(String(10), nullable=False)
    source_amount = Column(Float, nullable=False)
    target_amount = Column(Float, nullable=False)
    exchange_rate = Column(Float, nullable=False)
    fee_amount = Column(Float, default=0)
    fee_currency = Column(String(10))
    total_cost = Column(Float)
    execution_path = Column(Text)
    cost_comparison = Column(Text)
    status = Column(String(20), default='pending')
    gap_id = Column(Integer, ForeignKey('fund_gaps.id'))
    created_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)

class Approval(Base):
    __tablename__ = 'approvals'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    proposal_id = Column(String(50), ForeignKey('exchange_proposals.proposal_id'), nullable=False)
    level = Column(Integer, nullable=False)
    role = Column(String(50), nullable=False)
    approver = Column(String(100))
    status = Column(String(20), default='pending')
    comments = Column(String(500))
    approved_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)

class ExchangeExecution(Base):
    __tablename__ = 'exchange_executions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    execution_id = Column(String(50), unique=True, nullable=False)
    proposal_id = Column(String(50), ForeignKey('exchange_proposals.proposal_id'), nullable=False)
    source_account_id = Column(String(50), ForeignKey('bank_accounts.id'))
    target_account_id = Column(String(50), ForeignKey('bank_accounts.id'))
    source_amount = Column(Float, nullable=False)
    target_amount = Column(Float, nullable=False)
    executed_rate = Column(Float, nullable=False)
    fee = Column(Float, default=0)
    status = Column(String(20), default='processing')
    executed_at = Column(DateTime)
    settled_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)

class RiskExposure(Base):
    __tablename__ = 'risk_exposures'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    currency = Column(String(10), nullable=False)
    exposure_date = Column(Date, nullable=False)
    net_position = Column(Float, nullable=False)
    exposure_amount = Column(Float, nullable=False)
    base_currency = Column(String(10), nullable=False)
    volatility_3d = Column(Float)
    var_95 = Column(Float)
    created_at = Column(DateTime, default=datetime.now)

class RiskAlert(Base):
    __tablename__ = 'risk_alerts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_id = Column(String(50), unique=True, nullable=False)
    currency = Column(String(10), nullable=False)
    alert_type = Column(String(50), nullable=False)
    severity = Column(String(20), nullable=False)
    message = Column(String(500))
    metrics = Column(Text)
    hedge_recommendation = Column(Text)
    status = Column(String(20), default='active')
    created_at = Column(DateTime, default=datetime.now)
    resolved_at = Column(DateTime)

class HedgeTransaction(Base):
    __tablename__ = 'hedge_transactions'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    hedge_id = Column(String(50), unique=True, nullable=False)
    currency = Column(String(10), nullable=False)
    hedge_type = Column(String(50), nullable=False)
    notional_amount = Column(Float, nullable=False)
    strike_rate = Column(Float)
    maturity_date = Column(Date)
    cost = Column(Float)
    status = Column(String(20), default='active')
    created_at = Column(DateTime, default=datetime.now)

class ManualAdjustment(Base):
    __tablename__ = 'manual_adjustments'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    adjustment_id = Column(String(50), unique=True, nullable=False)
    currency = Column(String(10), nullable=False)
    adjustment_type = Column(String(20), nullable=False)
    amount = Column(Float, nullable=False)
    effective_date = Column(Date, nullable=False)
    description = Column(String(500))
    counterparty = Column(String(200))
    category = Column(String(100))
    created_by = Column(String(100))
    is_applied = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)

class MonthlyReport(Base):
    __tablename__ = 'monthly_reports'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    report_id = Column(String(50), unique=True, nullable=False)
    report_month = Column(String(7), nullable=False)
    report_data = Column(Text)
    pdf_path = Column(String(500))
    excel_path = Column(String(500))
    generated_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)

class SystemLog(Base):
    __tablename__ = 'system_logs'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    log_id = Column(String(50), unique=True, nullable=False)
    log_type = Column(String(50), nullable=False)
    module = Column(String(100), nullable=False)
    action = Column(String(100), nullable=False)
    status = Column(String(20), nullable=False)
    message = Column(String(1000))
    details = Column(Text)
    executed_by = Column(String(100))
    created_at = Column(DateTime, default=datetime.now)
    
    __table_args__ = (
        Index('idx_log_type_created', 'log_type', 'created_at'),
        Index('idx_log_module', 'module'),
    )

class NotificationQueue(Base):
    __tablename__ = 'notification_queue'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    notification_id = Column(String(50), unique=True, nullable=False)
    channel = Column(String(50), nullable=False)
    recipient = Column(String(200))
    title = Column(String(200), nullable=False)
    content = Column(String(2000), nullable=False)
    priority = Column(String(20), default='normal')
    status = Column(String(20), default='pending')
    sent_at = Column(DateTime)
    error_message = Column(String(500))
    created_at = Column(DateTime, default=datetime.now)

def init_db(db_path='data/fund_pool.db'):
    os.makedirs(os.path.dirname(db_path), exist_ok=True)
    engine = create_engine(f'sqlite:///{db_path}', echo=False, pool_size=20, max_overflow=30)
    Base.metadata.create_all(engine)
    Session = sessionmaker(bind=engine)
    return Session, engine
