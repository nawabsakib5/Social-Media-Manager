"""
IDOR fix — এতদিন posts app-এর প্রায় সব view (`post_detail`, `post_edit`,
`post_delete`, `post_publish_now`, `platform_edit`, `platform_delete`)
শুধু `login_required` চেক করত, কিন্তু post_id-টা আসলে requesting
user-এর নাকি অন্য কারো — সেটা কখনো যাচাই করত না। ফলে URL-এ post_id
পাল্টে যে কোনো logged-in user (এমনকি Viewer role-ও) অন্য কারো/অন্য
team-এর post দেখতে, edit করতে, delete করতে এমনকি publish করতে পারত।

এই module-টা centralized permission check দেয়, যাতে প্রতিটা view-তে
আলাদা আলাদা করে লজিক না লিখে একই জায়গা থেকে maintain করা যায়।
"""
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404

from .models import Post


def user_can_access_post(user, post):
    """App admin/superuser সব post access করতে পারবে। সাধারণ user শুধু
    তখনই access পাবে যদি সে post-টা নিজে বানিয়ে থাকে, অথবা post-টা যেসব
    social account-এ যাচ্ছে তার অন্তত একটায় তার permission থাকে।"""
    if user.is_app_admin:
        return True

    if post.created_by_id == user.id:
        return True

    permitted_account_ids = set(
        user.permitted_accounts.values_list('id', flat=True)
    ) if hasattr(user, 'permitted_accounts') else set()

    post_account_ids = set(post.social_accounts.values_list('id', flat=True))

    return bool(permitted_account_ids & post_account_ids)


def get_permitted_post_or_403(request, post_id, queryset=None):
    """get_object_or_404-এর জায়গায় ব্যবহার করার জন্য — object আছে কিনা
    এবং user-এর access আছে কিনা দুটোই একসাথে চেক করে।"""
    manager = queryset if queryset is not None else Post.objects
    post = get_object_or_404(manager, id=post_id)
    if not user_can_access_post(request.user, post):
        raise PermissionDenied("You don't have permission to access this post.")
    return post