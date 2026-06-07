import logging
from datetime import datetime
from typing import Dict, List, Optional, Tuple

from src.database import get_db, ExchangeProposal, Approval, ExchangeExecution
from src.banking.exchange_rates import ExchangeRateManager
from src.utils.helpers import generate_id, round_currency

logger = logging.getLogger(__name__)

class ApprovalWorkflow:
    def __init__(self, approval_levels: List[Dict], base_currency: str = 'USD',
                 auto_approve_below: float = 10000, rate_manager: ExchangeRateManager = None):
        self.approval_levels = sorted(approval_levels, key=lambda x: x['threshold'])
        self.base_currency = base_currency
        self.auto_approve_below = auto_approve_below
        self.rate_manager = rate_manager
    
    def _calculate_approval_level(self, amount: float, currency: str) -> Tuple[int, str]:
        if self.rate_manager:
            amount_base = self.rate_manager.convert(amount, currency, self.base_currency)
        else:
            amount_base = amount
        
        level = 0
        role = self.approval_levels[0]['role'] if self.approval_levels else 'financial_manager'
        
        for i, lvl in enumerate(self.approval_levels):
            if amount_base >= lvl['threshold']:
                level = i + 1
                role = lvl['role']
        
        return level, role
    
    def _get_required_approvals(self, amount: float, currency: str) -> List[Dict]:
        if self.rate_manager:
            amount_base = self.rate_manager.convert(amount, currency, self.base_currency)
        else:
            amount_base = amount
        
        required = []
        for i, lvl in enumerate(self.approval_levels):
            if amount_base >= lvl['threshold']:
                required.append({
                    'level': i + 1,
                    'role': lvl['role'],
                    'threshold': lvl['threshold']
                })
        
        if not required:
            required.append({
                'level': 1,
                'role': self.approval_levels[0]['role'] if self.approval_levels else 'financial_manager',
                'threshold': 0
            })
        
        return required
    
    def initiate_approvals(self, proposal_id: str) -> List[Dict]:
        logger.info(f"Initiating approval workflow for proposal {proposal_id}")
        
        with get_db() as db:
            proposal = db.query(ExchangeProposal).filter_by(
                proposal_id=proposal_id
            ).first()
            
            if not proposal:
                logger.error(f"Proposal {proposal_id} not found")
                return []
            
            if self.rate_manager:
                amount_base = self.rate_manager.convert(
                    proposal.source_amount, proposal.source_currency, self.base_currency
                )
            else:
                amount_base = proposal.source_amount
            
            if amount_base < self.auto_approve_below:
                logger.info(f"Proposal {proposal_id} auto-approved (amount below threshold)")
                self._auto_approve(proposal_id, db)
                return []
            
            required_approvals = self._get_required_approvals(
                proposal.source_amount, proposal.source_currency
            )
            
            created_approvals = []
            for approval_req in required_approvals:
                existing = db.query(Approval).filter(
                    Approval.proposal_id == proposal_id,
                    Approval.level == approval_req['level']
                ).first()
                
                if not existing:
                    approval = Approval(
                        proposal_id=proposal_id,
                        level=approval_req['level'],
                        role=approval_req['role'],
                        status='pending'
                    )
                    db.add(approval)
                    created_approvals.append({
                        'proposal_id': proposal_id,
                        'level': approval_req['level'],
                        'role': approval_req['role'],
                        'status': 'pending'
                    })
            
            proposal.status = 'pending_approval'
            db.commit()
            
            logger.info(f"Created {len(created_approvals)} approval records for proposal {proposal_id}")
            return created_approvals
    
    def _auto_approve(self, proposal_id: str, db):
        approval = Approval(
            proposal_id=proposal_id,
            level=0,
            role='system',
            status='approved',
            approver='auto_approve',
            comments='自动审批：金额低于阈值',
            approved_at=datetime.now()
        )
        db.add(approval)
        
        proposal = db.query(ExchangeProposal).filter_by(proposal_id=proposal_id).first()
        if proposal:
            proposal.status = 'approved'
    
    def approve(self, proposal_id: str, level: int, approver: str,
                comments: str = None) -> bool:
        logger.info(f"Approving proposal {proposal_id} at level {level} by {approver}")
        
        with get_db() as db:
            approval = db.query(Approval).filter(
                Approval.proposal_id == proposal_id,
                Approval.level == level
            ).first()
            
            if not approval:
                logger.error(f"Approval record not found for {proposal_id} level {level}")
                return False
            
            if approval.status != 'pending':
                logger.warning(f"Approval already {approval.status} for {proposal_id} level {level}")
                return False
            
            approval.status = 'approved'
            approval.approver = approver
            approval.comments = comments
            approval.approved_at = datetime.now()
            
            if self._check_all_approved(proposal_id, db):
                proposal = db.query(ExchangeProposal).filter_by(
                    proposal_id=proposal_id
                ).first()
                if proposal:
                    proposal.status = 'approved'
                    logger.info(f"Proposal {proposal_id} fully approved")
            
            db.commit()
            return True
    
    def reject(self, proposal_id: str, level: int, approver: str,
               comments: str = None) -> bool:
        logger.info(f"Rejecting proposal {proposal_id} at level {level} by {approver}")
        
        with get_db() as db:
            approval = db.query(Approval).filter(
                Approval.proposal_id == proposal_id,
                Approval.level == level
            ).first()
            
            if not approval:
                logger.error(f"Approval record not found for {proposal_id} level {level}")
                return False
            
            approval.status = 'rejected'
            approval.approver = approver
            approval.comments = comments
            approval.approved_at = datetime.now()
            
            proposal = db.query(ExchangeProposal).filter_by(
                proposal_id=proposal_id
            ).first()
            if proposal:
                proposal.status = 'rejected'
            
            db.commit()
            return True
    
    def _check_all_approved(self, proposal_id: str, db) -> bool:
        approvals = db.query(Approval).filter(
            Approval.proposal_id == proposal_id,
            Approval.level > 0
        ).all()
        
        if not approvals:
            return True
        
        return all(a.status == 'approved' for a in approvals)
    
    def get_approval_status(self, proposal_id: str) -> Dict:
        with get_db() as db:
            proposal = db.query(ExchangeProposal).filter_by(
                proposal_id=proposal_id
            ).first()
            
            if not proposal:
                return {}
            
            approvals = db.query(Approval).filter(
                Approval.proposal_id == proposal_id
            ).order_by(Approval.level).all()
            
            return {
                'proposal_id': proposal_id,
                'status': proposal.status,
                'approvals': [
                    {
                        'level': a.level,
                        'role': a.role,
                        'status': a.status,
                        'approver': a.approver,
                        'approved_at': a.approved_at,
                        'comments': a.comments
                    }
                    for a in approvals
                ]
            }

