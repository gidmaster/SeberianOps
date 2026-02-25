#!/bin/bash
# Run once on fresh server to get initial certificate

DOMAIN="siberianops.gidmaster.dev"
EMAIL="k.syrovatsky@gmail.com"

# Start nginx first (needed for acme-challenge)
docker compose -f docker-compose.prod.yml up -d nginx

# Get certificate
docker compose -f docker-compose.prod.yml run --rm certbot \
  certonly --webroot \
  --webroot-path=/var/www/certbot \
  --email $EMAIL \
  --agree-tos \
  --no-eff-email \
  -d $DOMAIN \
  -d www.$DOMAIN

# Start everything
docker compose -f docker-compose.prod.yml up -d