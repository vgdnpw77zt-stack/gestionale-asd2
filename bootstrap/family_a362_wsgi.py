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

# A367: administrator-only correction and audit of individual historical attendance.
from a367_attendance_corrections import install as install_a367
install_a367(app)

# A368: scoped collaborator dialogs and compliance readability, no data writes.
from a368_collaboratori_ui import install as install_a368
install_a368(app)

# A370: original ASD folder archive, admin-only, read-only.
from a370_asd_folder_browser import install as install_a370
install_a370(app)

# A371: monthly collaborator hours, signature documents, and persistent folders.
from a371_monthly_collaborators import install as install_a371
install_a371(app)

# A372: single reusable SumUp open-amount link on all eligible Family pages.
from a372_sumup_shared import install as install_a372
install_a372(app)
