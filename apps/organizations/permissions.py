"""The fixed vocabulary of org-scoped permissions an OrganizationRole can
grant — mirrors permissions/roles.py::Resource's role as a small, static
list validated against at role-save time, not a Django Permission/Group
row (those are global; a role here only ever applies within one org).

Adding a new permission is a code change here, same cost/shape as adding a
new Resource for the platform RBAC system — deliberately not a DB-editable
catalog, since this is meant to stay "basic" per the launch-phase brief.
"""
from django.db import models


class OrganizationPermission(models.TextChoices):
    CREATE_CAMPAIGN = 'create_campaign', 'Create Campaign'
    EDIT_CAMPAIGN = 'edit_campaign', 'Edit Campaign'
    DELETE_CAMPAIGN = 'delete_campaign', 'Delete Campaign'
    PAUSE_RESUME_CAMPAIGN = 'pause_resume_campaign', 'Pause/Resume Campaign'
    WITHDRAW_FUNDS = 'withdraw_funds', 'Withdraw Funds'
    MANAGE_MEMBERS = 'manage_members', 'Manage Members'
    MANAGE_ORGANIZATION = 'manage_organization', 'Manage Organization'


ALL_ORGANIZATION_PERMISSIONS = [choice.value for choice in OrganizationPermission]
