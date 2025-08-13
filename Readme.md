# Bitcoin Mixer Service

Production-ready Bitcoin mixing service with advanced security features.

## 🚀 Features

- **Advanced Mixing Algorithm**: Multi-round mixing with random delays
- **PostgreSQL Database**: Reliable transaction tracking
- **Redis Caching**: High-performance rate limiting and session management
- **Celery Workers**: Asynchronous task processing
- **Docker Support**: Easy deployment with docker-compose
- **CSRF Protection**: Flask-WTF security
- **Rate Limiting**: DDoS protection
- **SSL/HTTPS**: Nginx reverse proxy with SSL
- **Comprehensive Testing**: pytest test suite
- **Monitoring**: Detailed logging and alerts

## 📋 Requirements

- Docker & Docker Compose
- Bitcoin Core with RPC enabled
- Python 3.11+ (for development)
- PostgreSQL 15+
- Redis 7+

## 🛠️ Quick Start

### Using Docker (Recommended)

1. Clone the repository:
```bash
git clone https://github.com/yourusername/bitcoin-mixer.git
cd bitcoin-mixer
```

2. Copy environment file:
```bash
cp .env.example .env
```

3. Configure `.env` file with your settings:
```ini
SECRET_KEY=your-very-secret-key
RPC_USER=your_bitcoin_rpc_user
RPC_PASS=your_bitcoin_rpc_password
RPC_HOST=your_bitcoin_node_ip
```

4. Run deployment script:
```bash
./deploy.sh
```

5. Access the application:
- HTTP: http://localhost
- HTTPS: https://localhost

### Manual Installation

1. Install dependencies:
```bash
pip install -r requirements.txt
```

2. Setup PostgreSQL and Redis

3. Run migrations:
```bash
flask db upgrade
flask init-db
```

4. Start services:
```bash
# Terminal 1: Flask app
gunicorn --bind 0.0.0.0:5000 mixer_service:app

# Terminal 2: Celery worker
celery -A tasks.celery worker --loglevel=info

# Terminal 3: Celery beat
celery -A tasks.celery beat --loglevel=info
```

## 🔧 Configuration

### Environment Variables

| Variable | Description | Default |
|----------|-------------|---------|
| SECRET_KEY | Flask secret key | Required |
| DATABASE_URL | PostgreSQL connection string | Required |
| REDIS_URL | Redis connection string | Required |
| RPC_USER | Bitcoin RPC username | Required |
| RPC_PASS | Bitcoin RPC password | Required |
| RPC_HOST | Bitcoin RPC host | 127.0.0.1 |
| RPC_PORT | Bitcoin RPC port | 8332 |
| MIN_AMOUNT | Minimum mix amount (BTC) | 0.001 |
| MAX_AMOUNT | Maximum mix amount (BTC) | 100 |
| FEE_PERCENT | Mixing fee percentage | 0.03 |
| MIXING_ROUNDS | Number of mixing rounds | 3 |

## 🧪 Testing

Run tests with coverage:
```bash
pytest
```

Run specific test categories:
```bash
pytest -m unit
pytest -m integration
```

## 📊 Monitoring

### Logs
- Application logs: `logs/mixer.log`
- Celery logs: `docker-compose logs celery_worker`
- Nginx logs: `docker-compose logs nginx`

### Health Checks
- Main app: http://localhost:5000/health
- PostgreSQL: `docker-compose exec postgres pg_isready`
- Redis: `docker-compose exec redis redis-cli ping`

## 🔒 Security

- All connections use HTTPS in production
- CSRF protection on all forms
- Rate limiting (10 requests/minute)
- Input validation and sanitization
- SQL injection protection
- XSS prevention
- Session security with secure cookies

## 🚀 Production Deployment

1. Use strong SECRET_KEY
2. Enable HTTPS with valid SSL certificate
3. Configure firewall rules
4. Set up monitoring and alerts
5. Regular backups of PostgreSQL
6. Use environment-specific configs

## 📝 API Documentation

### POST /mixer
Create new mixing transaction

### GET /status/<transaction_id>
Check transaction status

### GET /api/check_payment/<transaction_id>
Check if payment received (JSON)

## 🤝 Contributing

1. Fork the repository
2. Create feature branch
3. Commit changes
4. Push to branch
5. Create Pull Request

## ⚠️ Disclaimer

This software is for educational and privacy purposes only. Users are responsible for complying with local laws and regulations.

## 📄 License

MIT License - see LICENSE file for details