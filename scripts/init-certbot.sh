#!/bin/bash
# Run once on fresh server to get initial certificate

DOMAIN="siberianops.gidmaster.dev"
EMAIL="k.syrovatsky@gmail.com"

echo ">>> Creating data directories"
mkdir -p data/certbot/conf data/certbot/www

echo ">>> Starting Nginx with HTTP-only config"
cp docker/nginx/nginx.conf docker/nginx/nginx.conf.backup
cp docker/nginx/nginx.conf.init docker/nginx/nginx.conf

docker compose -f docker-compose.prod.yml up -d nginx

echo ">>> Waiting for Nginx"
sleep 5

echo ">>> Issuing certificate"
docker compose -f docker-compose.prod.yml run --rm \
  --entrypoint "certbot certonly --webroot \
    --webroot-path=/var/www/certbot \
    --email ${EMAIL} \
    --agree-tos \
    --no-eff-email \
    -d ${DOMAIN} \
    -d www.${DOMAIN}" \
  certbot

echo ">>> Restoring SSL Nginx config"
cp docker/nginx/nginx.conf.backup docker/nginx/nginx.conf

echo ">>> Restarting all services"
docker compose -f docker-compose.prod.yml up -d

echo ">>> Done"