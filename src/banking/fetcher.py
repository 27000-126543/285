import logging
from abc import ABC, abstractmethod
from datetime import date, datetime, timedelta
from typing import List, Dict, Any, Tuple
import random
import time
from concurrent.futures import ThreadPoolExecutor, as_completed

from src.database import get_db, BankAccount, AccountBalance, Transaction
from src.utils.helpers import generate_id, hash_transaction, round_currency

logger = logging.getLogger(__name__)

class BankAPIClient(ABC):
    def __init__(self, account_config: Dict[str, Any]):
        self.account_config = account_config
        self.account_id = account_config['id']
        self.currency = account_config['currency']
        self.bank = account_config['bank']
    
    @abstractmethod
    def fetch_balance(self) -> Dict[str, Any]:
        pass
    
    @abstractmethod
    def fetch_transactions(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        pass

class MockBankClient(BankAPIClient):
    def fetch_balance(self) -> Dict[str, Any]:
        base_balance = {
            'USD': 500000 + random.uniform(-50000, 50000),
            'EUR': 400000 + random.uniform(-40000, 40000),
            'CNY': 3000000 + random.uniform(-300000, 300000),
            'HKD': 2000000 + random.uniform(-200000, 200000),
            'JPY': 50000000 + random.uniform(-5000000, 5000000),
            'GBP': 300000 + random.uniform(-30000, 30000),
        }
        balance = base_balance.get(self.currency, 100000)
        return {
            'account_id': self.account_id,
            'currency': self.currency,
            'balance': round_currency(balance, self.currency),
            'available_balance': round_currency(balance * 0.95, self.currency),
            'balance_date': date.today(),
        }
    
    def fetch_transactions(self, start_date: date, end_date: date) -> List[Dict[str, Any]]:
        transactions = []
        current_date = start_date
        counterparties = [
            '供应商A科技有限公司', '供应商B贸易有限公司', '客户C制造集团',
            '客户D电子科技', '物流E运输公司', '咨询F管理公司',
            '材料G实业公司', '服务H外包集团', '薪资发放', '税费缴纳',
            '水电费用', '办公费用', '差旅费报销', '设备采购'
        ]
        categories = {
            'in': ['销售收入', '投资收益', '退款收入', '利息收入', '政府补贴'],
            'out': ['原材料采购', '工资福利', '税费支出', '物流费用', '咨询费用',
                    '办公费用', '差旅费用', '设备采购', '研发费用', '营销费用']
        }
        
        while current_date <= end_date:
            num_txns = random.randint(30, 80)
            for i in range(num_txns):
                is_inflow = random.random() < 0.45
                txn_type = 'in' if is_inflow else 'out'
                
                if self.currency == 'JPY':
                    amount = random.uniform(50000, 5000000)
                elif self.currency in ('USD', 'EUR', 'GBP'):
                    amount = random.uniform(500, 50000)
                else:
                    amount = random.uniform(5000, 500000)
                
                amount = round_currency(amount, self.currency)
                if not is_inflow:
                    amount = -amount
                
                category = random.choice(categories[txn_type])
                counterparty = random.choice(counterparties)
                
                txn_hour = random.randint(8, 18)
                txn_minute = random.randint(0, 59)
                txn_time = datetime.combine(current_date, datetime.min.time()).replace(
                    hour=txn_hour, minute=txn_minute
                )
                
                txn_data = {
                    'account_id': self.account_id,
                    'currency': self.currency,
                    'amount': amount,
                    'txn_type': txn_type,
                    'counterparty': counterparty,
                    'description': f'{category} - {counterparty}',
                    'txn_date': current_date,
                    'txn_time': txn_time,
                    'category': category,
                }
                txn_data['txn_id'] = hash_transaction(txn_data)
                transactions.append(txn_data)
            
            current_date += timedelta(days=1)
        
        return transactions

class BankAPIFactory:
    _clients = {}
    
    @classmethod
    def get_client(cls, account_config: Dict[str, Any]) -> BankAPIClient:
        bank = account_config['bank']
        account_id = account_config['id']
        key = f"{bank}_{account_id}"
        
        if key not in cls._clients:
            cls._clients[key] = MockBankClient(account_config)
        
        return cls._clients[key]

class BankDataFetcher:
    def __init__(self, accounts_config: List[Dict[str, Any]], max_workers: int = 5):
        self.accounts_config = accounts_config
        self.max_workers = max_workers
        self._init_accounts_in_db()
    
    def _init_accounts_in_db(self):
        with get_db() as db:
            for acc_config in self.accounts_config:
                existing = db.query(BankAccount).filter_by(id=acc_config['id']).first()
                if not existing:
                    account = BankAccount(
                        id=acc_config['id'],
                        name=acc_config['name'],
                        bank=acc_config['bank'],
                        currency=acc_config['currency'],
                        status='active'
                    )
                    db.add(account)
            db.commit()
    
    def fetch_all_balances(self) -> List[Dict[str, Any]]:
        logger.info("Starting balance fetch for all accounts")
        results = []
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_account = {
                executor.submit(self._fetch_single_balance, acc): acc['id']
                for acc in self.accounts_config
            }
            
            for future in as_completed(future_to_account):
                account_id = future_to_account[future]
                try:
                    result = future.result()
                    results.append(result)
                    logger.info(f"Fetched balance for {account_id}: {result['balance']} {result['currency']}")
                except Exception as e:
                    logger.error(f"Failed to fetch balance for {account_id}: {e}")
        
        self._save_balances(results)
        logger.info(f"Completed balance fetch: {len(results)} accounts processed")
        return results
    
    def _fetch_single_balance(self, account_config: Dict[str, Any]) -> Dict[str, Any]:
        client = BankAPIFactory.get_client(account_config)
        return client.fetch_balance()
    
    def _save_balances(self, balances: List[Dict[str, Any]]):
        with get_db() as db:
            for bal_data in balances:
                balance = AccountBalance(
                    account_id=bal_data['account_id'],
                    currency=bal_data['currency'],
                    balance=bal_data['balance'],
                    available_balance=bal_data['available_balance'],
                    balance_date=bal_data['balance_date'],
                )
                db.add(balance)
            db.commit()
    
    def fetch_all_transactions(self, days: int = 1) -> Dict[str, List[Dict[str, Any]]]:
        logger.info(f"Starting transaction fetch for last {days} days")
        end_date = date.today()
        start_date = end_date - timedelta(days=days - 1)
        results = {}
        
        with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
            future_to_account = {
                executor.submit(self._fetch_single_transactions, acc, start_date, end_date): acc['id']
                for acc in self.accounts_config
            }
            
            for future in as_completed(future_to_account):
                account_id = future_to_account[future]
                try:
                    txns = future.result()
                    results[account_id] = txns
                    logger.info(f"Fetched {len(txns)} transactions for {account_id}")
                except Exception as e:
                    logger.error(f"Failed to fetch transactions for {account_id}: {e}")
        
        total_txns = sum(len(txns) for txns in results.values())
        self._save_transactions(results)
        logger.info(f"Completed transaction fetch: {total_txns} total transactions")
        return results
    
    def _fetch_single_transactions(self, account_config: Dict[str, Any], 
                                   start_date: date, end_date: date) -> List[Dict[str, Any]]:
        client = BankAPIFactory.get_client(account_config)
        return client.fetch_transactions(start_date, end_date)
    
    def _save_transactions(self, all_txns: Dict[str, List[Dict[str, Any]]]):
        with get_db() as db:
            for account_id, txns in all_txns.items():
                if not txns:
                    continue
                
                existing_ids = set(
                    r[0] for r in db.query(Transaction.txn_id).filter(
                        Transaction.txn_id.in_([t['txn_id'] for t in txns])
                    ).all()
                )
                
                new_txns = [t for t in txns if t['txn_id'] not in existing_ids]
                
                for txn_data in new_txns:
                    txn = Transaction(
                        txn_id=txn_data['txn_id'],
                        account_id=txn_data['account_id'],
                        currency=txn_data['currency'],
                        amount=txn_data['amount'],
                        txn_type=txn_data['txn_type'],
                        counterparty=txn_data.get('counterparty'),
                        description=txn_data.get('description'),
                        txn_date=txn_data['txn_date'],
                        txn_time=txn_data.get('txn_time'),
                        category=txn_data.get('category'),
                        status='completed',
                    )
                    db.add(txn)
                
                db.commit()
                logger.info(f"Saved {len(new_txns)} new transactions for {account_id}")
    
    def backfill_historical_data(self, days: int = 90):
        logger.info(f"Starting historical data backfill for {days} days")
        batch_days = 7
        current_end = date.today()
        current_start = current_end - timedelta(days=batch_days - 1)
        
        while current_start > date.today() - timedelta(days=days):
            if current_start < date.today() - timedelta(days=days):
                current_start = date.today() - timedelta(days=days)
            
            logger.info(f"Backfilling {current_start} to {current_end}")
            
            with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
                future_to_account = {
                    executor.submit(self._fetch_single_transactions, acc, current_start, current_end): acc['id']
                    for acc in self.accounts_config
                }
                
                batch_results = {}
                for future in as_completed(future_to_account):
                    account_id = future_to_account[future]
                    try:
                        txns = future.result()
                        batch_results[account_id] = txns
                    except Exception as e:
                        logger.error(f"Backfill error for {account_id}: {e}")
                
                self._save_transactions(batch_results)
            
            current_end = current_start - timedelta(days=1)
            current_start = current_end - timedelta(days=batch_days - 1)
            time.sleep(0.5)
        
        logger.info("Historical data backfill completed")
