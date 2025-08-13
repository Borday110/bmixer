#!/usr/bin/env python3
"""
Bitcoin Mixer Service - Main Flask Application
"""
import os
import hashlib
import secrets
import logging
from datetime import datetime
from decimal import Decimal
from flask import Flask, request, render_template, abort, jsonify, session, redirect, url_for
from flask_wtf import FlaskForm, CSRFProtect
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_talisman import Talisman
from flask_cors import CORS
from wtforms import StringField, DecimalField, HiddenField
from wtforms.validators import DataRequired, ValidationError
import qrcode
import io
import base64
from config import config
from models import db, MixingTransaction, SecurityAlert
from mixing_service import MixingService
from tasks import celery, send_security_alert

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)

# Initialize Flask app
app = Flask(__name__)
app.config.from_object(config[os.getenv('FLASK_ENV', 'development')])

# Initialize extensions
db.init_app(app)
migrate = Migrate(app, db)
csrf = CSRFProtect(app)
cors = CORS(app, origins=app.config.get('CORS_ORIGINS', []))

# Initialize rate limiter
limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    storage_uri=app.config['REDIS_URL']
)

# Initialize security headers (only in production)
if app.config['ENV'] == 'production':
    Talisman(app, force_https=True)

# Initialize mixing service
mixing_service = MixingService(app.config)

# Form definitions
class MixerForm(FlaskForm):
    """Mixing transaction form"""
    amount = DecimalField('Amount', validators=[DataRequired()], places=8)
    output_address = StringField('Output Address', validators=[DataRequired()])
    
    def validate_amount(self, field):
        if field.data < Decimal(str(app.config['MIN_AMOUNT'])):
            raise ValidationError(f"Minimum amount is {app.config['MIN_AMOUNT']} BTC")
        if field.data > Decimal(str(app.config['MAX_AMOUNT'])):
            raise ValidationError(f"Maximum amount is {app.config['MAX_AMOUNT']} BTC")
    
    def validate_output_address(self, field):
        if not mixing_service.validate_bitcoin_address(field.data):
            raise ValidationError("Invalid Bitcoin address")


# Utility functions
def generate_qr_code(address: str) -> str:
    """Generate QR code for Bitcoin address"""
    qr = qrcode.QRCode(version=1, box_size=10, border=4)
    qr.add_data(f"bitcoin:{address}")
    qr.make(fit=True)
    
    img = qr.make_image(fill_color="black", back_color="white")
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    buffer.seek(0)
    
    return base64.b64encode(buffer.getvalue()).decode()


def anonymize_ip(ip: str) -> str:
    """Anonymize IP address"""
    return hashlib.sha256(f"{ip}{app.config['SECRET_KEY']}".encode()).hexdigest()[:16]


def anonymize_user_agent(user_agent: str) -> str:
    """Anonymize user agent"""
    return hashlib.sha256(f"{user_agent}{app.config['SECRET_KEY']}".encode()).hexdigest()[:16]


def get_client_ip() -> str:
    """Get client IP address"""
    if "X-Forwarded-For" in request.headers:
        ip = request.headers.get("X-Forwarded-For").split(",")[0].strip()
    elif "X-Real-IP" in request.headers:
        ip = request.headers.get("X-Real-IP")
    else:
        ip = request.remote_addr
    return ip


def check_suspicious_activity(ip_hash: str, user_agent_hash: str) -> bool:
    """Check for suspicious activity patterns"""
    # Check recent alerts from this IP
    recent_alerts = SecurityAlert.query.filter_by(ip_hash=ip_hash).filter(
        SecurityAlert.created_at >= datetime.utcnow() - timedelta(hours=1)
    ).count()
    
    if recent_alerts > 5:
        send_security_alert.delay(
            "SUSPICIOUS_ACTIVITY",
            "high",
            {"ip_hash": ip_hash, "recent_alerts": recent_alerts}
        )
        return False
    
    return True


# Session management
@app.before_request
def create_session():
    """Create session for each user"""
    if 'session_id' not in session:
        session['session_id'] = secrets.token_urlsafe(32)
        session.permanent = True


# Routes
@app.route("/")
def index():
    """Home page"""
    return render_template("index.html")


