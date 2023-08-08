#!/usr/bin/env python3
# Copyright 2023 Canonical Ltd.
# See LICENSE file for licensing details.
"""Config builder for Nginx."""

import os
from textwrap import dedent

NGINX_CONFIG_PATH = "/etc/nginx/nginx.conf"
CATALOGUE_CERTS_DIR = "/etc/catalogue/certs"
CERT_PATH = os.path.join(CATALOGUE_CERTS_DIR, "catalogue.cert.pem")
KEY_PATH = os.path.join(CATALOGUE_CERTS_DIR, "catalogue.key.pem")
CA_CERT_PATH = os.path.join(CATALOGUE_CERTS_DIR, "ca.cert")

HTTP_SERVICE = """
http {
    include            mime.types;
    default_type       application/octet-stream;
    sendfile           on;
    keepalive_timeout  65;

    upstream self {
      server localhost:80;
    }

    server {
        listen               80;
        server_name          localhost;
        root                 /web;

        error_page           500 502 503 504  /50x.html;
        location = /50x.html {
            root             /usr/share/nginx/html;
        }
    }
}
"""

HTTPS_SERVICE = f"""
http {{
    include             mime.types;
    default_type        application/octet-stream;
    sendfile            on;
    ssl_session_cache   shared:SSL:10m;
    ssl_session_timeout 10m;

    server {{
        listen               443 ssl;
        server_name          localhost;
        keepalive_timeout    70;
        root                 /web;
        ssl_certificate      {CERT_PATH};
        ssl_certificate_key  {KEY_PATH};
        ssl_protocols        TLSv1 TLSv1.1 TLSv1.2 TLSv1.3;
        ssl_ciphers          HIGH:!aNULL:!MD5;

        error_page           500 502 503 504  /50x.html;
        location = /50x.html {{
            root             /usr/share/nginx/html;
        }}
    }}
}}
"""


class NginxConfigBuilder:
    """Class."""

    def __init__(self, tls: bool = False):
        self._tls = tls

    def _nginx_config(self, service: str) -> str:
        return dedent(
            f"""worker_processes  1;
        events {{
            worker_connections  1024;
        }}

        {service}
        """
        )

    def build(self):
        """Build Nginx config file."""
        if self._tls:
            return self._nginx_config(HTTPS_SERVICE)

        return self._nginx_config(HTTP_SERVICE)
