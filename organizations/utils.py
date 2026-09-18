from .models import Membership


def get_user_organization(user):
    """User-এর Membership দেখে তার Organization return করে।
    Membership না থাকলে None return করে।"""
    if not user or not user.is_authenticated:
        return None
    membership = (
        Membership.objects
        .select_related('organization')
        .filter(user=user, organization__is_active=True)
        .first()
    )
    return membership.organization if membership else None