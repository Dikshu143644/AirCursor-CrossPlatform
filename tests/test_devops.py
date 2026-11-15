"""
AirCursor DevOps & Production Portability Test Suite.
Validates:
1. Dockerfile multi-stage syntax, virtual display (Xvfb/noVNC), security & healthchecks.
2. docker-compose.yml service schema, ports (8765, 4242/udp), volumes, environment & healthchecks.
3. Kubernetes production offline manifests (deployment, service, configmap, ingress, kustomization).
4. Offline packaging bundle (100% self-contained, 0 CDNs, SHA256 manifest, launchers).
5. Web Remote & Status API (/status 200 OK, REST settings, actions, PWA static serving).
"""

from __future__ import annotations

import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import time
import unittest
import urllib.request
import zipfile
import yaml

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from server import AirCursorServer
from package_offline import (
    build_offline_bundle,
    verify_file_offline_readiness,
    verify_python_core_offline_readiness,
    DISALLOWED_CDN_PATTERNS,
)


class TestDockerfileSyntaxAndBestPractices(unittest.TestCase):
    """Subject 06: Dockerfile syntax, multi-stage structure, and display server configuration."""

    def setUp(self):
        self.dockerfile_path = ROOT_DIR / "Dockerfile"
        self.entrypoint_path = ROOT_DIR / "entrypoint.sh"
        self.assertTrue(self.dockerfile_path.exists(), "Dockerfile must exist at repository root")
        self.content = self.dockerfile_path.read_text(encoding="utf-8")

    def test_dockerfile_multi_stage_syntax(self):
        """Verifies multi-stage build structure with python:3.12-slim base."""
        from_stages = re.findall(r"^FROM\s+([^\s]+)\s+AS\s+([^\s]+)", self.content, re.MULTILINE | re.IGNORECASE)
        self.assertGreaterEqual(len(from_stages), 2, "Dockerfile must define multi-stage build")
        self.assertEqual(from_stages[0][1].lower(), "builder")
        self.assertEqual(from_stages[1][1].lower(), "runtime")
        for base_img, _ in from_stages:
            self.assertIn("python:3.12-slim", base_img)

    def test_dockerfile_virtual_display_packages(self):
        """Verifies virtual display stack (Xvfb + x11vnc + noVNC/websockify) is installed."""
        required_pkgs = ["xvfb", "x11vnc", "novnc", "websockify", "curl"]
        for pkg in required_pkgs:
            self.assertIn(pkg, self.content, f"Dockerfile must install virtual display package: {pkg}")

    def test_dockerfile_ports_exposed(self):
        """Only the authenticated remote and sensor input ports are exposed by default."""
        exposes = re.findall(r"^EXPOSE\s+([^\s]+)", self.content, re.MULTILINE | re.IGNORECASE)
        self.assertIn("8765", exposes, "Must expose 8765 for Web Remote & REST API")
        self.assertTrue(
            any("4242" in p and "udp" in p.lower() for p in exposes),
            "Must expose 4242/udp for OpenTrack / AirPods receiver",
        )
        self.assertNotIn("6080", exposes, "noVNC must not be exposed by default")
        self.assertIn("ENABLE_NOVNC=false", self.content)

    def test_dockerfile_unprivileged_user(self):
        """Verifies container creates non-root user and switches with USER instruction."""
        self.assertIn("useradd", self.content, "Dockerfile must create an unprivileged user")
        self.assertIn("USER aircursor", self.content, "Dockerfile must switch to unprivileged USER aircursor")

    def test_dockerfile_healthcheck(self):
        """Verifies container defines a HEALTHCHECK querying http://localhost:8765/status."""
        self.assertIn("HEALTHCHECK", self.content)
        self.assertIn("http://localhost:8765/status", self.content)

    def test_entrypoint_script(self):
        """Verifies entrypoint.sh exists and configures Xvfb, x11vnc, noVNC, and signal trap."""
        self.assertTrue(self.entrypoint_path.exists(), "entrypoint.sh must exist")
        sh_content = self.entrypoint_path.read_text(encoding="utf-8")
        self.assertIn("Xvfb", sh_content, "entrypoint.sh must handle Xvfb virtual display")
        self.assertIn("x11vnc", sh_content, "entrypoint.sh must handle x11vnc")
        self.assertIn("websockify", sh_content, "entrypoint.sh must handle websockify/noVNC")
        self.assertIn("trap", sh_content, "entrypoint.sh must handle signal trapping")
        self.assertIn('ENABLE_NOVNC="${ENABLE_NOVNC:-false}"', sh_content)
        self.assertIn("VNC_PASSWORD", sh_content)
        self.assertIn("-rfbauth", sh_content)
        self.assertNotIn("-nopw", sh_content)


