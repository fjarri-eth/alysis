class ValidationError(Exception):
    """Invalid values of some of the arguments."""

    pass


class BlockNotFound(Exception):
    """Requested block cannot be found."""

    pass


class TransactionNotFound(Exception):
    """Requested transaction cannot be found."""

    pass


class FilterNotFound(Exception):
    """Requested filter cannot be found."""

    pass


class SnapshotNotFound(Exception):
    """Requested snapshot cannot be found."""

    pass


class TransactionFailed(Exception):
    """Transaction could not be executed."""

    pass


class TransactionReverted(Exception):
    """Transaction was partially executed, but had to be reverted."""

    pass
