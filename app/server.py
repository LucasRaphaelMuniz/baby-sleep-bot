"""App factory do Flask.

Mantido fora de `app/__init__.py` de propósito: assim importar os módulos do
núcleo (`app.core.*`, `app.handler`) não puxa Flask/Supabase/WhatsApp, e os testes
rodam sem essas dependências.
"""
from __future__ import annotations

from flask import Flask
from werkzeug.middleware.proxy_fix import ProxyFix


def create_app() -> Flask:
    app = Flask(__name__)

    # Railway (e outros PaaS) ficam atrás de um proxy que termina o HTTPS.
    # ProxyFix reconstrói esquema/host a partir dos headers X-Forwarded-*,
    # para que request.url reflita a URL pública (https) real.
    app.wsgi_app = ProxyFix(app.wsgi_app, x_proto=1, x_host=1)

    from app.routes.webhook import bp as webhook_bp

    app.register_blueprint(webhook_bp)
    return app
