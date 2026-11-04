"""Gunicorn entry point; original application imports and routes are preserved."""
import importlib
from app import app
from family_a362_runtime import install
install(app,importlib.import_module('asd_app.routes_bodymind_final'))
# A364 read-only monthly attendance; the existing A362 Home and A309 POSTs remain unchanged.
from a364_monthly_attendance import install as install_a364
install_a364(app)
