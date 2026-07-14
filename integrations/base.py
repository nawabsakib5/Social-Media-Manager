from abc import ABC, abstractmethod

class BaseSocialAdapter(ABC):
    """Base adapter for all social media platforms"""
    
    def __init__(self, social_account=None):
        self.social_account = social_account
    
    @abstractmethod
    def publish_post(self, post, platform_status):
        """Publish a post to the platform"""
        pass
    
    @abstractmethod
    def delete_post(self, post, platform_status):
        """Delete a post from the platform"""
        pass
    
    @abstractmethod
    def update_post(self, post, platform_status, new_text):
        """Update a post on the platform"""
        pass
    
    def get_page_token(self, social_account):
        """Get page token for the platform - override in child classes"""
        return social_account.access_token, None
    
    def _is_mock(self):
        """Check if we're in mock/testing mode"""
        return False