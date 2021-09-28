import pkg_resources

__version__ = version = pkg_resources.get_distribution("kaskade").version
documentation = "https://github.com/sauljabin/kaskade"
name = "kaskade"


class KaskadePackage:
    def __init__(self, name, version, documentation):
        self.name = name
        self.version = version
        self.documentation = documentation


kaskade_package = KaskadePackage(name, version, documentation)