class TestDockerComposeConfig(unittest.TestCase):
    """Subject 06: docker-compose.yml schema, services, ports, environment, and healthchecks."""

    def setUp(self):
        self.compose_path = ROOT_DIR / "docker-compose.yml"
        self.assertTrue(self.compose_path.exists(), "docker-compose.yml must exist at repository root")
        with open(self.compose_path, "r", encoding="utf-8") as f:
            self.data = yaml.safe_load(f)

    def test_compose_structure(self):
        """Verifies valid compose structure and aircursor service definition."""
        self.assertIsInstance(self.data, dict)
        self.assertIn("services", self.data)
        self.assertIn("aircursor", self.data["services"])

    def test_compose_port_mappings(self):
        """Verifies port mappings for 8765 and 4242/udp."""
        service = self.data["services"]["aircursor"]
        ports = service.get("ports", [])
        port_strs = [str(p) for p in ports]
        has_http = any("8765:8765" in p for p in port_strs)
        has_udp = any("4242:4242/udp" in p for p in port_strs)
        self.assertTrue(has_http, "docker-compose must map port 8765:8765")
        self.assertTrue(has_udp, "docker-compose must map port 4242:4242/udp")
        self.assertFalse(any("6080:6080" in p for p in port_strs), "noVNC must not be published by default")

    def test_compose_environment_flags(self):
        """Verifies AUTORUN=true and MODE flags (synthetic, airpods, camera)."""
        service = self.data["services"]["aircursor"]
        env = service.get("environment", [])
        env_dict = {}
        if isinstance(env, list):
            for item in env:
                if "=" in item:
                    k, v = item.split("=", 1)
                    env_dict[k.strip()] = v.strip()
        elif isinstance(env, dict):
            env_dict = env

        self.assertIn("AUTORUN", env_dict)
        self.assertIn("MODE", env_dict)
        self.assertEqual(str(env_dict.get("ENABLE_NOVNC", "")).lower(), "false")

    def test_compose_volumes_and_restart_policy(self):
        """Verifies custom config volume mount and restart policy."""
        service = self.data["services"]["aircursor"]
        volumes = [str(v) for v in service.get("volumes", [])]
        self.assertTrue(any("config" in v for v in volumes), "Must mount custom configs volume")
        restart = service.get("restart", "")
        self.assertIn(restart, ("unless-stopped", "always"))

    def test_compose_healthcheck(self):
        """Verifies healthcheck targets http://localhost:8765/status."""
        service = self.data["services"]["aircursor"]
        hc = service.get("healthcheck", {})
        test_cmd = str(hc.get("test", ""))
        self.assertIn("http://localhost:8765/status", test_cmd)


