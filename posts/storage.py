from cloudinary_storage.storage import MediaCloudinaryStorage


class AutoMediaCloudinaryStorage(MediaCloudinaryStorage):
    """
    resource_type='auto' ব্যবহার করে image + video দুটোই support করে।
    এবং double-nested Cloudinary URL সমস্যা fix করে।
    """
    RESOURCE_TYPE = 'auto'

    def _save(self, name, content):
        # যদি name-এ Cloudinary URL ঢুকে যায় সেটা clean করা হচ্ছে
        # double-nested URL prevent করতে শুধু filename রাখা হচ্ছে
        if 'res.cloudinary.com' in str(name):
            name = str(name).split('/')[-1]
        return super()._save(name, content)