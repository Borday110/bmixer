"""
Enhanced security utilities for Bitcoin Mixer
"""
import hmac
import hashlib
import secrets
from functools import wraps
from flask import request, abort, current_app
from models import SecurityAlert, db
import re


class SecurityManager:
    """Security management utilities"""
    
    @staticmethod
    def validate_bitcoin_address(address: str) -> bool:
        """Enhanced Bitcoin address validation"""
        # Basic regex patterns for different address types
        patterns = [
            r'^[13][a-km-zA-HJ-NP-Z1-9]{25,34}$',  # Legacy
            r'^bc1[a-z0-9]{39,59}$',  # Bech32
            r'^[2mn][a-km-zA-HJ-NP-Z1-9]{33}$',  # Testnet
        ]
        
        return any(re.match(pattern, address) for pattern in patterns)
    
    @staticmethod
    def generate_secure_token(length: int = 32) -> str:
        """Generate cryptographically secure token"""
        return secrets.token_urlsafe(length)
    
    @staticmethod
    def hash_data(data: str, salt: str = None) -> str:
        """Hash data with optional salt"""
        if salt is None:
            salt = current_app.config['SECRET_KEY']
        
        return hashlib.sha256(f"{data}{salt}".encode()).hexdigest()
    
    @staticmethod
    def verify_signature(data: str, signature: str, secret: str = None) -> bool:
        """Verify HMAC signature"""
        if secret is None:
            secret = current_app.config['SECRET_KEY']
        
        expected = hmac.new(
            secret.encode(),
            data.encode(),
            hashlib.sha256
        ).hexdigest()
        
        return hmac.compare_digest(expected, signature)
    
    @staticmethod
    def check_sql_injection(data: str) -> bool:
        """Basic SQL injection detection"""
        suspicious_patterns = [
            r"(\b(union|select|insert|update|delete|drop|create)\b)",
            r"(;|--|\*|\/\*|\*\/)",
            r"(\b(or|and)\b\s*\d+\s*=\s*\d+)",
            r"('|\"|`)"
        ]
        
        data_lower = data.lower()
        for pattern in suspicious_patterns:
            if re.search(pattern, data_lower, re.IGNORECASE):
                return False
        return True
    
    @staticmethod
    def log_security_event(event_type: str, severity: str, details: dict):
        """Log security event to database"""
        alert = SecurityAlert(
            alert_type=event_type,
            severity=severity,
            details=details,
            ip_hash=details.get('ip_hash'),
        )
        db.session.add(alert)
        db.session.commit()


def require_api_key(f):
    """Decorator to require API key for certain endpoints"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        api_key = request.headers.get('X-API-Key')
        
        if not api_key:
            abort(401, description="API key required")
        
        # In production, validate against database
        valid_keys = current_app.config.get('VALID_API_KEYS', [])
        if api_key not in valid_keys:
            abort(403, description="Invalid API key")
        
        return f(*args, **kwargs)
    return decorated_function


def validate_transaction_data(f):
    """Decorator to validate transaction data"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if request.method == 'POST':
            data = request.get_json() or request.form
            
            # Check for required fields
            required_fields = ['output_address', 'amount']
            for field in required_fields:
                if field not in data:
                    abort(400, description=f"Missing required field: {field}")
            
            # Validate address
            if not SecurityManager.validate_bitcoin_address(data.get('output_address', '')):
                abort(400, description="Invalid Bitcoin address")
            
            # Check for SQL injection
            for value in data.values():
                if isinstance(value, str) and not SecurityManager.check_sql_injection(value):
                    SecurityManager.log_security_event(
                        "SQL_INJECTION_ATTEMPT",
                        "critical",
                        {"data": str(value)[:100], "ip": request.remote_addr}
                    )
                    abort(400, description="Invalid input detected")
        
        return f(*args, **kwargs)
    return decorated_function