class TestKubernetesOfflineManifests(unittest.TestCase):
    """Subject 07: Kubernetes production offline manifests (deployment, service, configmap, ingress, kustomization)."""

    def setUp(self):
        self.k8s_dir = ROOT_DIR / "k8s"
        self.assertTrue(self.k8s_dir.is_dir(), "k8s/ directory must exist")

    def test_k8s_files_exist(self):
        """Verifies all required k8s manifest files are present."""
        expected = [
            "deployment.yaml",
            "service.yaml",
            "configmap.yaml",
            "ingress.yaml",
            "kustomization.yaml",
        ]
        for name in expected:
            f = self.k8s_dir / name
            self.assertTrue(f.exists(), f"k8s/{name} must exist")

    def test_deployment_schema(self):
        """Validates Deployment resource limits, offline pull policy, and health probes."""
        dep_path = self.k8s_dir / "deployment.yaml"
        with open(dep_path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)

        self.assertEqual(doc.get("kind"), "Deployment")
        self.assertIn("spec", doc)
        self.assertGreaterEqual(doc["spec"].get("replicas", 0), 1)

        template = doc["spec"]["template"]
        containers = template["spec"]["containers"]
        self.assertEqual(len(containers), 1)
        c = containers[0]

        # Offline pull policy: IfNotPresent
        self.assertEqual(c.get("imagePullPolicy"), "IfNotPresent")

        # Ports
        port_names = {p["name"]: p["containerPort"] for p in c.get("ports", [])}
        self.assertEqual(port_names.get("http-web"), 8765)
        self.assertEqual(port_names.get("udp-sensor"), 4242)
        self.assertNotIn(6080, port_names.values(), "noVNC must be disabled in the default pod")

        # Liveness & Readiness Probes
        live = c.get("livenessProbe", {}).get("httpGet", {})
        ready = c.get("readinessProbe", {}).get("httpGet", {})
        self.assertEqual(live.get("path"), "/status")
        self.assertEqual(live.get("port"), 8765)
        self.assertEqual(ready.get("path"), "/status")
        self.assertEqual(ready.get("port"), 8765)

        # Resource limits and requests
        resources = c.get("resources", {})
        self.assertIn("requests", resources)
        self.assertIn("limits", resources)

        # Non-root security context
        sec = template["spec"].get("securityContext", {})
        self.assertTrue(sec.get("runAsNonRoot"))
        self.assertEqual(sec.get("runAsUser"), 1000)

    def test_service_schema(self):
        """Validates Service definitions for HTTP (8765) and UDP (4242)."""
        svc_path = self.k8s_dir / "service.yaml"
        with open(svc_path, "r", encoding="utf-8") as f:
            docs = list(yaml.safe_load_all(f))

        self.assertEqual(len(docs), 1, "Only the internal ClusterIP service should be applied by default")
        self.assertEqual(docs[0]["spec"].get("type"), "ClusterIP")
        found_http = False
        found_udp = False

        for doc in docs:
            self.assertEqual(doc.get("kind"), "Service")
            ports = doc["spec"].get("ports", [])
            for p in ports:
                if p.get("port") == 8765 and p.get("protocol") == "TCP":
                    found_http = True
                if p.get("port") == 4242 and p.get("protocol") == "UDP":
                    found_udp = True
                self.assertNotEqual(p.get("port"), 6080, "noVNC must not be exposed by default")

        self.assertTrue(found_http, "k8s service must expose port 8765 TCP")
        self.assertTrue(found_udp, "k8s service must expose port 4242 UDP")

    def test_configmap_schema(self):
        """Validates centralized configmap containing sensitivity, dwell, gestures, and ports."""
        cm_path = self.k8s_dir / "configmap.yaml"
        with open(cm_path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)

        self.assertEqual(doc.get("kind"), "ConfigMap")
        data = doc.get("data", {})
        self.assertIn("HTTP_PORT", data)
        self.assertIn("UDP_PORT", data)
        self.assertIn("SENSITIVITY", data)
        self.assertIn("DWELL_DURATION", data)
        self.assertIn("ENABLE_NOD", data)
        self.assertIn("ENABLE_SHAKE", data)
        self.assertIn("ENABLE_TILT", data)
        self.assertEqual(data.get("ENABLE_NOVNC"), "false")
        self.assertIn("settings.json", data)

        # Embedded JSON settings must be valid
        embedded_json = json.loads(data["settings.json"])
        self.assertIn("pointer", embedded_json)
        self.assertIn("dwell", embedded_json)
        self.assertIn("gestures", embedded_json)

    def test_ingress_schema(self):
        """Validates Ingress resource routing for Web Remote."""
        ing_path = self.k8s_dir / "ingress.yaml"
        with open(ing_path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)

        self.assertEqual(doc.get("kind"), "Ingress")
        rules = doc["spec"].get("rules", [])
        self.assertGreaterEqual(len(rules), 1)
        paths = rules[0]["http"]["paths"]
        root_path = next((p for p in paths if p["path"] == "/"), None)
        self.assertIsNotNone(root_path, "Ingress must route path / to Web Remote")
        self.assertEqual(root_path["backend"]["service"]["port"]["number"], 8765)
        self.assertTrue(doc["spec"].get("tls"), "Ingress must require TLS for bearer-token transport")
        self.assertEqual(doc["spec"]["rules"][0].get("host"), "aircursor.example.com")
        self.assertFalse(any(p["path"].startswith("/vnc") for p in paths), "noVNC must not be routed")

    def test_kustomization_schema(self):
        """Validates kustomization.yaml references all components."""
        kust_path = self.k8s_dir / "kustomization.yaml"
        with open(kust_path, "r", encoding="utf-8") as f:
            doc = yaml.safe_load(f)

        self.assertEqual(doc.get("kind"), "Kustomization")
        resources = doc.get("resources", [])
        self.assertIn("deployment.yaml", resources)
        self.assertIn("service.yaml", resources)
        self.assertIn("configmap.yaml", resources)
        self.assertIn("ingress.yaml", resources)

    def test_kubectl_kustomize_execution(self):
        """Runs 'kubectl kustomize k8s/' if kubectl is installed on the system."""
        try:
            res = subprocess.run(
                ["kubectl", "kustomize", str(self.k8s_dir)],
                capture_output=True,
                text=True,
                check=False,
            )
            if res.returncode == 0:
                self.assertIn("kind: Deployment", res.stdout)
                self.assertIn("kind: Service", res.stdout)
                self.assertIn("kind: ConfigMap", res.stdout)
                self.assertIn("kind: Ingress", res.stdout)
        except FileNotFoundError:
            # kubectl not installed in environment, skip execution test
            pass


