from fastapi import FastAPI, HTTPException, Depends, Query
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from datetime import date, datetime, timedelta
from typing import List, Optional, Dict, Any
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.system import get_system
from src.database import get_db
from src.utils.helpers import safe_json_loads

app = FastAPI(title="企业级多币种资金池管理系统 API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.mount("/static", StaticFiles(directory="static"), name="static")

_system = None

def get_system_instance():
    global _system
    if _system is None:
        _system = get_system()
    return _system

@app.get("/")
async def root():
    return FileResponse("static/pages/index.html")

@app.get("/api/health")
async def health_check():
    return {"status": "ok", "timestamp": datetime.now().isoformat()}

@app.get("/api/dashboard/summary")
async def get_dashboard_summary():
    system = get_system_instance()
    rate_manager = system._components['rate_manager']
    
    with get_db() as db:
        from src.database import AccountBalance, BankAccount
        
        latest_balances = {}
        for account in db.query(BankAccount).all():
            balance = db.query(AccountBalance).filter(
                AccountBalance.account_id == account.id
            ).order_by(AccountBalance.balance_date.desc()).first()
            if balance:
                if account.currency not in latest_balances:
                    latest_balances[account.currency] = {
                        'balance': 0,
                        'available': 0,
                        'accounts': 0
                    }
                latest_balances[account.currency]['balance'] += balance.balance
                latest_balances[account.currency]['available'] += balance.available_balance
                latest_balances[account.currency]['accounts'] += 1
        
        total_balance_base = 0
        for curr, data in latest_balances.items():
            if curr == system.config['currencies']['base']:
                total_balance_base += data['balance']
            else:
                total_balance_base += rate_manager.convert(
                    data['balance'], curr, system.config['currencies']['base']
                )
        
        currencies_info = []
        for curr, data in latest_balances.items():
            volatility = rate_manager.calculate_volatility(curr, days=7)
            currencies_info.append({
                'currency': curr,
                'balance': round(data['balance'], 2),
                'available': round(data['available'], 2),
                'accounts': data['accounts'],
                'rate_to_base': round(rate_manager.get_rate(curr, system.config['currencies']['base']), 6),
                'volatility_7d': round(volatility.get('weekly', 0) * 100, 2)
            })
        
        from src.database import FundGap
        active_gaps = db.query(FundGap).filter(FundGap.status == 'open').count()
        
        from src.database import RiskAlert
        active_alerts = db.query(RiskAlert).filter(RiskAlert.status == 'active').count()
        
        from src.database import ExchangeProposal
        pending_approvals = db.query(ExchangeProposal).filter(
            ExchangeProposal.status == 'pending_approval'
        ).count()
    
    return {
        'total_balance_base': round(total_balance_base, 2),
        'base_currency': system.config['currencies']['base'],
        'currencies': currencies_info,
        'active_gaps': active_gaps,
        'active_alerts': active_alerts,
        'pending_approvals': pending_approvals,
        'update_time': datetime.now().isoformat()
    }

@app.get("/api/dashboard/fx-rates")
async def get_fx_rates():
    system = get_system_instance()
    rate_manager = system._components['rate_manager']
    base = system.config['currencies']['base']
    supported = system.config['currencies']['supported']
    
    rates = []
    for curr in supported:
        if curr == base:
            continue
        rate = rate_manager.get_rate(curr, base)
        hist = rate_manager.get_historical_rates(curr, base, date.today() - timedelta(days=7), date.today())
        
        rates.append({
            'currency': curr,
            'rate': round(rate, 6),
            'change_7d': round((hist[-1][1] - hist[0][1]) / hist[0][1] * 100, 2) if len(hist) > 1 else 0,
            'history': [{'date': d.isoformat(), 'rate': round(r, 6)} for d, r in hist]
        })
    
    return {'base_currency': base, 'rates': rates}

@app.get("/api/transactions")
async def get_transactions(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currencies: Optional[str] = None,
    account_ids: Optional[str] = None,
    txn_type: Optional[str] = None,
    min_amount: Optional[float] = None,
    max_amount: Optional[float] = None,
    category: Optional[str] = None,
    counterparty: Optional[str] = None,
    page: int = 1,
    page_size: int = 20
):
    system = get_system_instance()
    
    start_dt = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else None
    end_dt = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else None
    curr_list = currencies.split(',') if currencies else None
    acc_list = account_ids.split(',') if account_ids else None
    
    result = system.query_transactions(
        start_date=start_dt,
        end_date=end_dt,
        currencies=curr_list,
        account_ids=acc_list,
        txn_type=txn_type,
        min_amount=min_amount,
        max_amount=max_amount,
        category=category,
        counterparty=counterparty,
        page=page,
        page_size=page_size
    )
    
    return result

@app.get("/api/transactions/export")
async def export_transactions(
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    currencies: Optional[str] = None,
    account_ids: Optional[str] = None,
    format: str = 'excel'
):
    system = get_system_instance()
    
    start_dt = datetime.strptime(start_date, '%Y-%m-%d').date() if start_date else date.today() - timedelta(days=30)
    end_dt = datetime.strptime(end_date, '%Y-%m-%d').date() if end_date else date.today()
    curr_list = currencies.split(',') if currencies else None
    acc_list = account_ids.split(',') if account_ids else None
    
    path = system.export_transactions(
        start_date=start_dt,
        end_date=end_dt,
        export_format=format,
        currencies=curr_list
    )
    
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="Export file not found")
    
    filename = os.path.basename(path)
    return FileResponse(
        path,
        media_type='application/octet-stream',
        filename=filename
    )

