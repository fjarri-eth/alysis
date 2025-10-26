class ValidationError(Exception):
    """Invalid values of some of the arguments."""


class BlockNotFound(Exception):
    """Requested block cannot be found."""


class TransactionNotFound(Exception):
    """Requested transaction cannot be found."""


class IndexNotFound(Exception):
    """Requested index is outside of the available range."""


class FilterNotFound(Exception):
    """Requested filter cannot be found."""


class TransactionFailed(Exception):
    """Transaction could not be executed."""


class TransactionReverted(Exception):
    """Transaction was partially executed, but had to be reverted."""
