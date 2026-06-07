import logging
from datetime import date, datetime
from typing import Dict, List, Optional
from sqlalchemy import and_

from src.database import get_db, ManualAdjustment, Forecast
from src.utils.helpers import generate_id, round_currency

logger = logging.getLogger(__name__)

class ManualAdjustmentManager:
    def __init__(self, currencies: List[str]):
        self.currencies = currencies
    
    def create_adjustment(self, currency: str, adjustment_type: str,
                          amount: float, effective_date: date,
                          description: str, counterparty: str = None,
                          category: str = None, created_by: str = 'manual') -> Dict:
        logger.info(f"Creating manual adjustment: {adjustment_type} {amount} {currency} on {effective_date}")
        
        if currency not in self.currencies:
            raise ValueError(f"Unsupported currency: {currency}")
        
        if adjustment_type not in ('inflow', 'outflow'):
            raise ValueError("adjustment_type must be 'inflow' or 'outflow'")
        
        adjustment_id = generate_id('ADJ')
        amount = abs(amount)
        
        with get_db() as db:
            adjustment = ManualAdjustment(
                adjustment_id=adjustment_id,
                currency=currency,
                adjustment_type=adjustment_type,
                amount=round_currency(amount, currency),
                effective_date=effective_date,
                description=description,
                counterparty=counterparty,
                category=category,
                created_by=created_by,
                is_applied=False
            )
            db.add(adjustment)
            db.commit()
            
            logger.info(f"Created manual adjustment {adjustment_id}")
            return {
                'adjustment_id': adjustment_id,
                'currency': currency,
                'adjustment_type': adjustment_type,
                'amount': round_currency(amount, currency),
                'effective_date': effective_date,
                'description': description,
                'is_applied': False
            }
    
    def apply_adjustment(self, adjustment_id: str) -> bool:
        logger.info(f"Applying manual adjustment {adjustment_id}")
        
        with get_db() as db:
            adjustment = db.query(ManualAdjustment).filter_by(
                adjustment_id=adjustment_id
            ).first()
            
            if not adjustment:
                logger.error(f"Adjustment {adjustment_id} not found")
                return False
            
            if adjustment.is_applied:
                logger.warning(f"Adjustment {adjustment_id} already applied")
                return False
            
            adjustment.is_applied = True
            db.commit()
            
            logger.info(f"Applied adjustment {adjustment_id}")
            return True
    
    def cancel_adjustment(self, adjustment_id: str) -> bool:
        logger.info(f"Cancelling manual adjustment {adjustment_id}")
        
        with get_db() as db:
            adjustment = db.query(ManualAdjustment).filter_by(
                adjustment_id=adjustment_id
            ).first()
            
            if not adjustment:
                logger.error(f"Adjustment {adjustment_id} not found")
                return False
            
            if adjustment.is_applied:
                adjustment.is_applied = False
                db.commit()
                logger.info(f"Cancelled adjustment {adjustment_id}")
                return True
            
            db.delete(adjustment)
            db.commit()
            logger.info(f"Deleted adjustment {adjustment_id}")
            return True
    
    def get_pending_adjustments(self, currency: str = None,
                                start_date: date = None,
                                end_date: date = None) -> List[Dict]:
        with get_db() as db:
            query = db.query(ManualAdjustment).filter(
                ManualAdjustment.is_applied == True
            )
            
            if currency:
                query = query.filter(ManualAdjustment.currency == currency)
            
            if start_date:
                query = query.filter(ManualAdjustment.effective_date >= start_date)
            
            if end_date:
                query = query.filter(ManualAdjustment.effective_date <= end_date)
            
            adjustments = query.order_by(ManualAdjustment.effective_date).all()
            
            return [
                {
                    'adjustment_id': adj.adjustment_id,
                    'currency': adj.currency,
                    'adjustment_type': adj.adjustment_type,
                    'amount': adj.amount,
                    'effective_date': adj.effective_date,
                    'description': adj.description,
                    'counterparty': adj.counterparty,
                    'category': adj.category,
                    'created_by': adj.created_by,
                    'created_at': adj.created_at
                }
                for adj in adjustments
            ]
    
    def record_large_payment(self, currency: str, amount: float,
                             payment_date: date, counterparty: str,
                             description: str, payment_type: str = 'outflow') -> Dict:
        if payment_type == 'inflow':
            adj_type = 'inflow'
            desc_prefix = '大额预收'
        else:
            adj_type = 'outflow'
            desc_prefix = '大额预付'
        
        return self.create_adjustment(
            currency=currency,
            adjustment_type=adj_type,
            amount=amount,
            effective_date=payment_date,
            description=f"{desc_prefix}: {description}",
            counterparty=counterparty,
            category='large_payment',
            created_by='manual_entry'
        )
    
    def record_deferred_payment(self, original_date: date, new_date: date,
                                currency: str, amount: float,
                                counterparty: str, description: str) -> Dict:
        outflow_adj = self.create_adjustment(
            currency=currency,
            adjustment_type='outflow',
            amount=amount,
            effective_date=original_date,
            description=f"取消原付款: {description}",
            counterparty=counterparty,
            category='deferred_payment',
            created_by='manual_entry'
        )
        self.apply_adjustment(outflow_adj['adjustment_id'])
        
        inflow_adj = self.create_adjustment(
            currency=currency,
            adjustment_type='inflow',
            amount=amount,
            effective_date=original_date,
            description=f"冲销原付款: {description}",
            counterparty=counterparty,
            category='deferred_payment',
            created_by='manual_entry'
        )
        self.apply_adjustment(inflow_adj['adjustment_id'])
        
        new_payment = self.create_adjustment(
            currency=currency,
            adjustment_type='outflow',
            amount=amount,
            effective_date=new_date,
            description=f"延期付款: {description}",
            counterparty=counterparty,
            category='deferred_payment',
            created_by='manual_entry'
        )
        self.apply_adjustment(new_payment['adjustment_id'])
        
        return new_payment
