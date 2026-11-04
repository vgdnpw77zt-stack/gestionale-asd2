"""Gunicorn entry point; original application imports and routes are preserved."""
import importlib
from app import app
from family_a362_runtime import install
install(app,importlib.import_module('asd_app.routes_bodymind_final'))
# A364 read-only monthly attendance; the existing A362 Home and A309 POSTs remain unchanged.
from a364_monthly_attendance import install as install_a364
install_a364(app)

# A365: show A364 attendance chart inside the existing Family Home.
from a365_home_inline import install as install_a365
install_a365(app)

# A366: replace numeric family due display with status-only presentation.
from a366_family_dues_status import install as install_a366
install_a366(app,importlib.import_module('asd_app.routes_bodymind_final'))
