import logging
from datetime import date, datetime
from typing import Dict, List, Tuple, Optional
from collections import defaultdict
from itertools import permutations

from src.database import get_db, FundGap, ExchangeProposal, AccountBalance
from src.banking.exchange_rates import ExchangeRateManager
from src.utils.helpers import generate_id, safe_json_dumps, round_currency

logger = logging.getLogger(__name__)

class ExchangePathFinder:
    def __init__(self, rate_manager: ExchangeRateManager):
        self.rate_manager = rate_manager
        self.fee_structure = {
            'direct': 0.001,
            'triangular': 0.0015,
        }
    
    def find_optimal_path(self, source_currency: str, target_currency: str,
                          amount: float, intermediate_currencies: List[str] = None) -> Dict:
        if intermediate_currencies is None:
            intermediate_currencies = ['USD', 'EUR', 'CNY']
        
        direct_path = self._evaluate_direct_path(source_currency, target_currency, amount)
        
        triangular_paths = []
        for intermediate in intermediate_currencies:
            if intermediate in (source_currency, target_currency):
                continue
            path = self._evaluate_triangular_path(
                source_currency, intermediate, target_currency, amount
            )
            triangular_paths.append(path)
        
        all_paths = [direct_path] + triangular_paths
        all_paths.sort(key=lambda x: x['total_cost'])
        
        return {
            'optimal_path': all_paths[0],
            'all_paths': all_paths,
            'recommendation': all_paths[0]
        }
    
    def _evaluate_direct_path(self, source: str, target: str, amount: float) -> Dict:
        rate = self.rate_manager.get_rate(source, target)
        fee_rate = self.fee_structure['direct']
        target_amount = amount * rate
        fee = target_amount * fee_rate
        net_amount = target_amount - fee
        
        return {
            'path_type': 'direct',
            'path': [source, target],
            'exchange_rate': rate,
            'source_amount': amount,
            'target_amount': round_currency(target_amount, target),
            'fee_amount': round_currency(fee, target),
            'fee_rate': fee_rate,
            'net_amount': round_currency(net_amount, target),
            'total_cost': round_currency(fee, target)
        }
    
    def _evaluate_triangular_path(self, source: str, intermediate: str,
                                   target: str, amount: float) -> Dict:
        rate1 = self.rate_manager.get_rate(source, intermediate)
        rate2 = self.rate_manager.get_rate(intermediate, target)
        effective_rate = rate1 * rate2
        
        fee_rate = self.fee_structure['triangular']
        intermediate_amount = amount * rate1
        target_amount = intermediate_amount * rate2
        fee = target_amount * fee_rate
        net_amount = target_amount - fee
        
        return {
            'path_type': 'triangular',
            'path': [source, intermediate, target],
            'exchange_rate': effective_rate,
            'intermediate_rate_1': rate1,
            'intermediate_rate_2': rate2,
            'source_amount': amount,
            'intermediate_amount': round_currency(intermediate_amount, intermediate),
            'target_amount': round_currency(target_amount, target),
            'fee_amount': round_currency(fee, target),
            'fee_rate': fee_rate,
            'net_amount': round_currency(net_amount, target),
            'total_cost': round_currency(fee, target)
        }

