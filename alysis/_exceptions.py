class ValidationError(Exception):
    """Invalid values of some of the arguments."""


class BlockNotFound(Exception):
    """Requested block cannot be found."""


class TransactionNotFound(Exception):
    """Requested transaction cannot be found."""


class FilterNotFound(Exception):
    """Requested filter cannot be found."""


class TransactionFailed(Exception):
    """Transaction could not be executed."""


class TransactionReverted(Exception):
    """Transaction was partially executed, but had to be reverted."""