@app.route("/mixer", methods=["GET", "POST"])
@limiter.limit("10 per minute")
def mixer():
    """Mixer form and processing"""
    form = MixerForm()
    
    if form.validate_on_submit():
        try:
            # Get client info
            ip = get_client_ip()
            ip_hash = anonymize_ip(ip)
            user_agent_hash = anonymize_user_agent(request.headers.get('User-Agent', ''))
            
            # Check suspicious activity
            if not check_suspicious_activity(ip_hash, user_agent_hash):
                abort(429, description="Too many requests. Please try again later.")
            
            # Create mixing transaction
            transaction = mixing_service.create_mixing_transaction(
                input_amount=form.amount.data,
                output_address=form.output_address.data,
                session_id=session['session_id'],
                ip_hash=ip_hash,
                user_agent_hash=user_agent_hash
            )
            
            # Generate QR code for input address
            qr_code = generate_qr_code(transaction.input_address)
            
            logger.info(f"New mixing transaction created: {transaction.id}")
            
            return render_template("mixer_confirm.html", 
                                 transaction=transaction,
                                 qr_code=qr_code)
            
        except Exception as e:
            logger.error(f"Error creating transaction: {e}")
            abort(500, description="An error occurred. Please try again.")
    
    return render_template("mixer.html", form=form)


@app.route("/about")
def about():
    """About page"""
    return render_template("about.html")


@app.route("/status/<transaction_id>")
@limiter.limit("30 per minute")
def transaction_status(transaction_id):
    """Check transaction status"""
    status = mixing_service.get_transaction_status(transaction_id)
    
    if not status:
        abort(404, description="Transaction not found")
    
    # Only show to correct session
    transaction = MixingTransaction.query.get(transaction_id)
    if transaction.session_id != session.get('session_id'):
        abort(403, description="Access denied")
    
    return render_template("status.html", status=status)


# API Routes
@app.route("/api/check_payment/<transaction_id>")
@limiter.limit("60 per minute")
def check_payment(transaction_id):
    """Check if payment has been received"""
    transaction = MixingTransaction.query.get(transaction_id)
    
    if not transaction:
        return jsonify({"error": "Transaction not found"}), 404
    
    # Check session
    if transaction.session_id != session.get('session_id'):
        return jsonify({"error": "Access denied"}), 403
    
    # Check payment
    payment_received = mixing_service.check_incoming_payment(transaction_id)
    
    return jsonify({
        "transaction_id": str(transaction.id),
        "payment_received": payment_received,
        "status": transaction.status.value,
        "input_address": transaction.input_address,
        "expected_amount": str(transaction.input_amount)
    })


# Error handlers
@app.errorhandler(400)
def bad_request(e):
    logger.warning(f"Bad request: {e}")
    return render_template("error.html", 
                         code=400, 
                         message="400 - Bad Request", 
                         details=str(e.description)), 400


@app.errorhandler(403)
def forbidden(e):
    logger.warning(f"Forbidden access: {e}")
    return render_template("error.html", 
                         code=403, 
                         message="403 - Forbidden", 
                         details=str(e.description)), 403


@app.errorhandler(404)
def not_found(e):
    return render_template("error.html", 
                         code=404, 
                         message="404 - Not Found", 
                         details=str(e.description)), 404


@app.errorhandler(429)
def too_many_requests(e):
    ip = get_client_ip()
    logger.warning(f"Rate limit exceeded for IP: {ip}")
    send_security_alert.delay(
        "RATE_LIMIT_EXCEEDED",
        "medium",
        {"ip": ip, "endpoint": request.endpoint}
    )
    return render_template("error.html", 
                         code=429, 
                         message="429 - Too Many Requests", 
                         details="Please wait before making another request."), 429


@app.errorhandler(500)
def internal_error(e):
    logger.error(f"Internal error: {e}", exc_info=True)
    return render_template("error.html", 
                         code=500, 
                         message="500 - Internal Server Error", 
                         details="An unexpected error occurred."), 500


# CLI Commands
@app.cli.command()
def init_db():
    """Initialize the database"""
    db.create_all()
    print("Database initialized!")


@app.cli.command()
def create_pool_addresses():
    """Create initial pool addresses"""
    mixing_service.get_mixing_pool_addresses(10)
    print("Pool addresses created!")


if __name__ == "__main__":
    # Development server only
    app.run(host="127.0.0.1", port=5000)
