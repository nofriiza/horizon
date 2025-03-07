from django.utils.translation import gettext_lazy as _

# The slug of the panel group to be added to HORIZON_CONFIG. Required.
PANEL_GROUP = 'federation'
# The display name of the PANEL_GROUP. Required.
PANEL_GROUP_NAME = _('Federation')
# The slug of the dashboard the PANEL_GROUP associated with. Required.
PANEL_GROUP_DASHBOARD = 'identity'

DISABLED = True
