"""Explicit access policies for API views."""

from rest_framework.permissions import BasePermission


class DenyAll(BasePermission):
    """Require every API view to opt into an access policy."""

    def has_permission(self, request: object, view: object) -> bool:
        del request, view
        return False


class IsAdministratorWithOperationPermission(BasePermission):
    """Require an active staff user with each permission declared by the view."""

    def has_permission(self, request: object, view: object) -> bool:
        user = getattr(request, "user", None)
        permissions = getattr(view, "required_operation_permissions", ())
        valid_permissions = (
            isinstance(permissions, tuple)
            and bool(permissions)
            and all(isinstance(permission, str) and bool(permission) for permission in permissions)
        )
        return bool(
            user
            and user.is_authenticated
            and user.is_active
            and user.is_staff
            and valid_permissions
            and user.has_perms(permissions)
        )