class ExchangeProposalGenerator:
    def __init__(self, rate_manager: ExchangeRateManager, 
                 currencies: List[str], base_currency: str = 'CNY'):
        self.rate_manager = rate_manager
        self.path_finder = ExchangePathFinder(rate_manager)
        self.currencies = currencies
        self.base_currency = base_currency
    
    def generate_proposals_for_gaps(self, gaps: List[Dict]) -> List[Dict]:
        logger.info(f"Generating exchange proposals for {len(gaps)} gaps")
        
        available_funds = self._get_available_funds()
        
        proposals = []
        for gap in gaps:
            if gap['severity'] in ('medium', 'high'):
                gap_proposals = self._generate_proposals_for_gap(gap, available_funds)
                proposals.extend(gap_proposals)
        
        self._save_proposals(proposals)
        logger.info(f"Generated {len(proposals)} exchange proposals")
        return proposals
    
    def _get_available_funds(self) -> Dict[str, float]:
        with get_db() as db:
            latest_balances = {}
            for account in db.query(AccountBalance).all():
                curr = account.currency
                if curr not in latest_balances or account.balance_date > latest_balances[curr][1]:
                    latest_balances[curr] = (account.available_balance, account.balance_date)
            
            return {curr: bal for curr, (bal, _) in latest_balances.items()}
    
    def _generate_proposals_for_gap(self, gap: Dict, available_funds: Dict) -> List[Dict]:
        target_currency = gap['currency']
        required_amount = gap['gap_amount'] * 1.2
        
        proposals = []
        source_candidates = [
            curr for curr in self.currencies
            if curr != target_currency and available_funds.get(curr, 0) > 0
        ]
        
        for source_currency in source_candidates:
            rate = self.rate_manager.get_rate(source_currency, target_currency)
            max_source_amount = available_funds[source_currency] * 0.8
            max_target_from_source = max_source_amount * rate
            
            if max_target_from_source < required_amount * 0.3:
                continue
            
            source_amount = min(max_source_amount, required_amount / rate)
            target_amount = source_amount * rate
            
            path_analysis = self.path_finder.find_optimal_path(
                source_currency, target_currency, source_amount
            )
            
            optimal = path_analysis['optimal_path']
            
            proposal = {
                'proposal_id': generate_id('EXC'),
                'source_currency': source_currency,
                'target_currency': target_currency,
                'source_amount': round_currency(source_amount, source_currency),
                'target_amount': round_currency(target_amount, target_currency),
                'exchange_rate': optimal['exchange_rate'],
                'fee_amount': optimal['fee_amount'],
                'fee_currency': target_currency,
                'total_cost': optimal['total_cost'],
                'execution_path': safe_json_dumps(optimal['path']),
                'cost_comparison': safe_json_dumps({
                    'paths': path_analysis['all_paths'],
                    'savings_vs_direct': self._calculate_savings(path_analysis['all_paths'])
                }),
                'gap_id': gap.get('id'),
                'status': 'pending',
                'created_by': 'system',
                'created_at': datetime.now()
            }
            proposals.append(proposal)
        
        proposals.sort(key=lambda x: x['total_cost'])
        return proposals[:3]
    
    def _calculate_savings(self, paths: List[Dict]) -> Dict:
        if len(paths) < 2:
            return {}
        
        direct_path = next((p for p in paths if p['path_type'] == 'direct'), None)
        optimal = paths[0]
        
        if direct_path and optimal != direct_path:
            savings = direct_path['total_cost'] - optimal['total_cost']
            return {
                'savings_amount': savings,
                'savings_percent': (savings / direct_path['total_cost']) * 100 if direct_path['total_cost'] > 0 else 0
            }
        
        return {}
    
    def _save_proposals(self, proposals: List[Dict]):
        with get_db() as db:
            for prop_data in proposals:
                existing = db.query(ExchangeProposal).filter_by(
                    proposal_id=prop_data['proposal_id']
                ).first()
                
                if not existing:
                    proposal = ExchangeProposal(
                        proposal_id=prop_data['proposal_id'],
                        source_currency=prop_data['source_currency'],
                        target_currency=prop_data['target_currency'],
                        source_amount=prop_data['source_amount'],
                        target_amount=prop_data['target_amount'],
                        exchange_rate=prop_data['exchange_rate'],
                        fee_amount=prop_data['fee_amount'],
                        fee_currency=prop_data['fee_currency'],
                        total_cost=prop_data['total_cost'],
                        execution_path=prop_data['execution_path'],
                        cost_comparison=prop_data['cost_comparison'],
                        status=prop_data['status'],
                        gap_id=prop_data.get('gap_id'),
                        created_by=prop_data['created_by']
                    )
                    db.add(proposal)
            
            db.commit()
    
    def get_proposal_details(self, proposal_id: str) -> Optional[Dict]:
        with get_db() as db:
            proposal = db.query(ExchangeProposal).filter_by(
                proposal_id=proposal_id
            ).first()
            
            if not proposal:
                return None
            
            return {
                'proposal_id': proposal.proposal_id,
                'source_currency': proposal.source_currency,
                'target_currency': proposal.target_currency,
                'source_amount': proposal.source_amount,
                'target_amount': proposal.target_amount,
                'exchange_rate': proposal.exchange_rate,
                'fee_amount': proposal.fee_amount,
                'total_cost': proposal.total_cost,
                'execution_path': proposal.execution_path,
                'cost_comparison': proposal.cost_comparison,
                'status': proposal.status,
                'created_at': proposal.created_at
            }
