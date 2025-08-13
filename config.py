"""
Bitcoin Mixer Configuration File
"""
import os
from datetime import timedelta
from dotenv import load_dotenv

load_dotenv()


class Config:
    """Base configuration"""
    # Flask
    SECRET_KEY = os.getenv('SECRET_KEY', 'dev-secret-key-change-in-production')
    WTF_CSRF_ENABLED = True
    WTF_CSRF_TIME_LIMIT = None
    
    # Database
    SQLALCHEMY_DATABASE_URI = os.getenv(
        'DATABASE_URL',
        'postgresql://mixer:mixer@localhost/mixer_db'
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SQLALCHEMY_ENGINE_OPTIONS = {
        'pool_size': 10,
        'pool_recycle': 3600,
        'pool_pre_ping': True
    }
    
    # Redis
    REDIS_URL = os.getenv('REDIS_URL', 'redis://localhost:6379/0')
    
    # Celery
    CELERY_BROKER_URL = os.getenv('CELERY_BROKER_URL', 'redis://localhost:6379/1')
    CELERY_RESULT_BACKEND = os.getenv('CELERY_RESULT_BACKEND', 'redis://localhost:6379/2')
    
    # Bitcoin RPC
    RPC_USER = os.getenv('RPC_USER', 'bitcoinrpc')
    RPC_PASS = os.getenv('RPC_PASS', 'password')
    RPC_HOST = os.getenv('RPC_HOST', '127.0.0.1')
    RPC_PORT = int(os.getenv('RPC_PORT', '8332'))
    
    # Mixer Settings
    MIN_AMOUNT = float(os.getenv('MIN_AMOUNT', '0.001'))  # Lowered for testing
    MAX_AMOUNT = float(os.getenv('MAX_AMOUNT', '100'))
    FEE_PERCENT = float(os.getenv('FEE_PERCENT', '0.03'))
    MIXING_ROUNDS = int(os.getenv('MIXING_ROUNDS', '3'))
    DELAY_MINUTES_MIN = int(os.getenv('DELAY_MINUTES_MIN', '10'))
    DELAY_MINUTES_MAX = int(os.getenv('DELAY_MINUTES_MAX', '60'))
    
    # Security
    RATE_LIMIT_SECONDS = int(os.getenv('RATE_LIMIT_SECONDS', '6'))
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = 'Lax'
    PERMANENT_SESSION_LIFETIME = timedelta(hours=1)
    
    # Telegram
    TELEGRAM_BOT_TOKEN = os.getenv('TELEGRAM_BOT_TOKEN', '')
    TELEGRAM_CHAT_ID = os.getenv('TELEGRAM_CHAT_ID', '')
    
    # Logging
    LOG_LEVEL = os.getenv('LOG_LEVEL', 'INFO')
    LOG_DIR = 'logs'
    LOG_MAX_BYTES = 10 * 1024 * 1024  # 10MB
    LOG_BACKUP_COUNT = 5


class DevelopmentConfig(Config):
    """Development configuration"""
    DEBUG = True
    TESTING = False
    WTF_CSRF_ENABLED = False  # For easier testing
    SESSION_COOKIE_SECURE = False  # Allow HTTP in development


class ProductionConfig(Config):
    """Production configuration"""
    DEBUG = False
    TESTING = False
    # Force HTTPS
    SESSION_COOKIE_SECURE = True
    PREFERRED_URL_SCHEME = 'https'
    
    # Stronger secret key
    SECRET_KEY = os.getenv('SECRET_KEY')
    if not SECRET_KEY:
        raise ValueError("SECRET_KEY environment variable must be set in production")


class TestConfig(Config):
    """Testing configuration"""
    TESTING = True
    WTF_CSRF_ENABLED = False
    SQLALCHEMY_DATABASE_URI = 'sqlite:///:memory:'
    

# Configuration dictionary
config = {
    'development': DevelopmentConfig,
    'production': ProductionConfig,
    'testing': TestConfig,
    'default': DevelopmentConfig
}

