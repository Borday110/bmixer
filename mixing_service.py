"""
Bitcoin Mixing Service - Core mixing logic
"""
import random
import time
from datetime import datetime, timedelta
from decimal import Decimal
from typing import List, Dict, Optional, Tuple
import logging
from bitcoinrpc.authproxy import AuthServiceProxy
from models import db, MixingTransaction, MixingPool, MixingLog, TransactionStatus
from celery import Celery

logger = logging.getLogger(__name__)


class MixingService:
    """Core mixing service implementation"""
    
    def __init__(self, config):
        self.config = config
        self.rpc = self._init_rpc()
        
    def _init_rpc(self) -> AuthServiceProxy:
        """Initialize Bitcoin RPC connection"""
        try:
            rpc_url = f"http://{self.config.RPC_USER}:{self.config.RPC_PASS}@{self.config.RPC_HOST}:{self.config.RPC_PORT}"
            return AuthServiceProxy(rpc_url)
        except Exception as e:
            logger.error(f"Failed to initialize RPC: {e}")
            raise
    
    def validate_bitcoin_address(self, address: str) -> bool:
        """Validate Bitcoin address using RPC"""
        try:
            result = self.rpc.validateaddress(address)
            return result.get('isvalid', False)
        except Exception as e:
            logger.error(f"Address validation failed: {e}")
            return False
    
    def get_mixing_pool_addresses(self, count: int = 5) -> List[str]:
        """Get available mixing pool addresses"""
        pools = MixingPool.query.filter_by(is_active=True)\
            .order_by(MixingPool.last_used.asc())\
            .limit(count)\
            .all()
        
        if len(pools) < count:
            # Generate new pool addresses if needed
            for _ in range(count - len(pools)):
                new_address = self.rpc.getnewaddress("mixing_pool")
                pool = MixingPool(address=new_address)
                db.session.add(pool)
            db.session.commit()
            
            # Re-query to get all addresses
            pools = MixingPool.query.filter_by(is_active=True)\
                .order_by(MixingPool.last_used.asc())\
                .limit(count)\
                .all()
        
        return [pool.address for pool in pools]
    
    def create_mixing_transaction(self, 
                                input_amount: Decimal,
                                output_address: str,
                                session_id: str,
                                ip_hash: str,
                                user_agent_hash: str) -> MixingTransaction:
        """Create a new mixing transaction"""
        # Calculate fees
        fee_amount = input_amount * Decimal(str(self.config.FEE_PERCENT))
        output_amount = input_amount - fee_amount
        
        # Generate unique input address for this transaction
        input_address = self.rpc.getnewaddress("mixer_input")
        
        # Calculate scheduled output time (random delay)
        delay_minutes = random.randint(
            self.config.DELAY_MINUTES_MIN,
            self.config.DELAY_MINUTES_MAX
        )
        scheduled_output_time = datetime.utcnow() + timedelta(minutes=delay_minutes)
        
        # Create transaction record
        transaction = MixingTransaction(
            session_id=session_id,
            input_amount=input_amount,
            fee_amount=fee_amount,
            output_amount=output_amount,
            input_address=input_address,
            output_address=output_address,
            ip_hash=ip_hash,
            user_agent_hash=user_agent_hash,
            scheduled_output_time=scheduled_output_time
        )
        
        db.session.add(transaction)
        db.session.commit()
        
        # Log creation
        self._log_action(transaction.id, "CREATED", {
            "input_amount": str(input_amount),
            "output_address": output_address,
            "delay_minutes": delay_minutes
        })
        
        return transaction
    
    def check_incoming_payment(self, transaction_id: str) -> bool:
        """Check if payment has been received"""
        transaction = MixingTransaction.query.get(transaction_id)
        if not transaction:
            return False
        
        try:
            # Check for incoming transactions
            received = self.rpc.getreceivedbyaddress(transaction.input_address, 0)
            
            if received >= float(transaction.input_amount):
                # Get transaction ID
                txlist = self.rpc.listreceivedbyaddress(0, True, True, transaction.input_address)
                if txlist and txlist[0]['txids']:
                    transaction.input_txid = txlist[0]['txids'][0]
                
                transaction.status = TransactionStatus.MIXING
                transaction.mixing_started_at = datetime.utcnow()
                db.session.commit()
                
                self._log_action(transaction.id, "PAYMENT_RECEIVED", {
                    "amount": str(received),
                    "txid": transaction.input_txid
                })
                
                return True
        except Exception as e:
            logger.error(f"Error checking payment: {e}")
            
        return False
    
    def perform_mixing_round(self, transaction_id: str) -> bool:
        """Perform one round of mixing"""
        transaction = MixingTransaction.query.get(transaction_id)
        if not transaction or transaction.status != TransactionStatus.MIXING:
            return False
        
        try:
            # Get mixing pool addresses
            pool_addresses = self.get_mixing_pool_addresses()
            
            # Select random pool address
            mixing_address = random.choice(pool_addresses)
            
            # Move coins to mixing pool
            if transaction.mixing_rounds_completed == 0:
                # First round - move from input to pool
                from_address = transaction.input_address
            else:
                # Subsequent rounds - move between pools
                from_address = transaction.mixing_address
            
            # Create raw transaction (simplified - in production use proper UTXO management)
            amount_to_send = float(transaction.output_amount) * 0.99  # Small fee for each hop
            
            # In production, implement proper transaction creation
            # For now, we'll simulate the mixing
            transaction.mixing_address = mixing_address
            transaction.mixing_rounds_completed += 1
            
            self._log_action(transaction.id, f"MIXING_ROUND_{transaction.mixing_rounds_completed}", {
                "from": from_address,
                "to": mixing_address,
                "amount": str(amount_to_send)
            })
            
            # Check if mixing is complete
            if transaction.mixing_rounds_completed >= self.config.MIXING_ROUNDS:
                transaction.status = TransactionStatus.COMPLETED
                transaction.completed_at = datetime.utcnow()
                
                # Schedule final output
                self._schedule_output_transaction(transaction)
            
            db.session.commit()
            return True
            
        except Exception as e:
            logger.error(f"Mixing round failed: {e}")
            transaction.status = TransactionStatus.FAILED
            transaction.error_message = str(e)
            db.session.commit()
            return False
    
    def _schedule_output_transaction(self, transaction: MixingTransaction):
        """Schedule the final output transaction"""
        # In production, this would create a Celery task
        # For now, we'll just mark it as ready
        self._log_action(transaction.id, "OUTPUT_SCHEDULED", {
            "scheduled_time": transaction.scheduled_output_time.isoformat(),
            "output_address": transaction.output_address
        })
    
    def send_output_transaction(self, transaction_id: str) -> bool:
        """Send the final mixed coins to output address"""
        transaction = MixingTransaction.query.get(transaction_id)
        if not transaction or transaction.status != TransactionStatus.COMPLETED:
            return False
        
        try:
            # Send transaction
            txid = self.rpc.sendtoaddress(
                transaction.output_address,
                float(transaction.output_amount)
            )
            
            transaction.output_txid = txid
            db.session.commit()
            
            self._log_action(transaction.id, "OUTPUT_SENT", {
                "txid": txid,
                "amount": str(transaction.output_amount),
                "address": transaction.output_address
            })
            
            return True
            
        except Exception as e:
            logger.error(f"Output transaction failed: {e}")
            transaction.error_message = str(e)
            transaction.retry_count += 1
            db.session.commit()
            return False
    
    def _log_action(self, transaction_id: str, action: str, details: Dict):
        """Log mixing action"""
        log = MixingLog(
            transaction_id=transaction_id,
            action=action,
            details=details
        )
        db.session.add(log)
        db.session.commit()
    
    def get_transaction_status(self, transaction_id: str) -> Optional[Dict]:
        """Get transaction status and details"""
        transaction = MixingTransaction.query.get(transaction_id)
        if not transaction:
            return None
        
        return {
            'id': str(transaction.id),
            'status': transaction.status.value,
            'input_address': transaction.input_address,
            'input_amount': str(transaction.input_amount),
            'output_amount': str(transaction.output_amount),
            'fee_amount': str(transaction.fee_amount),
            'mixing_rounds_completed': transaction.mixing_rounds_completed,
            'created_at': transaction.created_at.isoformat(),
            'scheduled_output_time': transaction.scheduled_output_time.isoformat() if transaction.scheduled_output_time else None,
            'input_txid': transaction.input_txid,
            'output_txid': transaction.output_txid
        }

