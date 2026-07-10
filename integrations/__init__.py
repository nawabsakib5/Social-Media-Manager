from .facebook_adapter import FacebookAdapter
from .instagram_adapter import InstagramAdapter
from .twitter_adapter import TwitterAdapter
from .whatsapp_adapter import WhatsAppAdapter

ADAPTER_REGISTRY = {
    'facebook': FacebookAdapter,
    'instagram': InstagramAdapter,
    'twitter': TwitterAdapter,
    'whatsapp': WhatsAppAdapter,
}

def get_social_adapter(social_account):
    """Return the correct adapter instance for a given SocialAccount."""
    adapter_class = ADAPTER_REGISTRY.get(social_account.platform)
    if not adapter_class:
        raise ValueError(f"No adapter registered for platform: '{social_account.platform}'")
    return adapter_class(social_account)