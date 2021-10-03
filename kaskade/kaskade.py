import pkg_resources


class Kaskade:
    def __init__(self):
        self.name = "kaskade"
        self.version = pkg_resources.get_distribution("kaskade").version
