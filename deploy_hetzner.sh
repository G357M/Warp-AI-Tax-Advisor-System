#!/bin/bash
# InfoHub AI Tax Advisor - Hetzner Deployment Script
# Run this on your Hetzner server

set -e

echo "=========================================="
echo "🚀 InfoHub AI - Hetzner Deployment"
echo "=========================================="
echo ""

# Update system
echo "📦 Updating system..."
sudo apt-get update
sudo apt-get upgrade -y

# Install Docker
echo "🐳 Installing Docker..."
if ! command -v docker &> /dev/null; then
    curl -fsSL https://get.docker.com -o get-docker.sh
    sudo sh get-docker.sh
    sudo usermod -aG docker $USER
    echo "✅ Docker installed"
else
    echo "✅ Docker already installed"
fi

# Install Docker Compose
echo "📦 Installing Docker Compose..."
if ! command -v docker-compose &> /dev/null; then
    sudo curl -L "https://github.com/docker/compose/releases/download/v2.24.0/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
    sudo chmod +x /usr/local/bin/docker-compose
    echo "✅ Docker Compose installed"
else
    echo "✅ Docker Compose already installed"
fi

# Install Git
echo "📦 Installing Git..."
sudo apt-get install -y git

# Clone repository
echo "📥 Cloning repository..."
if [ ! -d "InfoHub-AI" ]; then
    git clone https://github.com/G357M/Warp-AI-Tax-Advisor-System.git InfoHub-AI
    cd InfoHub-AI
else
    cd InfoHub-AI
    git pull
fi

# Create .env file
echo "⚙️ Creating environment file..."
cat > .env << 'EOF'
# Database
DATABASE_URL=postgresql://infohub_user:CHANGE_THIS_PASSWORD@postgres:5432/infohub_ai
POSTGRES_USER=infohub_user
POSTGRES_PASSWORD=CHANGE_THIS_PASSWORD
POSTGRES_DB=infohub_ai

# Redis
REDIS_URL=redis://redis:6379/0

# OpenAI (REQUIRED - Add your key!)
OPENAI_API_KEY=sk-your-openai-key-here

# JWT Security (Generate random secret!)
JWT_SECRET_KEY=CHANGE_THIS_TO_RANDOM_SECRET_KEY
JWT_ALGORITHM=HS256
JWT_EXPIRATION_MINUTES=1440

# Application
APP_NAME=InfoHub AI Tax Advisor
APP_VERSION=1.0.0
ENVIRONMENT=production
DEBUG=false
LOG_LEVEL=INFO

# API
API_HOST=0.0.0.0
API_PORT=8000
CORS_ORIGINS=["*"]

# Embeddings
EMBEDDING_MODEL=sentence-transformers/paraphrase-multilingual-mpnet-base-v2
EMBEDDING_DIMENSION=768

# LLM
LLM_MODEL=gpt-4-turbo-preview
LLM_TEMPERATURE=0.3
LLM_MAX_TOKENS=1000

# ChromaDB
CHROMA_HOST=chromadb
CHROMA_PORT=8000
CHROMA_COLLECTION=tax_documents

# Rate Limiting
GUEST_RATE_LIMIT=10
USER_RATE_LIMIT=60
RATE_LIMIT_WINDOW=60
EOF

echo ""
echo "⚠️  IMPORTANT: Edit .env file and set:"
echo "   1. OPENAI_API_KEY (required for AI)"
echo "   2. POSTGRES_PASSWORD (change default)"
echo "   3. JWT_SECRET_KEY (generate random)"
echo ""
read -p "Press Enter after editing .env file..."

# Create docker-compose for production
echo "🐳 Creating docker-compose.yml..."
cat > docker-compose.prod.yml << 'EOF'
version: '3.8'