@app.get("/api/forecast")
async def get_forecast():
    system = get_system_instance()
    forecaster = system._components['forecaster']
    
    with get_db() as db:
        from src.database import Forecast, FundGap
        
        latest_forecast_date = db.query(Forecast.forecast_date).order_by(
            Forecast.forecast_date.desc()
        ).first()
        
        if not latest_forecast_date:
            return {'forecast_date': None, 'forecasts': [], 'gaps': []}
        
        forecast_date = latest_forecast_date[0]
        
        forecasts = {}
        for fc in db.query(Forecast).filter(Forecast.forecast_date == forecast_date).all():
            if fc.currency not in forecasts:
                forecasts[fc.currency] = []
            forecasts[fc.currency].append({
                'target_date': fc.target_date.isoformat(),
                'inflow': fc.inflow,
                'outflow': fc.outflow,
                'net_flow': fc.net_flow,
                'projected_balance': fc.projected_balance,
                'confidence': fc.confidence
            })
        
        gaps = []
        for gap in db.query(FundGap).filter(FundGap.status == 'open').all():
            gaps.append({
                'id': gap.id,
                'currency': gap.currency,
                'gap_date': gap.gap_date.isoformat(),
                'gap_amount': gap.gap_amount,
                'projected_balance': gap.projected_balance,
                'threshold': gap.threshold,
                'severity': gap.severity
            })
        
        return {
            'forecast_date': forecast_date.isoformat(),
            'forecasts': forecasts,
            'gaps': gaps
        }

@app.get("/api/gaps/{gap_id}/proposals")
async def get_gap_proposals(gap_id: int):
    system = get_system_instance()
    
    with get_db() as db:
        from src.database import ExchangeProposal
        
        proposals = db.query(ExchangeProposal).filter(
            ExchangeProposal.gap_id == gap_id
        ).all()
        
        result = []
        for prop in proposals:
            result.append({
                'proposal_id': prop.proposal_id,
                'source_currency': prop.source_currency,
                'target_currency': prop.target_currency,
                'source_amount': prop.source_amount,
                'target_amount': prop.target_amount,
                'exchange_rate': prop.exchange_rate,
                'fee_amount': prop.fee_amount,
                'total_cost': prop.total_cost,
                'execution_path': safe_json_loads(prop.execution_path),
                'cost_comparison': safe_json_loads(prop.cost_comparison),
                'status': prop.status,
                'created_at': prop.created_at.isoformat()
            })
        
        return {'proposals': result}

@app.get("/api/proposals")
async def get_proposals(status: Optional[str] = None):
    system = get_system_instance()
    
    with get_db() as db:
        from src.database import ExchangeProposal, Approval
        
        query = db.query(ExchangeProposal)
        if status:
            query = query.filter(ExchangeProposal.status == status)
        
        proposals = query.order_by(ExchangeProposal.created_at.desc()).all()
        
        result = []
        for prop in proposals:
            approvals = db.query(Approval).filter(
                Approval.proposal_id == prop.proposal_id
            ).order_by(Approval.level).all()
            
            result.append({
                'proposal_id': prop.proposal_id,
                'source_currency': prop.source_currency,
                'target_currency': prop.target_currency,
                'source_amount': prop.source_amount,
                'target_amount': prop.target_amount,
                'exchange_rate': prop.exchange_rate,
                'fee_amount': prop.fee_amount,
                'total_cost': prop.total_cost,
                'status': prop.status,
                'execution_path': safe_json_loads(prop.execution_path),
                'cost_comparison': safe_json_loads(prop.cost_comparison),
                'approvals': [
                    {
                        'level': a.level,
                        'role': a.role,
                        'status': a.status,
                        'approver': a.approver,
                        'approved_at': a.approved_at.isoformat() if a.approved_at else None
                    }
                    for a in approvals
                ],
                'created_at': prop.created_at.isoformat()
            })
        
        return {'proposals': result}

@app.post("/api/proposals/{proposal_id}/approve")
async def approve_proposal(proposal_id: str, level: int, approver: str, comments: Optional[str] = None):
    system = get_system_instance()
    success = system.approve_proposal(proposal_id, level, approver, comments)
    if not success:
        raise HTTPException(status_code=400, detail="Approval failed")
    return {'status': 'success', 'proposal_id': proposal_id}

