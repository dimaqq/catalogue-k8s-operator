# Service Catalogue

[![Charmhub Badge](https://charmhub.io/catalogue-k8s/badge.svg)](https://charmhub.io/catalogue-k8s)
[![Release Edge](https://github.com/canonical/catalogue-k8s-operator/actions/workflows/release-edge.yaml/badge.svg)](https://github.com/canonical/catalogue-k8s-operator/actions/workflows/release-edge.yaml)
[![Release Libraries](https://github.com/canonical/catalogue-k8s-operator/actions/workflows/release-libs.yaml/badge.svg)](https://github.com/canonical/catalogue-k8s-operator/actions/workflows/release-libs.yaml)
[![Discourse Status](https://img.shields.io/discourse/status?server=https%3A%2F%2Fdiscourse.charmhub.io&style=flat&label=CharmHub%20Discourse)](https://discourse.charmhub.io)

## Description

The service catalogue is a charmed operator helping users to locate the user interfaces of charms it relates to. 

## Usage

Relate the charm to an ingress of your choice, followed by any charms implementing the providing side of the `dashboard_info` interface.

## OCI Images

The default OCI image for this charm is [the one built as part of this repo](https://github.com/canonical/catalogue-k8s-operator/tree/main/workload). It is published in the GitHub Container Registry as `ghcr.io/canonical/catalogue-k8s-operator`.

## Contributing


Please see the [Juju SDK docs](https://juju.is/docs/sdk) for guidelines on enhancements to this
charm following best practice guidelines, and
[CONTRIBUTING.md](https://github.com/canonical/catalogue-k8s-operator/blob/main/CONTRIBUTING.md) for developer
guidance.
