"""Gunicorn entry point; original application imports and routes are preserved."""
import importlib
from app import app
from family_a362_runtime import install
install(app,importlib.import_module('asd_app.routes_bodymind_final'))
