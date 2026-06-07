# 企业级多币种资金池自动化管理系统

## 系统概述

这是一个功能完整的企业级多币种资金池自动化管理系统，支持：
- 多银行账户实时余额和交易流水抓取
- 7天资金缺口预测和智能预警
- 最优换汇路径计算和成本对比
- 多级审批工作流（超50万美金需CFO审批）
- 汇率风险敞口计算和对冲建议
- 手动录入大额预付/延期付款
- 月度分析报告自动生成（PDF/Excel）
- 全生命周期流水查询和批量导出
- 详细操作日志和企业群实时预警推送

## 目录结构

```
fund_pool_system/
├── config/
│   └── settings.yaml          # 系统配置文件
├── src/
│   ├── banking/               # 银行数据抓取模块
│   │   ├── fetcher.py         # 账户余额和流水抓取
│   │   └── exchange_rates.py  # 汇率管理
│   ├── forecasting/           # 资金预测模块
│   │   ├── forecaster.py      # 7天缺口预测
│   │   └── manual_adjustments.py  # 手动调整管理
│   ├── exchange/              # 换汇方案模块
│   │   └── proposal_generator.py  # 最优路径计算
│   ├── approval/              # 审批模块
│   │   └── workflow.py        # 多级审批和执行
│   ├── risk/                  # 风险管理模块
│   │   └── calculator.py      # 风险敞口和预警
│   ├── reports/               # 报告模块
│   │   └── generator.py       # 月度报告生成
│   ├── query/                 # 查询模块
│   │   └── transaction_query.py  # 流水查询导出
│   ├── notifications/         # 通知模块
│   │   └── sender.py          # 企业微信/邮件推送
│   ├── database/              # 数据库模块
│   │   ├── models.py          # 数据模型
│   │   └── db.py              # 数据库连接
│   ├── utils/                 # 工具模块
│   │   ├── helpers.py         # 通用工具函数
│   │   └── logger.py          # 日志配置
│   ├── config.py              # 配置加载
│   └── system.py              # 系统核心类
├── data/                      # 数据库存储
├── logs/                      # 日志文件
├── exports/                   # 导出文件
│   ├── pdf/
│   └── excel/
├── main.py                    # 命令行入口
├── example.py                 # 使用示例
├── requirements.txt           # Python依赖
└── .env.example               # 环境变量模板
```

## 安装步骤

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

依赖包说明：
- `sqlalchemy`: ORM数据库框架
- `pyyaml`: YAML配置文件解析
- `requests`: HTTP请求（银行API、汇率API）
- `schedule`: 定时任务调度
- `pandas`: 数据分析和预测
- `openpyxl`: Excel文件生成
- `reportlab`: PDF文件生成

### 2. 配置环境变量

复制 `.env.example` 为 `.env` 并填写实际配置：

```bash
cp .env.example .env
```

配置项说明：
- 各银行API密钥
- 企业微信Webhook地址（用于预警推送）

### 3. 初始化系统

```bash
python main.py init
```

## 命令行使用

### 基础命令

```bash
# 查看帮助
python main.py --help

# 初始化系统
python main.py init

# 回填历史数据（默认90天）
python main.py backfill --days 90

# 执行每日任务（抓取+预测+风险检查）
python main.py daily

# 单独生成资金预测
python main.py forecast

# 单独执行风险检查
python main.py risk-check

# 生成月度报告
python main.py monthly-report --year 2026 --month 6

# 启动定时调度器（后台运行）
python main.py start
```

### 交易流水导出

```bash
# 按日期范围导出Excel
python main.py export --start-date 2026-01-01 --end-date 2026-06-01 --format excel

# 指定币种导出CSV
python main.py export --start-date 2026-01-01 --end-date 2026-06-01 --format csv --currencies USD EUR CNY
```

### 手动调整管理

```bash
# 添加大额预付
python main.py add-adjustment --currency USD --type outflow --amount 50000 --date 2026-06-15 --description "大额预付供应商货款"
```

### 审批和执行

```bash
# 审批换汇方案
python main.py approve --proposal-id EXC123456 --level 1 --approver finance_manager --comments "同意"

# 执行换汇
python main.py execute --proposal-id EXC123456 --source-account BANK001 --target-account BANK003
```

## 定时任务说明

系统默认调度时间（可在 `config/settings.yaml` 修改）：

| 任务 | 时间 | 说明 |
|------|------|------|
| 数据抓取 | 每日 06:00 | 抓取所有账户余额和交易流水 |
| 资金预测 | 每日 07:00 | 生成未来7天资金预测和缺口预警 |
| 风险检查 | 每日 09:00 | 计算风险敞口，检测汇率波动 |
| 月度报告 | 每月1日 08:00 | 生成上月资金池分析报告 |

