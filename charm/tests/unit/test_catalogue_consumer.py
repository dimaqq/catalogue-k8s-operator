# Copyright 2022 Canonical Ltd.
# See LICENSE file for licensing details.
#
# Learn more about testing at: https://juju.is/docs/sdk/testing

import json
import textwrap
import unittest
from unittest.mock import patch

from charms.catalogue_k8s.v1.catalogue import CatalogueConsumer, CatalogueItem
from ops.charm import CharmBase
from ops.framework import BoundEvent, EventBase, EventSource, Object, ObjectEvents
from ops.model import ActiveStatus
from ops.testing import Harness


class CustomEvent(EventBase):
    """Some custom event that is emitted mid-hook (without charm re-init)."""


class DummyEvents(ObjectEvents):
    """Dummy events."""

    custom_event = EventSource(CustomEvent)


class DummyLib(Object):
    on = DummyEvents()

    def __init__(self, charm):
        super().__init__(charm, "some_relation_name")
        self.some_dynamic_value = ""  # will be updated later, e.g. via a core event

    def update_something(self, something: str):
        self.some_dynamic_value = something
        self.on.custom_event.emit()


class DummyConsumerCharm(CharmBase):
    metadata_yaml = textwrap.dedent(
        """
        name: DummyConsumerCharm
        requires:
          catalogue:
            interface: catalogue
        """
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args)
        self.dummy_lib = DummyLib(self)

        # The dynamic value is updated in leader-elected
        self.framework.observe(self.on.leader_elected, self._on_leader_elected)

        self.catalogue = CatalogueConsumer(
            charm=self,
            refresh_event=[
                self.dummy_lib.on.custom_event,
            ],
            item_getter=lambda: CatalogueItem(
                name=self.dynamic_name(),
                url=self.dynamic_url(),
                icon=self.dynamic_icon(),
            ),
        )

    def _on_leader_elected(self, _):
        self.dummy_lib.update_something("foo")
        # at this point, the self.catalogue item should have "foo"

    def dynamic_name(self):
        return "DummyCharm-" + self.dummy_lib.some_dynamic_value

    def dynamic_url(self):
        return "http://some.url/" + self.dummy_lib.some_dynamic_value

    def dynamic_icon(self):
        return "some-cool-icon-" + self.dummy_lib.some_dynamic_value


class TestDeferredEvaluation(unittest.TestCase):
    def setUp(self) -> None:
        self.harness = Harness(DummyConsumerCharm, meta=DummyConsumerCharm.metadata_yaml)
        self.addCleanup(self.harness.cleanup)

        self.rel_id = self.harness.add_relation("catalogue", "catalogue-provider-app")

    def test_item_updated_after_charm_init(self):
        # WHEN a catalogue instance is only instantiated
        self.harness.set_leader(False)
        self.harness.begin_with_initial_hooks()

        # THEN no relation data is present
        app_data = self.harness.get_relation_data(self.rel_id, self.harness.charm.app.name)
        self.assertEqual(app_data, {})

        # WHEN a custom refresh event is observed (via a core event, in this case: leader-elected)
        self.harness.set_leader(True)

        # THEN the catalogue consumer is deferring evaluation and as a result relation data is
        # up-to-date and includes the dynamic value
        app_data = self.harness.get_relation_data(self.rel_id, self.harness.charm.app.name)
        self.assertEqual(
            app_data,
            {"name": "DummyCharm-foo", "url": "http://some.url/foo", "icon": "some-cool-icon-foo"},
        )
