from cloudinary_storage.storage import MediaCloudinaryStorage


class AutoMediaCloudinaryStorage(MediaCloudinaryStorage):
    RESOURCE_TYPE = 'auto'