## 核心功能详解

### 1. 银行数据抓取

- 支持多银行API对接（目前使用模拟数据）
- 并发抓取，支持高吞吐
- 自动去重，避免重复记录
- 支持历史数据回填

### 2. 资金预测

- 基于加权移动平均模型（WMA）
- 考虑工作日/周末季节性
- 支持手动调整（大额预付/延期付款）
- 自动检测资金缺口并分级预警

### 3. 换汇方案优化

- 直汇和三角套汇路径对比
- 自动计算最优汇率路径
- 详细成本对比分析
- 节省金额量化展示

### 4. 多级审批

| 等值金额 | 审批角色 |
|----------|----------|
| < 5万 USD | 自动审批 |
| 5-50万 USD | 财务经理 |
| 50-200万 USD | 财务总监 |
| > 500万 USD | CFO |

### 5. 风险管理

- 每日计算各币种风险敞口
- 连续3天波动超2%自动预警
- 智能对冲建议（远期/期权/掉期）
- VaR（风险价值）量化分析

### 6. 报告生成

每月1号自动生成报告，包含：
- 资金归集率分析
- 换汇成本统计
- 汇率波动影响评估
- 风险敞口概览

支持导出为 PDF 和 Excel 格式。

## 高并发处理设计

1. **多线程并发抓取**：使用 `ThreadPoolExecutor` 并发处理多个银行账户
2. **批量数据库操作**：使用 `bulk_insert_mappings` 批量写入，提升性能
3. **数据库连接池**：配置 `pool_size=20, max_overflow=30` 应对高并发
4. **分页查询**：大数据量查询采用分页机制
5. **异步通知**：预警通知采用队列机制，不阻塞主流程

## 数据库表结构

系统包含以下核心数据表：
- `bank_accounts`: 银行账户配置
- `account_balances`: 账户余额历史
- `transactions`: 交易流水（支持数十万条记录）
- `exchange_rates`: 汇率历史数据
- `forecasts`: 资金预测记录
- `fund_gaps`: 资金缺口记录
- `exchange_proposals`: 换汇方案
- `approvals`: 审批记录
- `exchange_executions`: 换汇执行记录
- `risk_exposures`: 风险敞口记录
- `risk_alerts`: 风险预警记录
- `manual_adjustments`: 手动调整记录
- `monthly_reports`: 月度报告
- `system_logs`: 系统操作日志
- `notification_queue`: 通知队列

## 使用示例

运行完整示例：

```bash
python example.py
```

示例代码演示了：
1. 回填历史数据
2. 执行每日任务
3. 查询交易流水
4. 添加手动调整
5. 导出Excel报告
6. 生成月度分析报告

## Python代码调用示例

```python
from src.system import get_system
from datetime import date, timedelta

# 获取系统实例
system = get_system()

# 执行每日任务
system.run_daily_tasks()

# 查询交易
result = system.query_transactions(
    start_date=date.today() - timedelta(days=7),
    end_date=date.today(),
    currencies=['USD', 'CNY'],
    page_size=50
)

# 添加手动调整
adjustment = system.add_manual_adjustment(
    currency='EUR',
    adjustment_type='inflow',
    amount=100000,
    effective_date=date.today() + timedelta(days=5),
    description='预收客户货款'
)

# 导出数据
export_path = system.export_transactions(
    start_date=date(2026, 1, 1),
    end_date=date(2026, 6, 1),
    export_format='excel'
)
```

## 注意事项

1. **生产环境部署**：建议配合真实银行API使用，替换 `MockBankClient`
2. **数据安全**：敏感配置（API密钥）建议使用环境变量或密钥管理服务
3. **备份策略**：数据库建议每日备份，已配置自动备份功能
4. **监控告警**：系统异常会自动推送到企业群，建议配置值班机制
5. **汇率数据源**：生产环境建议接入专业汇率服务商API

## 扩展开发

### 接入真实银行API

在 `src/banking/fetcher.py` 中继承 `BankAPIClient` 类，实现：
- `fetch_balance()`: 账户余额查询接口
- `fetch_transactions()`: 交易流水查询接口

### 新增通知渠道

在 `src/notifications/sender.py` 中扩展 `NotificationSender` 类，支持：
- 钉钉机器人
- Slack
- 短信网关

### 扩展预测模型

在 `src/forecasting/forecaster.py` 中新增预测算法：
- ARIMA时间序列模型
- 机器学习预测模型
- 自定义业务规则模型
