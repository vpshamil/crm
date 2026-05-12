# crm/api/permissions.py

from rest_framework.permissions import BasePermission, SAFE_METHODS


class IsAdmin(BasePermission):
    """Only admin users."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role == 'admin'


class IsManagerOrAdmin(BasePermission):
    """Managers and admins only."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['manager', 'admin']


class IsSalesRepOrAbove(BasePermission):
    """Any authenticated user (all roles allowed)."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['sales_rep', 'manager', 'admin']


class LeadPermission(BasePermission):
    """
    Role-based permission for leads:
      admin      → full access to all leads
      manager    → full access to all leads
      sales_rep  → can view/create/update only their own leads
                   cannot delete
    """

    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False

        role = request.user.role

        # DELETE only for admin
        if view.action == 'destroy':
            return role == 'admin'

        return role in ['sales_rep', 'manager', 'admin']

    def has_object_permission(self, request, view, obj):
        """
        Called on retrieve, update, partial_update, destroy, custom actions.
        sales_rep can only touch leads assigned to them.
        """
        role = request.user.role

        if role in ['manager', 'admin']:
            return True

        # sales_rep — only their own leads
        return obj.assigned_to == request.user


class AnalyticsPermission(BasePermission):
    """Only managers and admins can see analytics."""
    def has_permission(self, request, view):
        return request.user.is_authenticated and request.user.role in ['manager', 'admin']


class ReadOnlyOrAdmin(BasePermission):
    """
    Anyone can read (GET).
    Only admin can write (POST, PUT, PATCH, DELETE).
    """
    def has_permission(self, request, view):
        if not request.user.is_authenticated:
            return False
        if request.method in SAFE_METHODS:
            return True
        return request.user.role == 'admin'
