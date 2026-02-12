#!/bin/bash
# Copy this to Dokploy Environment Tab

echo "=========================================="
echo "  DOKPLOY ENVIRONMENT VARIABLES"
echo "=========================================="
echo ""
echo "📋 Copy the content below and paste into Dokploy Environment tab:"
echo ""
echo "=========================================="
cat .env.dokploy
echo "=========================================="
echo ""
echo "⚠️  IMPORTANT: Update this line with your VPS IP:"
echo "CORS_ORIGINS=http://localhost:5174,http://127.0.0.1:5174,http://YOUR_VPS_IP:5174"
echo ""
echo "Replace YOUR_VPS_IP with your actual VPS IP address"
echo ""
