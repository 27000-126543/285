import logging
import json
import requests
from datetime import datetime
from typing import Dict, List, Optional
from sqlalchemy import and_

from src.database import get_db, NotificationQueue, SystemLog
from src.utils.helpers import generate_id

logger = logging.getLogger(__name__)

class NotificationSender:
    def __init__(self, wechat_webhook_url: str = None, email_config: Dict = None):
        self.wechat_webhook_url = wechat_webhook_url
        self.email_config = email_config or {}
    
    def send_alert(self, title: str, content: str, priority: str = 'normal',
                   channels: List[str] = None) -> List[Dict]:
        if channels is None:
            channels = ['wechat']
        
        results = []
        for channel in channels:
            notification_id = generate_id('NOT')
            result = {
                'notification_id': notification_id,
                'channel': channel,
                'status': 'pending',
                'error': None
            }
            
            try:
                if channel == 'wechat' and self.wechat_webhook_url:
                    sent = self._send_wechat(title, content)
                    result['status'] = 'sent' if sent else 'failed'
                elif channel == 'email':
                    result['status'] = 'queued'
                else:
                    result['status'] = 'skipped'
                    result['error'] = f'Channel {channel} not configured'
            except Exception as e:
                result['status'] = 'failed'
                result['error'] = str(e)
                logger.error(f"Failed to send {channel} notification: {e}")
            
            self._save_notification(result, title, content, priority)
            results.append(result)
        
        return results
    
    def _send_wechat(self, title: str, content: str) -> bool:
        if not self.wechat_webhook_url:
            return False
        
        if self.wechat_webhook_url.startswith('${'):
            logger.warning("WeChat webhook URL not configured, skipping notification")
            return False
        
        if not self.wechat_webhook_url.startswith('http'):
            logger.warning(f"Invalid WeChat webhook URL format: {self.wechat_webhook_url}")
            return False
        
        message = {
            "msgtype": "markdown",
            "markdown": {
                "content": f"## {title}\n\n{content}\n\n> 发送时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
            }
        }
        
        try:
            response = requests.post(
                self.wechat_webhook_url,
                json=message,
                headers={'Content-Type': 'application/json'},
                timeout=10
            )
            if response.status_code == 200:
                result = response.json()
                if result.get('errcode') == 0:
                    logger.info("WeChat notification sent successfully")
                    return True
            logger.warning(f"WeChat notification failed: {response.text}")
            return False
        except Exception as e:
            logger.error(f"WeChat notification error: {e}")
            return False
    
    def _save_notification(self, result: Dict, title: str, content: str, priority: str):
        with get_db() as db:
            notification = NotificationQueue(
                notification_id=result['notification_id'],
                channel=result['channel'],
                title=title,
                content=content[:2000],
                priority=priority,
                status=result['status'],
                error_message=result.get('error')
            )
            if result['status'] == 'sent':
                notification.sent_at = datetime.now()
            db.add(notification)
            db.commit()
    
    def send_risk_alert(self, alert_data: Dict) -> List[Dict]:
        title = f"【汇率风险预警】{alert_data['currency']} - {alert_data['severity'].upper()}"
        content = f"""
**预警类型**: {alert_data['alert_type']}
**涉及币种**: {alert_data['currency']}
**严重程度**: {alert_data['severity']}
**预警消息**: {alert_data['message']}

> 请相关人员及时关注并评估对冲策略。
        """
        return self.send_alert(title, content.strip(), priority='high')
    
    def send_gap_alert(self, gap_data: Dict) -> List[Dict]:
        title = f"【资金缺口预警】{gap_data['currency']} - {gap_data['severity'].upper()}"
        content = f"""
**缺口币种**: {gap_data['currency']}
**缺口日期**: {gap_data['gap_date']}
**缺口金额**: {gap_data['gap_amount']:,.2f} {gap_data['currency']}
**预计余额**: {gap_data['projected_balance']:,.2f} {gap_data['currency']}
**严重程度**: {gap_data['severity']}

> 请及时安排换汇或资金调拨。
        """
        return self.send_alert(title, content.strip(), priority='high')
    
    def send_approval_notification(self, proposal_id: str, level: int, role: str) -> List[Dict]:
        title = f"【审批通知】换汇方案待审批"
        content = f"""
**方案编号**: {proposal_id}
**审批级别**: 第 {level} 级
**审批角色**: {role}

> 请您及时登录系统进行审批。
        """
        return self.send_alert(title, content.strip(), priority='normal')
    
    def send_system_alert(self, module: str, action: str, error_msg: str) -> List[Dict]:
        title = f"【系统异常】{module} - {action}"
        content = f"""
**模块**: {module}
**操作**: {action}
**错误信息**: {error_msg}

> 请技术人员及时排查处理。
        """
        return self.send_alert(title, content.strip(), priority='high')

class SystemLogger:
    @staticmethod
    def log_action(log_type: str, module: str, action: str, status: str,
                   message: str = None, details: Dict = None, executed_by: str = 'system'):
        with get_db() as db:
            log = SystemLog(
                log_id=generate_id('LOG'),
                log_type=log_type,
                module=module,
                action=action,
                status=status,
                message=message,
                details=json.dumps(details, ensure_ascii=False) if details else None,
                executed_by=executed_by
            )
            db.add(log)
            db.commit()
        
        if status == 'error':
            logger.error(f"[{log_type}] {module}.{action}: {message}")
        else:
            logger.info(f"[{log_type}] {module}.{action}: {message}")
    
    @staticmethod
    def log_fetch(account_id: str, status: str, txn_count: int = 0, error_msg: str = None):
        SystemLogger.log_action(
            log_type='data_fetch',
            module='banking',
            action='fetch_transactions',
            status=status,
            message=f"账户 {account_id}: {txn_count} 条交易" if status == 'success' else error_msg,
            details={'account_id': account_id, 'txn_count': txn_count, 'error': error_msg}
        )
    
    @staticmethod
    def log_exchange(proposal_id: str, status: str, details: Dict = None):
        SystemLogger.log_action(
            log_type='exchange',
            module='exchange',
            action='execute_exchange',
            status=status,
            message=f"方案 {proposal_id}: {status}",
            details=details,
            executed_by='system'
        )
    
    @staticmethod
    def log_approval(proposal_id: str, level: int, approver: str, status: str):
        SystemLogger.log_action(
            log_type='approval',
            module='approval',
            action='approval_action',
            status=status,
            message=f"方案 {proposal_id} 第{level}级审批: {status}",
            details={'proposal_id': proposal_id, 'level': level, 'approver': approver},
            executed_by=approver
        )
    
    @staticmethod
    def get_recent_logs(log_type: str = None, module: str = None,
                        status: str = None, limit: int = 100) -> List[Dict]:
        with get_db() as db:
            query = db.query(SystemLog)
            
            if log_type:
                query = query.filter(SystemLog.log_type == log_type)
            if module:
                query = query.filter(SystemLog.module == module)
            if status:
                query = query.filter(SystemLog.status == status)
            
            logs = query.order_by(SystemLog.created_at.desc()).limit(limit).all()
            
            return [
                {
                    'log_id': log.log_id,
                    'log_type': log.log_type,
                    'module': log.module,
                    'action': log.action,
                    'status': log.status,
                    'message': log.message,
                    'details': json.loads(log.details) if log.details else None,
                    'executed_by': log.executed_by,
                    'created_at': log.created_at
                }
                for log in logs
            ]
