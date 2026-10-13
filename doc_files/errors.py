"""What can go wrong reading a document."""


class DocumentError(Exception):
    """The file could not be read as the format it claims to be."""


class UnsupportedFormat(DocumentError):
    """No reader handles this kind of file."""


class PasswordRequired(DocumentError):
    """The file is encrypted and no password (or a wrong one) was given."""


class MissingDependency(DocumentError):
    """The reader for this format needs a package that is not installed;
    the message says which, and how to install it."""
