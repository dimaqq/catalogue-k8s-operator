#!/usr/bin/env python3
# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more at: https://juju.is/docs/sdk

"""Charmed operator for creating landing pages on Kubernetes."""

import json
import logging

from charms.landing_page_k8s.v0.landing_page import (
    AppsChangedEvent,
    LandingPageProvider,
)
from ops.charm import CharmBase
from ops.framework import StoredState
from ops.main import main
from ops.model import ActiveStatus, BlockedStatus

logger = logging.getLogger(__name__)

ROOT_PATH = "/web"
CONFIG_PATH = ROOT_PATH + "/config.json"


class LandingPageCharm(CharmBase):
    """Charm the service."""

    _stored = StoredState()

    def __init__(self, *args):
        super().__init__(*args)
        self.name = "landing-page-k8s"
        self._info = LandingPageProvider(charm=self)
        self.framework.observe(
            self.on.landing_page_pebble_ready, self._on_landing_page_pebble_ready
        )
        self.framework.observe(self._info.on.apps_changed, self._on_apps_changed)
        self.framework.observe(self.on.upgrade_charm, self._on_upgrade)
        self.framework.observe(self.on.config_changed, self._on_config_changed)

    def _on_landing_page_pebble_ready(self, event):
        """Event handler for the pebble ready event."""
        container = event.workload
        pebble_layer = {
            "summary": "landing page layer",
            "description": "pebble config layer for the landing page",
            "services": {
                "web": {
                    "override": "replace",
                    "summary": "web",
                    "command": "python3 -m http.server 80",
                    "startup": "enabled",
                }
            },
        }
        container.add_layer("web", pebble_layer, combine=True)
        container.autostart()

        try:
            self.configure(self.apps)
        except:  # noqa
            self._update_status(BlockedStatus("Failed to write configuration"))

        self._update_status(ActiveStatus())

    def _update_status(self, status):
        self.app.status = self.unit.status = status

    def _on_upgrade(self, event):
        self.configure(self.apps)

    def _on_config_changed(self, event):
        self.configure(self.apps)

    def _on_apps_changed(self, event: AppsChangedEvent):
        self.configure(event.apps)

    def configure(self, apps):
        """Reconfigures the landing page, writing a new config file to the workload."""
        if not self.workload.can_connect():
            return
        if self.workload.exists(CONFIG_PATH):
            self.workload.remove_path(CONFIG_PATH)

        logger.info("Configuring %s application entries", len(apps))

        self.workload.push(
            CONFIG_PATH, json.dumps({**self.charm_config, "apps": apps}), make_dirs=True
        )

    @property
    def apps(self):
        """Applications to display on the landing page."""
        if not self._info:
            return []
        return self._info.apps

    @property
    def workload(self):
        """The main workload of the charm."""
        return self.unit.get_container("landing-page")

    @property
    def charm_config(self):
        """The part of the charm config that is set through `juju config`."""
        return {
            "title": self.model.config["title"],
            "tagline": self.model.config["tagline"],
            "description": self.model.config.get("description", ""),
            "links": json.loads(self.model.config["links"]),
        }


if __name__ == "__main__":
    main(LandingPageCharm)
