"""
Database models for Bitcoin Mixer
"""
from datetime import datetime
from enum import Enum
from flask_sqlalchemy import SQLAlchemy
from sqlalchemy import Index
from sqlalchemy.dialects.postgresql import UUID
import uuid

db = SQLAlchemy()


class TransactionStatus(Enum):
    """Transaction status enumeration"""
    PENDING = "pending"
    MIXING = "mixing"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class MixingTransaction(db.Model):
    """Main mixing transaction model"""
    __tablename__ = 'mixing_transactions'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    session_id = db.Column(db.String(64), nullable=False, index=True)
    
    # Amounts
    input_amount = db.Column(db.Numeric(16, 8), nullable=False)
    fee_amount = db.Column(db.Numeric(16, 8), nullable=False)
    output_amount = db.Column(db.Numeric(16, 8), nullable=False)
    
    # Addresses
    input_address = db.Column(db.String(64), nullable=False)
    output_address = db.Column(db.String(64), nullable=False)
    mixing_address = db.Column(db.String(64))  # Our temporary holding address
    
    # Status tracking
    status = db.Column(db.Enum(TransactionStatus), default=TransactionStatus.PENDING, nullable=False)
    mixing_rounds_completed = db.Column(db.Integer, default=0)
    
    # Transaction IDs
    input_txid = db.Column(db.String(64))
    output_txid = db.Column(db.String(64))
    
    # Timestamps
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    mixing_started_at = db.Column(db.DateTime)
    completed_at = db.Column(db.DateTime)
    scheduled_output_time = db.Column(db.DateTime)
    
    # Security
    ip_hash = db.Column(db.String(64))
    user_agent_hash = db.Column(db.String(64))
    
    # Error tracking
    error_message = db.Column(db.Text)
    retry_count = db.Column(db.Integer, default=0)
    
    # Indexes
    __table_args__ = (
        Index('idx_status_created', 'status', 'created_at'),
        Index('idx_session_status', 'session_id', 'status'),
    )
    
    def __repr__(self):
        return f'<MixingTransaction {self.id} - {self.status.value}>'


class MixingPool(db.Model):
    """Pool of coins available for mixing"""
    __tablename__ = 'mixing_pool'
    
    id = db.Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    address = db.Column(db.String(64), unique=True, nullable=False)
    balance = db.Column(db.Numeric(16, 8), default=0)
    last_used = db.Column(db.DateTime)
    is_active = db.Column(db.Boolean, default=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    
    def __repr__(self):
        return f'<MixingPool {self.address} - {self.balance} BTC>'


class MixingLog(db.Model):
    """Detailed mixing operation logs"""
    __tablename__ = 'mixing_logs'
    
    id = db.Column(db.Integer, primary_key=True)
    transaction_id = db.Column(UUID(as_uuid=True), db.ForeignKey('mixing_transactions.id'))
    timestamp = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    action = db.Column(db.String(50), nullable=False)
    details = db.Column(db.JSON)
    
    transaction = db.relationship('MixingTransaction', backref='logs')
    
    # Index for efficient log queries
    __table_args__ = (
        Index('idx_transaction_timestamp', 'transaction_id', 'timestamp'),
    )


class SecurityAlert(db.Model):
    """Security alerts and suspicious activity logs"""
    __tablename__ = 'security_alerts'
    
    id = db.Column(db.Integer, primary_key=True)
    alert_type = db.Column(db.String(50), nullable=False)
    severity = db.Column(db.String(20), nullable=False)  # low, medium, high, critical
    ip_hash = db.Column(db.String(64))
    details = db.Column(db.JSON)
    telegram_sent = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)
    
    # Index for alert queries
    __table_args__ = (
        Index('idx_alert_type_time', 'alert_type', 'created_at'),
        Index('idx_ip_hash_time', 'ip_hash', 'created_at'),
    )

