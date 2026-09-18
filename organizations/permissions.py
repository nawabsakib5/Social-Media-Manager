from functools import wraps
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404
from .models import Organization, Membership


def get_membership(user, organization):
    if not user.is_authenticated:
        return None
    return Membership.objects.filter(organization=organization, user=user).first()


def user_has_role(user, organization, min_role):
    if user.is_superuser or getattr(user, 'user_type', None) == 'admin':
        return True
    membership = get_membership(user, organization)
    return bool(membership and membership.has_at_least(min_role))


def require_org_role(min_role):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            org_slug = kwargs.get('org_slug')
            org_id = kwargs.get('organization_id')
            if org_slug:
                organization = get_object_or_404(Organization, slug=org_slug)
            elif org_id:
                organization = get_object_or_404(Organization, id=org_id)
            else:
                raise PermissionDenied("Organization context missing.")
            if not user_has_role(request.user, organization, min_role):
                raise PermissionDenied("You don't have the required role.")
            request.organization = organization
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator


def require_role(min_role):
    def decorator(view_func):
        @wraps(view_func)
        def wrapped(request, *args, **kwargs):
            from .utils import get_user_organization
            organization = get_user_organization(request.user)
            if organization is None:
                raise PermissionDenied("You are not part of any organization.")
            if not user_has_role(request.user, organization, min_role):
                raise PermissionDenied("You don't have the required role for this action.")
            request.organization = organization
            return view_func(request, *args, **kwargs)
        return wrapped
    return decorator