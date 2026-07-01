from functools import wraps
from django.http import HttpResponseForbidden
from .models import TeamMember


def get_user_team(user):
    membership = TeamMember.objects.filter(user=user).first()
    if membership:
        return membership.team
    return None


def get_user_role(user, team):
    membership = TeamMember.objects.filter(user=user, team=team).first()
    if membership:
        return membership.role
    return None


def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        team = get_user_team(request.user)
        role = get_user_role(request.user, team)
        if role != 'admin':
            return HttpResponseForbidden("এই কাজের জন্য Admin অ্যাক্সেস দরকার।")
        return view_func(request, *args, **kwargs)
    return wrapper