class TestOfflinePackaging(unittest.TestCase):
    """Subject 08: Offline 'Write Once, Run Anywhere' distribution packager."""

    @classmethod
    def setUpClass(cls):
        # Run bundle packaging
        cls.bundle_dir, cls.zip_path, cls.manifest = build_offline_bundle()

    def test_bundle_artifacts_exist(self):
        """Verifies bundle directory, zip file, and MANIFEST.json exist."""
        self.assertTrue(self.bundle_dir.exists())
        self.assertTrue(self.zip_path.exists())
        self.assertTrue((self.bundle_dir / "MANIFEST.json").exists())

    def test_zip_archive_integrity(self):
        """Verifies zip archive passes testzip() and contains expected structure."""
        with zipfile.ZipFile(self.zip_path, "r") as zf:
            corrupt = zf.testzip()
            self.assertIsNone(corrupt, "Zip archive must not contain corrupt files")
            names = zf.namelist()
            # Must include core, web, launchers, docs
            self.assertTrue(any("aircursor_core" in n for n in names))
            self.assertTrue(any("web/index.html" in n for n in names))
            self.assertTrue(any("Start-AirCursor.bat" in n for n in names))
            self.assertTrue(any("start-aircursor.sh" in n for n in names))
            self.assertTrue(any("docs/OFFLINE_GUIDE.md" in n for n in names))

    def test_zero_external_cdn_references(self):
        """Guarantees 100% offline self-containment with zero external CDN dependencies."""
        for root, _, files in os.walk(self.bundle_dir):
            for file in files:
                p = Path(root) / file
                issues = verify_file_offline_readiness(p)
                self.assertEqual(len(issues), 0, f"Found CDN issue in {p.name}: {issues}")

    def test_manifest_sha256_checksums(self):
        """Verifies MANIFEST.json contains SHA256 checksums for every packaged file."""
        self.assertTrue(self.manifest["offline_verified"])
        self.assertGreater(self.manifest["total_files"], 20)
        for record in self.manifest["files"]:
            self.assertIn("sha256", record)
            self.assertEqual(len(record["sha256"]), 64)


