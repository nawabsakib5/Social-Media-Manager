from abc import ABC, abstractmethod


class BaseSocialAdapter(ABC):
    def __init__(self, social_account):
        self.social_account = social_account
        self.access_token = social_account.access_token  # decrypted token

    @abstractmethod
    def publish_post(self, post) -> dict:
        """
        Publish a post to the platform.
        Must return:
            {'status': 'success', 'platform_post_id': '<id>'}
            {'status': 'failed',  'error_message': '<reason>'}
        """
        pass

    def _is_mock(self) -> bool:
        return self.access_token.startswith("mock_")