# Security Policy

## Remote control credentials

AirCursor can inject mouse and keyboard-like actions into the host desktop. Treat the Web Remote bearer token as a control credential.

- Do not share the pairing token or commit it to source control.
- The token is generated randomly for each process unless AIRCURSOR_REMOTE_TOKEN is explicitly configured.
- The mobile QR is served only to loopback clients on the host machine. Docker/headless users can read the random token in container logs and enter it into the PWA.
- All control POST requests require Authorization: Bearer <token>.
- Browser WebSocket clients must send an authenticated JSON auth message as their first application frame before any control command is accepted.
- Read-only status and static PWA assets remain publicly readable to clients that can reach the service.

## Network exposure

- Use the Web Remote only on a trusted private network.
- Plain HTTP does not protect bearer tokens from network interception. Use HTTPS/TLS or a trusted VPN when traffic crosses untrusted networks.
- Do not expose the API directly to the public internet.
- noVNC is disabled by default. When explicitly enabled, a VNC password is mandatory; keep the port private and do not rely on the password alone for internet exposure.
- Kubernetes defaults to ClusterIP, no NodePort and no noVNC route. The Ingress example requires TLS; replace the example hostname and create the TLS secret before applying.

## Reporting

Do not publish credentials, LAN addresses, packet captures containing tokens, or details that enable remote control. Report security problems privately to the repository maintainer.
