#!/usr/bin/env bash
# AirCursor Offline Kubernetes Deployment Script
cd "$(dirname "$0")"

echo "======================================================================"
echo "          AirCursor Production Offline Kubernetes Deployment"
echo "======================================================================"

kubectl apply -k k8s/

echo "[+] Manifests applied successfully."
echo "[*] Checking Pod and Service status..."
kubectl get pods -l app.kubernetes.io/name=aircursor
kubectl get svc -l app.kubernetes.io/name=aircursor
kubectl get ingress -l app.kubernetes.io/name=aircursor
