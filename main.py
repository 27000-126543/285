#!/usr/bin/env python3
import sys
import os
import argparse
import logging
from datetime import date, datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from src.utils.logger import setup_logging
from src.system import get_system

def main():
    parser = argparse.ArgumentParser(description='企业级多币种资金池自动化管理系统')
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    subparsers.add_parser('init', help='初始化系统和数据库')
    
    backfill_parser = subparsers.add_parser('backfill', help='回填历史数据')
    backfill_parser.add_argument('--days', type=int, default=90, help='回填天数')
    
    subparsers.add_parser('daily', help='执行每日任务')
    
    subparsers.add_parser('forecast', help='生成资金预测')
    
    subparsers.add_parser('risk-check', help='执行风险检查')
    
    report_parser = subparsers.add_parser('monthly-report', help='生成月度报告')
    report_parser.add_argument('--year', type=int, help='年份')
    report_parser.add_argument('--month', type=int, help='月份')
    
    export_parser = subparsers.add_parser('export', help='导出交易流水')
    export_parser.add_argument('--start-date', type=str, required=True, help='开始日期 (YYYY-MM-DD)')
    export_parser.add_argument('--end-date', type=str, required=True, help='结束日期 (YYYY-MM-DD)')
    export_parser.add_argument('--format', type=str, default='excel', choices=['excel', 'csv', 'json'])
    export_parser.add_argument('--currencies', type=str, nargs='*', help='币种筛选')
    
    adj_parser = subparsers.add_parser('add-adjustment', help='添加手动调整')
    adj_parser.add_argument('--currency', type=str, required=True)
    adj_parser.add_argument('--type', type=str, required=True, choices=['inflow', 'outflow'])
    adj_parser.add_argument('--amount', type=float, required=True)
    adj_parser.add_argument('--date', type=str, required=True, help='生效日期 (YYYY-MM-DD)')
    adj_parser.add_argument('--description', type=str, required=True)
    
    approve_parser = subparsers.add_parser('approve', help='审批换汇方案')
    approve_parser.add_argument('--proposal-id', type=str, required=True)
    approve_parser.add_argument('--level', type=int, required=True)
    approve_parser.add_argument('--approver', type=str, required=True)
    approve_parser.add_argument('--comments', type=str)
    
    execute_parser = subparsers.add_parser('execute', help='执行换汇')
    execute_parser.add_argument('--proposal-id', type=str, required=True)
    execute_parser.add_argument('--source-account', type=str, required=True)
    execute_parser.add_argument('--target-account', type=str, required=True)
    
    subparsers.add_parser('start', help='启动定时任务调度器')
    
    args = parser.parse_args()
    
    setup_logging()
    logger = logging.getLogger(__name__)
    
    system = get_system()
    
    if args.command == 'init':
        logger.info("系统初始化完成")
        print("[OK] 系统初始化完成")
        
    elif args.command == 'backfill':
        logger.info(f"开始回填 {args.days} 天历史数据")
        system.backfill_historical_data(days=args.days)
        print(f"[OK] 历史数据回填已启动 ({args.days}天)")
        
    elif args.command == 'daily':
        logger.info("执行每日任务")
        system.run_daily_tasks()
        print("[OK] 每日任务执行完成")
        
    elif args.command == 'forecast':
        logger.info("生成资金预测")
        system.daily_forecast()
        print("[OK] 资金预测生成完成")
        
    elif args.command == 'risk-check':
        logger.info("执行风险检查")
        system.daily_risk_check()
        print("[OK] 风险检查完成")
        
    elif args.command == 'monthly-report':
        today = date.today()
        year = args.year or today.year
        month = args.month or today.month
        logger.info(f"生成 {year}-{month:02d} 月度报告")
        report = system._components['report_generator'].generate_monthly_report(year, month)
        print(f"[OK] 月度报告生成完成")
        print(f"  Excel: {report['excel_path']}")
        print(f"  PDF: {report['pdf_path']}")
        
    elif args.command == 'export':
        start_date = datetime.strptime(args.start_date, '%Y-%m-%d').date()
        end_date = datetime.strptime(args.end_date, '%Y-%m-%d').date()
        logger.info(f"导出交易流水: {start_date} 至 {end_date}")
        path = system.export_transactions(
            start_date=start_date,
            end_date=end_date,
            export_format=args.format,
            currencies=args.currencies
        )
        print(f"[OK] 导出完成: {path}")
        
    elif args.command == 'add-adjustment':
        effective_date = datetime.strptime(args.date, '%Y-%m-%d').date()
        adjustment = system.add_manual_adjustment(
            currency=args.currency,
            adjustment_type=args.type,
            amount=args.amount,
            effective_date=effective_date,
            description=args.description
        )
        print(f"[OK] 手动调整已添加: {adjustment['adjustment_id']}")
        
    elif args.command == 'approve':
        success = system.approve_proposal(
            proposal_id=args.proposal_id,
            level=args.level,
            approver=args.approver,
            comments=args.comments
        )
        if success:
            print(f"[OK] 审批完成")
        else:
            print("[ERROR] 审批失败")
            
    elif args.command == 'execute':
        result = system.execute_exchange(
            proposal_id=args.proposal_id,
            source_account_id=args.source_account,
            target_account_id=args.target_account
        )
        if result:
            print(f"[OK] 换汇执行完成: {result['execution_id']}")
        else:
            print("[ERROR] 换汇执行失败")
            
    elif args.command == 'start':
        logger.info("启动定时任务调度器")
        system.start_scheduler()
        print("✓ 定时任务调度器已启动 (按 Ctrl+C 停止)")
        print("  - 每日 06:00: 数据抓取")
        print("  - 每日 07:00: 资金预测")
        print("  - 每日 09:00: 风险检查")
        print("  - 每月1日 08:00: 月度报告")
        
        try:
            while True:
                import time
                time.sleep(3600)
        except KeyboardInterrupt:
            print("\n调度器已停止")
            
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
