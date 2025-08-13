#!/bin/bash
# Bitcoin Mixer Deployment Script

set -e

echo "🚀 Starting Bitcoin Mixer deployment..."

# Check if .env file exists
if [ ! -f .env ]; then
    echo "❌ Error: .env file not found!"
    echo "Please copy .env.example to .env and configure it."
    exit 1
fi

# Load environment variables
export $(cat .env | grep -v '^#' | xargs)

# Check required environment variables
required_vars=("SECRET_KEY" "RPC_USER" "RPC_PASS" "DATABASE_URL")
for var in "${required_vars[@]}"; do
    if [ -z "${!var}" ]; then
        echo "❌ Error: $var is not set in .env file!"
        exit 1
    fi
done

# Generate SSL certificates if not exists
if [ ! -f ssl/cert.pem ]; then
    echo "📜 Generating self-signed SSL certificates..."
    mkdir -p ssl
    openssl req -x509 -newkey rsa:4096 -nodes -out ssl/cert.pem -keyout ssl/key.pem -days 365 \
        -subj "/C=US/ST=State/L=City/O=Organization/CN=localhost"
fi

# Build Docker images
echo "🔨 Building Docker images..."
docker-compose build

# Start services
echo "🚀 Starting services..."
docker-compose up -d postgres redis

# Wait for PostgreSQL to be ready
echo "⏳ Waiting for PostgreSQL..."
sleep 10

# Run database migrations
echo "🗄️ Running database migrations..."
docker-compose run --rm web flask db upgrade

# Initialize database
echo "🗄️ Initializing database..."
docker-compose run --rm web flask init-db

# Create mixing pool addresses
echo "💰 Creating mixing pool addresses..."
docker-compose run --rm web flask create-pool-addresses

# Start all services
echo "🚀 Starting all services..."
docker-compose up -d

# Show status
echo "✅ Deployment complete!"
echo ""
echo "Services running:"
docker-compose ps

echo ""
echo "🌐 Access the application at:"
echo "   HTTP:  http://localhost"
echo "   HTTPS: https://localhost"
echo ""
echo "📊 Monitor logs with:"
echo "   docker-compose logs -f"
echo ""
echo "🛑 Stop services with:"
echo "   docker-compose down"

