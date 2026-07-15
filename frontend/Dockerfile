FROM node:20-alpine
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY package*.json ./
RUN npm ci --no-audit --fund=false
COPY . .
