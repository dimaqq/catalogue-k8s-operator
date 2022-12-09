# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import json
import unittest
from unittest.mock import patch

from charms.catalogue_k8s.v0.catalogue import DEFAULT_RELATION_NAME
from ops.model import ActiveStatus
from ops.testing import Harness

from charm import CatalogueCharm

CONTAINER_NAME = "catalogue"


class TestCharm(unittest.TestCase):
    @patch("charm.KubernetesServicePatch", lambda x, y: None)
    def setUp(self):
        self.harness = Harness(CatalogueCharm)
        self.addCleanup(self.harness.cleanup)
        self.harness.begin_with_initial_hooks()
        self.harness.set_leader(True)

    def test_catalogue_pebble_ready(self):
        # Given the catalogue container
        # When pebble is ready
        # Then the catalogue web server should be started

        initial_plan = self._plan
        self.assertEqual(initial_plan.to_yaml(), "{}\n")

        expected_plan = {
            "services": {
                "catalogue": {
                    "override": "replace",
                    "summary": "catalogue",
                    "command": "nginx",
                    "startup": "enabled",
                }
            },
        }

        self.harness.charm.on.catalogue_pebble_ready.emit(self._container)

        updated_plan = self._plan.to_dict()
        self.assertEqual(expected_plan, updated_plan)

        service = self._container.get_service("catalogue")
        self.assertTrue(service.is_running())
        self.assertEqual(self.harness.model.unit.status, ActiveStatus())

    def test_reconfigure_applications(self):
        # Given the catalogue and a remote charm
        # When a relation is established
        # Then the remote charm should expose an application entry
        # And the catalogue should write the entry to its config

        rel_id = self.harness.add_relation(DEFAULT_RELATION_NAME, "rc")
        self.harness.add_relation_unit(rel_id, "rc/0")
        self.harness.update_relation_data(
            rel_id,
            "rc",
            {
                "name": "remote-charm",
                "url": "https://localhost",
                "icon": "some-cool-icon",
            },
        )

        data = self._container.pull("/web/config.json")
        self.assertEqual(
            [
                {
                    "name": "remote-charm",
                    "url": "https://localhost",
                    "icon": "some-cool-icon",
                    "description": "",
                }
            ],
            json.loads(data.read())["apps"],
        )

    @property
    def _container(self):
        return self.harness.model.unit.get_container(CONTAINER_NAME)

    @property
    def _plan(self):
        return self.harness.get_container_pebble_plan(CONTAINER_NAME)
