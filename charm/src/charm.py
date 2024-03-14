#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charmed operator for creating service catalogues on Kubernetes."""

import json
import logging
import socket
from typing import Optional
from urllib.parse import urlparse

from charms.catalogue_k8s.v1.catalogue import (
    CatalogueItemsChangedEvent,
    CatalogueProvider,
)
from charms.observability_libs.v0.cert_handler import CertHandler
from charms.observability_libs.v1.kubernetes_service_patch import KubernetesServicePatch
from charms.tempo_k8s.v1.charm_tracing import trace_charm
from charms.tempo_k8s.v2.tracing import TracingEndpointRequirer
from charms.traefik_k8s.v2.ingress import (
    IngressPerAppReadyEvent,
    IngressPerAppRequirer,
)
from lightkube.models.core_v1 import ServicePort
from nginx_config import CA_CERT_PATH, CERT_PATH, KEY_PATH, NGINX_CONFIG_PATH, NginxConfigBuilder
from ops.charm import CharmBase
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus, WaitingStatus
from ops.pebble import ChangeError, Error, Layer, PathError, ProtocolError

logger = logging.getLogger(__name__)

ROOT_PATH = "/web"
CONFIG_PATH = ROOT_PATH + "/config.json"


@trace_charm(
    tracing_endpoint="tracing_endpoint",
    server_cert="server_cert_path",
    extra_types=(
        CatalogueProvider,
        CertHandler,
        IngressPerAppRequirer,
        KubernetesServicePatch,
    ),
)
class CatalogueCharm(CharmBase):
    """Catalogue charm class."""

    def __init__(self, *args):
        super().__init__(*args)
        self.name = "catalogue"  # container, layer, service

        port = ServicePort(80, name=f"{self.app.name}")
        self.service_patcher = KubernetesServicePatch(self, [port])

        self._tracing = TracingEndpointRequirer(self, protocols=["otlp_http"])

        self._info = CatalogueProvider(charm=self)

        self.server_cert = CertHandler(
            self,
            key="catalogue-server-cert",
            peer_relation_name="replicas",
            extra_sans_dns=[socket.getfqdn()],
        )
        self._ingress = IngressPerAppRequirer(
            charm=self,
            port=self._internal_port,
            strip_prefix=True,
            scheme=lambda: urlparse(self._internal_url).scheme,
        )
        self.framework.observe(
            self.on.catalogue_pebble_ready, self._on_catalogue_pebble_ready  # pyright: ignore
        )
        self.framework.observe(
            self._info.on.items_changed, self._on_items_changed  # pyright: ignore
        )
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade)
        self.framework.observe(self.on.config_changed, self._on_config_changed)
        self.framework.observe(self._ingress.on.ready, self._on_ingress_ready)  # pyright: ignore
        self.framework.observe(
            self._ingress.on.revoked, self._on_ingress_revoked  # pyright: ignore
        )
        self.framework.observe(
            self.server_cert.on.cert_changed,  # pyright: ignore
            self._on_server_cert_changed,
        )

    def _on_ingress_ready(self, event: IngressPerAppReadyEvent):
        logger.info("This app's ingress URL: %s", event.url)
        self._configure(self.items, push_certs=True)

    def _on_ingress_revoked(self, _):
        logger.info("This app no longer has ingress")
        self._configure(self.items, push_certs=True)

    def _on_catalogue_pebble_ready(self, _):
        # We set push_certs to True here to cover the upgrade sequence. When upgrade-charm fires,
        # the container may not yet be ready, and the certs are written to non-persistent storage
        # (which is a good thing).
        self._configure(self.items, push_certs=True)

    def _update_status(self, status):
        if self.unit.is_leader():
            self.app.status = status
        self.unit.status = status

    def _on_upgrade(self, _):
        # Ideally we would want to push certs on upgrade, but at this point we can't know for sure
        # if pebble-ready (can_connect guard).
        self._configure(self.items)

    def _on_config_changed(self, _):
        self._configure(self.items)

    def _on_items_changed(self, event: CatalogueItemsChangedEvent):
        self._configure(event.items)

    def _on_server_cert_changed(self, _):
        self._configure(self.items, push_certs=True)

        # When server cert changes we need to update the scheme we inform traefik.
        parsed = urlparse(self._internal_url)
        port = parsed.port or 80 if parsed.scheme == "http" else 443
        self._ingress.provide_ingress_requirements(scheme=parsed.scheme, port=port)

    def _push_certs(self):
        for path in [KEY_PATH, CERT_PATH, CA_CERT_PATH]:
            self.workload.remove_path(path, recursive=True)

        if self.server_cert.ca:
            self.workload.push(CA_CERT_PATH, self.server_cert.ca, make_dirs=True)

        if self.server_cert.cert:
            self.workload.push(CERT_PATH, self.server_cert.cert, make_dirs=True)

        if self.server_cert.key:
            self.workload.push(KEY_PATH, self.server_cert.key, make_dirs=True)

    def _configure(self, items, push_certs: bool = False):
        if not self.workload.can_connect():
            self._update_status(WaitingStatus("Waiting for Pebble ready"))
            return

        if push_certs:
            try:
                self._push_certs()
            except (ProtocolError, PathError, Exception) as e:
                self._update_status(BlockedStatus(str(e)))
                logger.error(str(e))
                return

        nginx_config_changed = self._update_web_server_config()
        catalogue_config_changed = self._update_catalogue_config(items)
        pebble_layer_changed = self._update_pebble_layer()
        restart = any([nginx_config_changed, catalogue_config_changed, pebble_layer_changed])

        if restart:
            try:
                self.workload.restart(self.name)
            except ChangeError as e:
                msg = f"Failed to restart Catalogue: {e}"
                self._update_status(BlockedStatus(msg))
                logger.error(msg)
                return

        if self.unit.is_leader():
            self._update_status(ActiveStatus())

    def _update_pebble_layer(self) -> bool:
        current_layer = self.workload.get_plan()

        if current_layer.services == self._pebble_layer.services:
            return False

        self.workload.add_layer(self.name, self._pebble_layer, combine=True)
        self.workload.autostart()
        return True

    def _update_catalogue_config(self, items) -> bool:
        config = {**self.charm_config, "apps": items}

        if self._running_catalogue_config == config:
            return False

        self.workload.push(
            CONFIG_PATH,
            json.dumps({**self.charm_config, "apps": items}),
            make_dirs=True,
        )
        logger.info("Configuring %s application entries", len(items))
        return True

    def _update_web_server_config(self) -> bool:
        config = NginxConfigBuilder(self._is_tls_ready()).build()

        if self._running_nginx_config == config:
            return False

        self.workload.push(NGINX_CONFIG_PATH, config, make_dirs=True)
        logger.info("Configuring NGINX web server.")
        return True

    @property
    def _running_nginx_config(self) -> str:
        """Get the on-disk Nginx config."""
        if not self.workload.can_connect():
            return ""

        try:
            return str(self.workload.pull(NGINX_CONFIG_PATH, encoding="utf-8").read())
        except (FileNotFoundError, Error) as e:
            logger.error("Failed to retrieve Nginx config %s", e)
            return ""

    @property
    def _running_catalogue_config(self) -> dict:
        """Get the on-disk Catalogue config."""
        if not self.workload.can_connect():
            return {}

        try:
            return json.loads(self.workload.pull(CONFIG_PATH, encoding="utf-8").read())
        except (FileNotFoundError, Error) as e:
            logger.error("Failed to retrieve Catalogue config %s", e)
            return {}

    @property
    def _pebble_layer(self) -> Layer:
        return Layer(
            {
                "summary": "catalogue layer",
                "description": "pebble config layer for the catalogue",
                "services": {
                    self.name: {
                        "override": "replace",
                        "summary": "catalogue",
                        "command": f"nginx -g 'daemon off;' -c {NGINX_CONFIG_PATH}",
                        "startup": "enabled",
                    }
                },
            }
        )

    @property
    def items(self):
        """Applications to display in the catalogue."""
        if not self._info:
            return []
        return self._info.items

    @property
    def workload(self):
        """The main workload of the charm."""
        return self.unit.get_container(self.name)

    @property
    def charm_config(self):
        """The part of the charm config that is set through `juju config`."""
        return {
            "title": self.model.config["title"],
            "tagline": self.model.config["tagline"],
            "description": self.model.config.get("description", ""),
            "links": json.loads(self.model.config["links"]),
        }

    def _is_tls_ready(self) -> bool:
        """Returns True if the workload is ready to operate in TLS mode."""
        return (
            self.workload.can_connect()
            and self.server_cert.enabled
            and self.workload.exists(CERT_PATH)
            and self.workload.exists(KEY_PATH)
            and self.workload.exists(CA_CERT_PATH)
        )

    @property
    def _internal_url(self) -> str:
        """Return the fqdn dns-based in-cluster (private) address of the catalogue server."""
        scheme = "https" if self._is_tls_ready() else "http"
        port = 80 if scheme == "http" else 443
        return f"{scheme}://{socket.getfqdn()}:{port}"

    @property
    def _internal_port(self) -> int:
        """Return the port extracted from the internal URL."""
        parsed_url = urlparse(self._internal_url)
        return int(parsed_url.port or 80)

    @property
    def tracing_endpoint(self) -> Optional[str]:
        """Otlp http endpoint for charm instrumentation."""
        if self._tracing.is_ready():
            return self._tracing.get_endpoint("otlp_http")
        return None

    @property
    def server_cert_path(self) -> Optional[str]:
        """Server certificate path for tls tracing."""
        return CERT_PATH


if __name__ == "__main__":
    main(CatalogueCharm)
