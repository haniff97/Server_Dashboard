#!/bin/bash
echo "🚀 Deploying latest changes..."
cd /root/Projects/dashboard
git pull origin main
pm2 restart homelab-dashboard mqtt-exporter
pm2 status
echo "✅ Done! Dashboard: http://192.168.1.10:3000"
