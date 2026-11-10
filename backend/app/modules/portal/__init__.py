"""Patient portal domain: portal identity links only.

The portal reuses users/sessions/authN. This module owns the single extra
piece of authZ state: which patient a portal user may see, per tenant.
All clinical/billing reads stay in their domain services; the portal API
layer pins `patient_id` from the link resolved here.
"""

from app.modules.portal.models import PortalLink

__all__ = ["PortalLink"]