class TestWebRemoteAndStatusAPI(unittest.TestCase):
    """Verifies runtime behavior of Web Remote & /status endpoint on port 8765."""

    @classmethod
    def setUpClass(cls):
        # Use dedicated test ports
        cls.test_http_port = 28765
        cls.test_udp_port = 24242
        cls.server = AirCursorServer(
            host="127.0.0.1",
            http_port=cls.test_http_port,
            udp_port=cls.test_udp_port,
            mode="synthetic",
            autorun=True,
        )
        cls.server.start()
        time.sleep(0.3)

    @classmethod
    def tearDownClass(cls):
        cls.server.stop()

    def test_status_endpoint_contract(self):
        """Tests that GET /status returns 200 OK and valid JSON matching healthcheck spec."""
        url = f"http://127.0.0.1:{self.test_http_port}/status"
        req = urllib.request.Request(url)
        with urllib.request.urlopen(req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")
            self.assertEqual(data.get("service"), "aircursor")
            self.assertEqual(data.get("version"), "1.0.5")
            self.assertTrue(data.get("tracking"))
            self.assertIn("uptime_seconds", data)
            self.assertIn("fps", data)
            self.assertIn("cursor", data)

    def test_settings_api(self):
        """Tests GET and POST /api/settings."""
        # 1. GET settings
        url = f"http://127.0.0.1:{self.test_http_port}/api/settings"
        with urllib.request.urlopen(url, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            cfg = json.loads(resp.read().decode("utf-8"))
            self.assertIn("pointer", cfg)

        # 2. POST update sensitivity
        post_req = urllib.request.Request(
            url,
            data=json.dumps({"sensitivity": 2.4}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.server.access_token,
            },
            method="POST",
        )
        with urllib.request.urlopen(post_req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            updated = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(updated["pointer"]["sensitivity"], 2.4)

    def test_unauthenticated_action_is_rejected(self):
        """The headless API must reject commands without a bearer token."""
        url = f"http://127.0.0.1:{self.test_http_port}/api/action"
        request = urllib.request.Request(
            url,
            data=json.dumps({"action": "recenter"}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with self.assertRaises(urllib.error.HTTPError) as caught:
            urllib.request.urlopen(request, timeout=3.0)
        self.assertEqual(caught.exception.code, 401)

    def test_action_api(self):
        """Tests POST /api/action for recenter and toggle_tracking."""
        url = f"http://127.0.0.1:{self.test_http_port}/api/action"
        post_req = urllib.request.Request(
            url,
            data=json.dumps({"action": "recenter"}).encode("utf-8"),
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self.server.access_token,
            },
            method="POST",
        )
        with urllib.request.urlopen(post_req, timeout=3.0) as resp:
            self.assertEqual(resp.status, 200)
            data = json.loads(resp.read().decode("utf-8"))
            self.assertEqual(data.get("status"), "ok")

    def test_pwa_static_assets(self):
        """Tests static asset serving: index.html, manifest, service worker, CSS, JS."""
        base_url = f"http://127.0.0.1:{self.test_http_port}"
        assets = [
            ("/", "text/html"),
            ("/manifest.webmanifest", "application/manifest+json"),
            ("/sw.js", "javascript"),
            ("/css/app.css", "text/css"),
            ("/js/app.js", "javascript"),
            ("/icons/icon.svg", "svg"),
        ]
        for path, mime_part in assets:
            req = urllib.request.Request(base_url + path)
            with urllib.request.urlopen(req, timeout=3.0) as resp:
                self.assertEqual(resp.status, 200, f"Failed serving {path}")
                content_type = resp.headers.get("Content-Type", "")
                self.assertIn(mime_part, content_type)


if __name__ == "__main__":
    unittest.main()
