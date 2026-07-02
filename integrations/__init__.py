from .facebook_adapter import FacebookAdapter
from .instagram_adapter import InstagramAdapter
from .twitter_adapter import TwitterAdapter

# Register all social media platform adapters here
ADAPTER_REGISTRY = {
    'facebook': FacebookAdapter,
    'instagram': InstagramAdapter,
    'twitter': TwitterAdapter,
}

def get_social_adapter(social_account):
    adapter_class = ADAPTER_REGISTRY.get(social_account.platform)
    if not adapter_class:
        raise ValueError(f"No social adapter registered for platform: {social_account.platform}")
    return adapter_class(social_account)