class ExchangeExecutor:
    def __init__(self, rate_manager: ExchangeRateManager, accounts_config: List[Dict]):
        self.rate_manager = rate_manager
        self.accounts_config = accounts_config
    
    def execute_exchange(self, proposal_id: str, source_account_id: str,
                         target_account_id: str) -> Optional[Dict]:
        logger.info(f"Executing exchange for proposal {proposal_id}")
        
        with get_db() as db:
            proposal = db.query(ExchangeProposal).filter_by(
                proposal_id=proposal_id
            ).first()
            
            if not proposal:
                logger.error(f"Proposal {proposal_id} not found")
                return None
            
            if proposal.status != 'approved':
                logger.error(f"Proposal {proposal_id} not approved (status: {proposal.status})")
                return None
            
            execution_id = generate_id('EXE')
            
            executed_rate = self.rate_manager.get_rate(
                proposal.source_currency, proposal.target_currency
            )
            target_amount = proposal.source_amount * executed_rate
            fee = target_amount * 0.001
            
            execution = ExchangeExecution(
                execution_id=execution_id,
                proposal_id=proposal_id,
                source_account_id=source_account_id,
                target_account_id=target_account_id,
                source_amount=proposal.source_amount,
                target_amount=round_currency(target_amount, proposal.target_currency),
                executed_rate=executed_rate,
                fee=round_currency(fee, proposal.target_currency),
                status='processing',
                executed_at=datetime.now()
            )
            db.add(execution)
            
            proposal.status = 'executing'
            db.commit()
            
            logger.info(f"Exchange execution initiated: {execution_id}")
            
            self._settle_execution(execution_id, db)
            
            return {
                'execution_id': execution_id,
                'proposal_id': proposal_id,
                'source_amount': proposal.source_amount,
                'target_amount': round_currency(target_amount, proposal.target_currency),
                'executed_rate': executed_rate,
                'fee': round_currency(fee, proposal.target_currency),
                'status': 'completed'
            }
    
    def _settle_execution(self, execution_id: str, db):
        execution = db.query(ExchangeExecution).filter_by(
            execution_id=execution_id
        ).first()
        
        if execution:
            execution.status = 'completed'
            execution.settled_at = datetime.now()
            
            proposal = db.query(ExchangeProposal).filter_by(
                proposal_id=execution.proposal_id
            ).first()
            if proposal:
                proposal.status = 'completed'
            
            db.commit()
            logger.info(f"Execution {execution_id} settled")
    
    def get_execution_status(self, execution_id: str) -> Optional[Dict]:
        with get_db() as db:
            execution = db.query(ExchangeExecution).filter_by(
                execution_id=execution_id
            ).first()
            
            if not execution:
                return None
            
            return {
                'execution_id': execution.execution_id,
                'proposal_id': execution.proposal_id,
                'source_amount': execution.source_amount,
                'target_amount': execution.target_amount,
                'executed_rate': execution.executed_rate,
                'fee': execution.fee,
                'status': execution.status,
                'executed_at': execution.executed_at,
                'settled_at': execution.settled_at
            }