@app.post("/api/proposals/{proposal_id}/reject")
async def reject_proposal(proposal_id: str, level: int, approver: str, comments: Optional[str] = None):
    system = get_system_instance()
    success = system._components['approval_workflow'].reject(proposal_id, level, approver, comments)
    if not success:
        raise HTTPException(status_code=400, detail="Rejection failed")
    return {'status': 'success', 'proposal_id': proposal_id}

@app.post("/api/proposals/{proposal_id}/execute")
async def execute_exchange(proposal_id: str, source_account: str, target_account: str):
    system = get_system_instance()
    result = system.execute_exchange(proposal_id, source_account, target_account)
    if not result:
        raise HTTPException(status_code=400, detail="Execution failed")
    return {'status': 'success', 'execution': result}

@app.get("/api/accounts")
async def get_accounts():
    with get_db() as db:
        from src.database import BankAccount
        accounts = db.query(BankAccount).filter(BankAccount.status == 'active').all()
        return {
            'accounts': [
                {
                    'id': acc.id,
                    'name': acc.name,
                    'bank': acc.bank,
                    'currency': acc.currency,
                    'status': acc.status
                }
                for acc in accounts
            ]
        }

@app.post("/api/manual-adjustments")
async def create_manual_adjustment(
    currency: str,
    adjustment_type: str,
    amount: float,
    effective_date: str,
    description: str,
    counterparty: Optional[str] = None,
    category: Optional[str] = None
):
    system = get_system_instance()
    eff_date = datetime.strptime(effective_date, '%Y-%m-%d').date()
    
    adjustment = system.add_manual_adjustment(
        currency=currency,
        adjustment_type=adjustment_type,
        amount=amount,
        effective_date=eff_date,
        description=description,
        counterparty=counterparty,
        category=category
    )
    
    return {'status': 'success', 'adjustment': adjustment}

@app.get("/api/manual-adjustments")
async def get_manual_adjustments(currency: Optional[str] = None):
    system = get_system_instance()
    adjustments = system._components['manual_adjustments'].get_pending_adjustments(
        currency=currency
    )
    return {'adjustments': adjustments}

@app.get("/api/risk/alerts")
async def get_risk_alerts(status: Optional[str] = 'active'):
    with get_db() as db:
        from src.database import RiskAlert
        
        query = db.query(RiskAlert)
        if status:
            query = query.filter(RiskAlert.status == status)
        
        alerts = query.order_by(RiskAlert.created_at.desc()).all()
        
        result = []
        for alert in alerts:
            result.append({
                'alert_id': alert.alert_id,
                'currency': alert.currency,
                'alert_type': alert.alert_type,
                'severity': alert.severity,
                'message': alert.message,
                'metrics': safe_json_loads(alert.metrics),
                'hedge_recommendation': safe_json_loads(alert.hedge_recommendation),
                'status': alert.status,
                'created_at': alert.created_at.isoformat()
            })
        
        return {'alerts': result}

@app.get("/api/risk/exposures")
async def get_risk_exposures():
    with get_db() as db:
        from src.database import RiskExposure
        
        latest_date = db.query(RiskExposure.exposure_date).order_by(
            RiskExposure.exposure_date.desc()
        ).first()
        
        if not latest_date:
            return {'exposures': []}
        
        exposures = db.query(RiskExposure).filter(
            RiskExposure.exposure_date == latest_date[0]
        ).all()
        
        result = []
        for exp in exposures:
            result.append({
                'currency': exp.currency,
                'net_position': exp.net_position,
                'exposure_amount': exp.exposure_amount,
                'base_currency': exp.base_currency,
                'volatility_3d': exp.volatility_3d,
                'var_95': exp.var_95,
                'exposure_date': exp.exposure_date.isoformat()
            })
        
        return {'exposures': result}

@app.get("/api/reports")
async def get_reports():
    with get_db() as db:
        from src.database import MonthlyReport
        
        reports = db.query(MonthlyReport).order_by(MonthlyReport.report_month.desc()).all()
        
        result = []
        for report in reports:
            result.append({
                'report_id': report.report_id,
                'report_month': report.report_month,
                'pdf_path': report.pdf_path,
                'excel_path': report.excel_path,
                'created_at': report.created_at.isoformat()
            })
        
        return {'reports': result}

@app.get("/api/reports/{report_id}/download")
async def download_report(report_id: str, format: str = 'pdf'):
    with get_db() as db:
        from src.database import MonthlyReport
        
        report = db.query(MonthlyReport).filter(
            MonthlyReport.report_id == report_id
        ).first()
        
        if not report:
            raise HTTPException(status_code=404, detail="Report not found")
        
        path = report.pdf_path if format == 'pdf' else report.excel_path
        
        if not path or not os.path.exists(path):
            raise HTTPException(status_code=404, detail=f"{format.upper()} file not found")
        
        filename = os.path.basename(path)
        return FileResponse(
            path,
            media_type='application/octet-stream',
            filename=filename
        )

@app.post("/api/system/run-daily")
async def run_daily_tasks():
    system = get_system_instance()
    system.run_daily_tasks()
    return {'status': 'success', 'message': 'Daily tasks completed'}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
