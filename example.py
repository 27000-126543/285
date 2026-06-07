#!/usr/bin/env python3
import sys
import os
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.utils.logger import setup_logging
from src.system import get_system

def example_usage():
    setup_logging()
    
    system = get_system()
    
    print("=" * 60)
    print("企业级多币种资金池自动化管理系统 - 使用示例")
    print("=" * 60)
    
    print("\n1. 回填历史数据 (90天)...")
    system.backfill_historical_data(days=90)
    
    print("\n2. 执行每日任务...")
    system.run_daily_tasks()
    
    print("\n3. 查询交易流水...")
    end_date = date.today()
    start_date = end_date - timedelta(days=7)
    result = system.query_transactions(
        start_date=start_date,
        end_date=end_date,
        page=1,
        page_size=10
    )
    print(f"   共找到 {result['total_count']} 条交易，显示前10条:")
    for txn in result['data']:
        print(f"   - {txn['txn_date']} | {txn['currency']} {txn['amount']:,.2f} | {txn['category']}")
    
    print("\n4. 添加手动调整（大额预付）...")
    adj = system.add_manual_adjustment(
        currency='USD',
        adjustment_type='outflow',
        amount=50000,
        effective_date=date.today() + timedelta(days=3),
        description='大额预付供应商货款',
        counterparty='供应商A科技有限公司',
        category='large_payment'
    )
    print(f"   调整ID: {adj['adjustment_id']}")
    
    print("\n5. 导出交易流水...")
    export_path = system.export_transactions(
        start_date=start_date,
        end_date=end_date,
        export_format='excel'
    )
    print(f"   导出路径: {export_path}")
    
    print("\n6. 生成月度报告...")
    today = date.today()
    report = system._components['report_generator'].generate_monthly_report(
        year=today.year,
        month=today.month
    )
    print(f"   报告ID: {report['report_id']}")
    print(f"   Excel: {report['excel_path']}")
    print(f"   PDF: {report['pdf_path']}")
    
    print("\n" + "=" * 60)
    print("示例运行完成！")
    print("=" * 60)

if __name__ == '__main__':
    example_usage()
