"""
Celery async tasks for Bitcoin Mixer
"""
from celery import Celery
from celery.schedules import crontab
from datetime import datetime, timedelta
import logging
from models import db, MixingTransaction, TransactionStatus, SecurityAlert
from mixing_service import MixingService
from config import Config

logger = logging.getLogger(__name__)

# Initialize Celery
celery = Celery('mixer_tasks')
celery.config_from_object(Config)

# Configure Celery beat schedule
celery.conf.beat_schedule = {
    'check-pending-payments': {
        'task': 'tasks.check_pending_payments',
        'schedule': 30.0,  # Every 30 seconds
    },
    'process-mixing-rounds': {
        'task': 'tasks.process_mixing_rounds',
        'schedule': 60.0,  # Every minute
    },
    'send-scheduled-outputs': {
        'task': 'tasks.send_scheduled_outputs',
        'schedule': 60.0,  # Every minute
    },
    'cleanup-old-transactions': {
        'task': 'tasks.cleanup_old_transactions',
        'schedule': crontab(hour=2, minute=0),  # Daily at 2 AM
    },
}


@celery.task
def check_pending_payments():
    """Check for incoming payments on pending transactions"""
    try:
        mixing_service = MixingService(Config)
        
        # Get all pending transactions
        pending_txs = MixingTransaction.query.filter_by(
            status=TransactionStatus.PENDING
        ).filter(
            MixingTransaction.created_at >= datetime.utcnow() - timedelta(hours=24)
        ).all()
        
        for tx in pending_txs:
            if mixing_service.check_incoming_payment(str(tx.id)):
                logger.info(f"Payment received for transaction {tx.id}")
                # Start mixing process
                process_mixing.delay(str(tx.id))
        
        return f"Checked {len(pending_txs)} pending transactions"
        
    except Exception as e:
        logger.error(f"Error checking pending payments: {e}")
        return f"Error: {e}"


@celery.task
def process_mixing(transaction_id: str):
    """Process mixing rounds for a transaction"""
    try:
        mixing_service = MixingService(Config)
        transaction = MixingTransaction.query.get(transaction_id)
        
        if not transaction or transaction.status != TransactionStatus.MIXING:
            return f"Transaction {transaction_id} not ready for mixing"
        
        # Perform mixing rounds
        while transaction.mixing_rounds_completed < Config.MIXING_ROUNDS:
            if not mixing_service.perform_mixing_round(transaction_id):
                return f"Mixing failed for transaction {transaction_id}"
            
            # Add random delay between rounds (1-5 minutes)
            import time
            time.sleep(random.randint(60, 300))
        
        return f"Mixing completed for transaction {transaction_id}"
        
    except Exception as e:
        logger.error(f"Error processing mixing: {e}")
        return f"Error: {e}"


@celery.task
def process_mixing_rounds():
    """Process all active mixing transactions"""
    try:
        mixing_service = MixingService(Config)
        
        # Get transactions in mixing state
        mixing_txs = MixingTransaction.query.filter_by(
            status=TransactionStatus.MIXING
        ).all()
        
        for tx in mixing_txs:
            if tx.mixing_rounds_completed < Config.MIXING_ROUNDS:
                mixing_service.perform_mixing_round(str(tx.id))
        
        return f"Processed {len(mixing_txs)} mixing transactions"
        
    except Exception as e:
        logger.error(f"Error processing mixing rounds: {e}")
        return f"Error: {e}"


@celery.task
def send_scheduled_outputs():
    """Send output transactions that are due"""
    try:
        mixing_service = MixingService(Config)
        
        # Get completed transactions ready for output
        ready_txs = MixingTransaction.query.filter(
            MixingTransaction.status == TransactionStatus.COMPLETED,
            MixingTransaction.scheduled_output_time <= datetime.utcnow(),
            MixingTransaction.output_txid.is_(None)
        ).all()
        
        for tx in ready_txs:
            if mixing_service.send_output_transaction(str(tx.id)):
                logger.info(f"Output sent for transaction {tx.id}")
            else:
                logger.error(f"Failed to send output for transaction {tx.id}")
        
        return f"Processed {len(ready_txs)} output transactions"
        
    except Exception as e:
        logger.error(f"Error sending scheduled outputs: {e}")
        return f"Error: {e}"


@celery.task
def cleanup_old_transactions():
    """Clean up old transaction data for privacy"""
    try:
        # Delete transactions older than 30 days
        cutoff_date = datetime.utcnow() - timedelta(days=30)
        
        old_txs = MixingTransaction.query.filter(
            MixingTransaction.created_at < cutoff_date
        ).all()
        
        count = len(old_txs)
        for tx in old_txs:
            db.session.delete(tx)
        
        # Also clean up old security alerts
        old_alerts = SecurityAlert.query.filter(
            SecurityAlert.created_at < cutoff_date
        ).all()
        
        for alert in old_alerts:
            db.session.delete(alert)
        
        db.session.commit()
        
        logger.info(f"Cleaned up {count} old transactions and {len(old_alerts)} alerts")
        return f"Cleaned up {count} transactions"
        
    except Exception as e:
        logger.error(f"Error cleaning up old transactions: {e}")
        db.session.rollback()
        return f"Error: {e}"


@celery.task
def send_security_alert(alert_type: str, severity: str, details: dict):
    """Send security alert via Telegram"""
    try:
        from mixer_service import send_telegram_message
        
        alert = SecurityAlert(
            alert_type=alert_type,
            severity=severity,
            details=details
        )
        db.session.add(alert)
        
        if Config.TELEGRAM_BOT_TOKEN and Config.TELEGRAM_CHAT_ID:
            message = f"🚨 Security Alert: {alert_type}\n"
            message += f"Severity: {severity}\n"
            message += f"Details: {details}"
            
            if send_telegram_message(Config.TELEGRAM_BOT_TOKEN, Config.TELEGRAM_CHAT_ID, message):
                alert.telegram_sent = True
        
        db.session.commit()
        return "Alert sent"
        
    except Exception as e:
        logger.error(f"Error sending security alert: {e}")
        return f"Error: {e}"

