# AirCursor: Offline & Air-Gapped Deployment Guide

## Overview

AirCursor processes motion and camera input locally. The Web Remote is intended for a trusted private network and is protected by a random bearer token. No cloud inference is required.

## 1. Standalone execution

### Windows
1. Unzip the distribution bundle.
2. Launch the native desktop app with **Start-AirCursor.bat**.
3. The host console displays a private pairing token.
4. On the host PC, open **http://127.0.0.1:8765/pair** to display the QR code.
5. Scan the QR code from the phone connected to the same trusted Wi-Fi network.

The pairing token grants control of the host computer. Do not share it. To revoke existing mobile pairings, stop and restart AirCursor so a new token is generated.

### Linux
1. Ensure Python 3.10+ is installed.
2. Launch the remote/desktop process using the supplied launcher.
3. The host console displays the pairing token. Open the host-local **/pair** page when the selected server provides it.
4. Keep the token private and use only a trusted local network.

## 2. Docker deployment

The container includes Xvfb and optional noVNC packages, but **noVNC is disabled by default**. The Web Remote HTTP API uses bearer-token authentication; the random token is printed to container logs at startup.

~~~bash
docker build -t aircursor:latest .

docker run -d \
  --name aircursor \
  -p 8765:8765 \
  -p 127.0.0.1:4242:4242/udp \
  -e MODE=synthetic \
  -e ENABLE_NOVNC=false \
  aircursor:latest

# Read the access token from the startup log:
docker logs aircursor
~~~

On a phone on the same trusted LAN, open **http://HOST-LAN-IP:8765**. The PWA asks for the token from docker logs on the first control action.

OpenTrack UDP is bound to host loopback in the example above. Change the UDP publish address only when a remote sensor host genuinely needs LAN access.

### Optional noVNC (not recommended on shared networks)

noVNC is not published by default. To enable it, provide a strong VNC password and explicitly publish port 6080. The entrypoint refuses to start x11vnc without VNC_PASSWORD.

~~~bash
docker run -d \
  --name aircursor \
  -p 8765:8765 \
  -p 6080:6080 \
  -e ENABLE_NOVNC=true \
  -e VNC_PASSWORD='strong-private-password' \
  aircursor:latest
~~~

VNC is a separate remote-desktop surface. Keep it behind a trusted network or VPN and never expose it directly to the public internet.

## 3. Docker Compose

The default docker-compose.yml exposes the authenticated Web Remote and binds UDP sensor input to host loopback. It does not publish noVNC. Run:

~~~bash
docker compose up -d
docker compose logs aircursor
~~~

Use the token printed in the service logs when the PWA requests it.

## 4. Kubernetes

The default Kustomize stack uses a ClusterIP service and does not create a NodePort or publish noVNC. The Ingress template requires TLS.

Before applying, edit k8s/ingress.yaml and replace aircursor.example.com with your real DNS name. Create the TLS secret in the same namespace:

~~~bash
kubectl create secret tls aircursor-tls \
  --cert=fullchain.pem \
  --key=privkey.pem
kubectl apply -k k8s/
~~~

Read the random Web Remote token from the pod logs:

~~~bash
kubectl logs deployment/aircursor
~~~

Do not expose the service through a NodePort or plaintext Ingress. If you add external access, retain TLS and the bearer-token gate, and restrict network access at the ingress/firewall layer.

## 5. Hardware sensor connectivity

- **OpenTrack UDP:** the container listens on port 4242/udp; the example Docker mapping binds only to host loopback.
- **Linux AirPods Bluetooth:** connect through the local BlueZ stack and required host permissions.
- **Phone gyroscope / touchpad:** connect the phone browser to the Web Remote over the same trusted LAN and pair using the host token.

## Security notes

- The pairing credential grants remote input control. Keep it private.
- Tokens are generated per server process unless AIRCURSOR_REMOTE_TOKEN is supplied. Restarting without a configured token revokes old process tokens.
- The QR page is restricted to loopback clients. Docker/headless deployments may require copying the token from logs into the PWA.
- Bearer authentication over plain HTTP is vulnerable to interception on an untrusted network. Use the TLS Ingress or a trusted VPN for remote deployment.
- noVNC is disabled by default and requires a password when explicitly enabled.
