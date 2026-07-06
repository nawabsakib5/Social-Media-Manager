from abc import ABC, abstractmethod

class BaseSocialAdapter(ABC):
    def __init__(self, social_account):
        self.social_account = social_account
        self.access_token = social_account.access_token

    @abstractmethod
    def publish_post(self, post) -> dict:
        pass