services:
  postgres:
    image: postgres:15-alpine
    container_name: infohub-postgres
    environment:
      POSTGRES_USER: ${POSTGRES_USER}
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD}
      POSTGRES_DB: ${POSTGRES_DB}
    volumes:
      - postgres_data:/var/lib/postgresql/data
    ports:
      - "5432:5432"
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U ${POSTGRES_USER}"]
      interval: 10s
      timeout: 5s
      retries: 5

  redis:
    image: redis:7-alpine
    container_name: infohub-redis
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "redis-cli", "ping"]
      interval: 10s
      timeout: 3s
      retries: 5

  backend:
    build:
      context: .
      dockerfile: backend/Dockerfile
    container_name: infohub-backend
    environment:
      - DATABASE_URL=${DATABASE_URL}
      - REDIS_URL=${REDIS_URL}
      - OPENAI_API_KEY=${OPENAI_API_KEY}
      - JWT_SECRET_KEY=${JWT_SECRET_KEY}
      - ENVIRONMENT=production
    ports:
      - "8000:8000"
    depends_on:
      postgres:
        condition: service_healthy
      redis:
        condition: service_healthy
    restart: unless-stopped
    volumes:
      - ./data:/app/data
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8000/health"]
      interval: 30s
      timeout: 10s
      retries: 3

  frontend:
    build:
      context: ./frontend
      dockerfile: Dockerfile
      args:
        - NEXT_PUBLIC_API_URL=http://your-server-ip:8000/api/v1
    container_name: infohub-frontend
    ports:
      - "3000:3000"
    depends_on:
      - backend
    restart: unless-stopped

  nginx:
    image: nginx:alpine
    container_name: infohub-nginx
    ports:
      - "80:80"
      - "443:443"
    volumes:
      - ./nginx.conf:/etc/nginx/nginx.conf:ro
      - ./ssl:/etc/nginx/ssl:ro
    depends_on:
      - backend
      - frontend
    restart: unless-stopped

volumes:
  postgres_data:
  redis_data:
EOF

# Create nginx config
echo "🌐 Creating nginx config..."
cat > nginx.conf << 'EOF'
events {
    worker_connections 1024;
}

http {
    upstream backend {
        server backend:8000;
    }

    upstream frontend {
        server frontend:3000;
    }

    server {
        listen 80;
        server_name _;

        client_max_body_size 100M;

        # Frontend
        location / {
            proxy_pass http://frontend;
            proxy_http_version 1.1;
            proxy_set_header Upgrade $http_upgrade;
            proxy_set_header Connection 'upgrade';
            proxy_set_header Host $host;
            proxy_cache_bypass $http_upgrade;
        }

        # Backend API
        location /api {
            proxy_pass http://backend;
            proxy_set_header Host $host;
            proxy_set_header X-Real-IP $remote_addr;
            proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
            proxy_set_header X-Forwarded-Proto $scheme;
        }

        # Metrics
        location /metrics {
            proxy_pass http://backend;
        }

        # Health check
        location /health {
            proxy_pass http://backend;
        }
    }
}
EOF

# Create backend Dockerfile if not exists
if [ ! -f "backend/Dockerfile" ]; then
    echo "🐳 Creating backend Dockerfile..."
    cat > backend/Dockerfile << 'EOF'
FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    g++ \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements
COPY requirements.txt .

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Copy application
COPY . .

# Expose port
EXPOSE 8000

# Health check
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

# Run application
CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
EOF
fi

# Create frontend Dockerfile if not exists
if [ ! -f "frontend/Dockerfile" ]; then
    echo "🐳 Creating frontend Dockerfile..."
    cat > frontend/Dockerfile << 'EOF'
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM node:20-alpine

WORKDIR /app

COPY --from=builder /app/next.config.js ./
COPY --from=builder /app/public ./public
COPY --from=builder /app/.next ./.next
COPY --from=builder /app/node_modules ./node_modules
COPY --from=builder /app/package.json ./package.json

EXPOSE 3000

CMD ["npm", "start"]
EOF
fi

# Start services
echo ""
echo "🚀 Starting services..."
docker-compose -f docker-compose.prod.yml up -d

echo ""
echo "⏳ Waiting for services to start..."
sleep 10

# Show status
echo ""
echo "📊 Services status:"
docker-compose -f docker-compose.prod.yml ps

echo ""
echo "=========================================="
echo "✅ Deployment Complete!"
echo "=========================================="
echo ""
echo "📍 Access URLs:"
echo "   Web App:     http://$(curl -s ifconfig.me)"
echo "   Admin Panel: http://$(curl -s ifconfig.me)/admin"
echo "   API Docs:    http://$(curl -s ifconfig.me):8000/docs"
echo "   Metrics:     http://$(curl -s ifconfig.me):8000/metrics"
echo ""
echo "📝 Useful commands:"
echo "   View logs:     docker-compose -f docker-compose.prod.yml logs -f"
echo "   Stop:          docker-compose -f docker-compose.prod.yml down"
echo "   Restart:       docker-compose -f docker-compose.prod.yml restart"
echo "   Update:        git pull && docker-compose -f docker-compose.prod.yml up -d --build"
echo ""
echo "🔒 Security reminders:"
echo "   1. Set up firewall (ufw)"
echo "   2. Configure SSL/TLS certificate"
echo "   3. Change default passwords in .env"
echo "   4. Set up automatic backups"
echo ""
