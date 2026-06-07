#!/usr/bin/env python3
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.system import get_system
from datetime import date, datetime, timedelta
import logging

logging.basicConfig(level=logging.INFO)

def init_test_data():
    print("=" * 60)
    print("初始化测试数据...")
    print("=" * 60)
    
    system = get_system()
    
    print("\n1. 回填90天历史数据...")
    system.backfill_historical_data(days=90)
    
    print("\n2. 执行每日任务...")
    system.run_daily_tasks()
    
    print("\n3. 生成月度报告...")
    today = date.today()
    report = system._components['report_generator'].generate_monthly_report(today.year, today.month)
    
    print("\n4. 验证数据库数据...")
    from src.database import get_db, Transaction, AccountBalance, Forecast, FundGap, ExchangeProposal
    
    with get_db() as db:
        txn_count = db.query(Transaction).count()
        balance_count = db.query(AccountBalance).count()
        forecast_count = db.query(Forecast).count()
        gap_count = db.query(FundGap).count()
        proposal_count = db.query(ExchangeProposal).count()
        
        print(f"   - 交易记录: {txn_count} 条")
        print(f"   - 余额记录: {balance_count} 条")
        print(f"   - 预测记录: {forecast_count} 条")
        print(f"   - 资金缺口: {gap_count} 条")
        print(f"   - 换汇方案: {proposal_count} 条")
    
    print("\n" + "=" * 60)
    print("测试数据初始化完成！")
    print("=" * 60)
    print(f"\n月度报告已生成:")
    print(f"  Excel: {report['excel_path']}")
    print(f"  PDF: {report['pdf_path']}")

if __name__ == '__main__':
    init_test_data()
