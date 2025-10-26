from copy import deepcopy
from typing import Any

from ethereum_rpc import (
    Address,
    Amount,
    Block,
    BlockHash,
    BlockInfo,
    BlockLabel,
    EstimateGasParams,
    EthCallParams,
    FilterParams,
    FilterParamsEIP234,
    LogEntry,
    TxHash,
    TxInfo,
    TxReceipt,
)

from ._backend import PyEVMBackend
from ._constants import EVMVersion
from ._exceptions import FilterNotFound, ValidationError


class LogFilter:
    def __init__(self, params: FilterParams, current_block_number: int):
        if isinstance(params.from_block, int):
            from_block = params.from_block
        elif params.from_block in (BlockLabel.LATEST, BlockLabel.SAFE, BlockLabel.FINALIZED):
            from_block = current_block_number
        elif params.from_block == BlockLabel.EARLIEST:
            from_block = 0
        else:
            raise ValidationError(f"`from_block` value of {params.from_block} is not supported")

        if isinstance(params.to_block, int):
            to_block = params.to_block
        elif params.to_block in (BlockLabel.LATEST, BlockLabel.SAFE, BlockLabel.FINALIZED):
            to_block = None  # indicates an open-ended filter
        elif params.from_block == BlockLabel.EARLIEST:
            to_block = 0
        else:
            raise ValidationError(f"`to_block` value of {params.to_block} is not supported")

        if isinstance(params.address, tuple):
            addresses = params.address
        elif params.address is None:
            addresses = None
        else:
            addresses = (params.address,)

        self._from_block = from_block
        self._to_block = to_block
        self._addresses = addresses
        self._topics = params.topics

    def block_number_range(self, current_block_number: int) -> range:
        to_block = self._to_block if self._to_block is not None else current_block_number
        return range(self._from_block, to_block + 1)

    def matches(self, entry: LogEntry) -> bool:  # noqa: PLR0911
        if entry.block_number < self._from_block:
            return False

        if self._to_block is not None and entry.block_number > self._to_block:
            return False

        if self._addresses is not None and entry.address not in self._addresses:
            return False

        if self._topics is None:
            return True

        # If we filter by more topics than there is in the entry,
        # it's an automatic mismatch.
        if len(self._topics) > len(entry.topics):
            return False

        # But note that if `self._topics` is shorter than `entry.topics`
        # it is equivalent to the missing values being `None`,
        # that is, matching anything.
        for topics, logged_topic in zip(self._topics, entry.topics, strict=False):
            if topics is None:
                continue

            filter_topics = topics if isinstance(topics, tuple) else (topics,)

            for filter_topic in filter_topics:
                if filter_topic == logged_topic:
                    break
            else:
                return False

        return True


class Node:
    """
    An Ethereum node maintaining its own local chain.

    If ``auto_mine_transactions`` is ``True``, a new block is mined
    after every successful transaction.
    """

    DEFAULT_ID = int.from_bytes(b"alysis", byteorder="big")

    root_private_key: bytes
    """The private key of the funded address created with the chain."""

    def __init__(
        self,
        *,
        root_balance_wei: int,
        evm_version: EVMVersion = EVMVersion.PRAGUE,
        chain_id: int = DEFAULT_ID,
        net_version: int = 1,
        auto_mine_transactions: bool = True,
    ):
        backend = PyEVMBackend(
            root_balance_wei=root_balance_wei, chain_id=chain_id, evm_version=evm_version
        )
        self._initialize(
            backend=backend,
            net_version=net_version,
            auto_mine_transactions=auto_mine_transactions,
            filter_counter=0,
            log_filters={},
            log_filter_entries={},
            block_filters={},
            pending_transaction_filters={},
        )

    def _initialize(
        self,
        backend: PyEVMBackend,
        net_version: int,
        auto_mine_transactions: bool,  # noqa: FBT001
        filter_counter: int,
        log_filters: dict[int, LogFilter],
        log_filter_entries: dict[int, list[LogEntry]],
        block_filters: dict[int, list[BlockHash]],
        pending_transaction_filters: dict[int, list[TxHash]],
    ) -> None:
        self.root_private_key = backend.root_private_key
        self._backend = backend
        self._auto_mine_transactions = auto_mine_transactions
        self._net_version = net_version

        # filter tracking
        self._filter_counter = filter_counter
        self._log_filters = log_filters
        self._log_filter_entries = log_filter_entries
        self._block_filters = block_filters
        self._pending_transaction_filters = pending_transaction_filters

    def __deepcopy__(self, memo: None | dict[Any, Any]) -> "Node":
        """
        Makes a copy of this object that includes the chain state
        (with the pending transactions) and the filter state.
        """
        obj = object.__new__(self.__class__)
        obj._initialize(  # noqa: SLF001
            backend=deepcopy(self._backend, memo),
            net_version=self._net_version,
            auto_mine_transactions=self._auto_mine_transactions,
            filter_counter=self._filter_counter,
            # Shallow copy is enough, LogFilter objects are immutable
            log_filters=dict(self._log_filters),
            # One level deep copy is enough here
            log_filter_entries={key: val[:] for key, val in self._log_filter_entries.items()},
            block_filters={key: val[:] for key, val in self._block_filters.items()},
            pending_transaction_filters={
                key: val[:] for key, val in self._pending_transaction_filters.items()
            },
        )
        return obj

    def enable_auto_mine_transactions(self) -> None:
        """Turns automining on and mines a new block."""
        self._auto_mine_transactions = True
        self.mine_block()

    def disable_auto_mine_transactions(self) -> None:
        """Turns automining off."""
        self._auto_mine_transactions = False

    def mine_block(self, timestamp: None | int = None) -> None:
        """
        Mines a new block containing all the pending transactions.

        If ``timestamp`` is not ``None``, sets the new block's timestamp to the given value.
        """
        block_hash = self._backend.mine_block(timestamp=timestamp)

        # feed the block hash to any block filters
        for block_filter in self._block_filters.values():
            block_filter.append(block_hash)

        for filter_id, log_filter in self._log_filters.items():
            log_entries = self._backend.get_log_entries_by_block_hash(block_hash)
            for log_entry in log_entries:
                if log_filter.matches(log_entry):
                    self._log_filter_entries[filter_id].append(log_entry)

    def net_version(self) -> int:
        """Returns the current network id."""
        return self._net_version

    def web3_client_version(self) -> str:
        return "Alysis testerchain"

    def eth_chain_id(self) -> int:
        """Returns the chain ID used for signing replay-protected transactions."""
        return self._backend.chain_id

    def eth_gas_price(self) -> Amount:
        """Returns an estimate of the current price per gas in wei."""
        # The specific algorithm is not enforced in the standard,
        # but this is the logic Infura uses. Seems to work for them.
        block_info = self.eth_get_block_by_number(BlockLabel.LATEST, with_transactions=False)

        # Base fee plus 1 GWei
        return block_info.base_fee_per_gas + Amount.gwei(1)

    def eth_block_number(self) -> int:
        """Returns the number of most recent block."""
        return self._backend.get_latest_block_number()

    def eth_get_balance(self, address: Address, block: Block) -> int:
        """Returns the balance (in wei) of the account of given address."""
        return self._backend.get_balance(address, block)

    def eth_get_code(self, address: Address, block: Block) -> bytes:
        """Returns code of the contract at a given address."""
        return self._backend.get_code(address, block)

    def eth_get_storage_at(
        self,
        address: Address,
        slot: int,
        block: Block,
    ) -> bytes:
        """Returns the value from a storage position at a given address."""
        return self._backend.get_storage(address, slot, block)

    def eth_get_transaction_count(self, address: Address, block: Block) -> int:
        """Returns the number of transactions sent from an address."""
        return self._backend.get_transaction_count(address, block)

    def eth_get_transaction_by_hash(self, transaction_hash: TxHash) -> TxInfo:
        """
        Returns the information about a transaction requested by transaction hash.

        Raises :py:class:`TransactionNotFound` if the transaction with this hash
        has not been included in a block yet.
        """
        return self._backend.get_transaction_by_hash(transaction_hash)

    def eth_get_block_by_number(self, block: Block, *, with_transactions: bool) -> BlockInfo:
        """
        Returns information about a block by block number.

        Raises :py:class:`BlockNotFound` if the requested block does not exist.
        """
        return self._backend.get_block_by_number(block, with_transactions=with_transactions)

    def eth_get_block_by_hash(self, block_hash: BlockHash, *, with_transactions: bool) -> BlockInfo:
        """
        Returns information about a block by hash.

        Raises :py:class:`BlockNotFound` if the requested block does not exist.
        """
        return self._backend.get_block_by_hash(block_hash, with_transactions=with_transactions)

    def eth_get_transaction_receipt(self, transaction_hash: TxHash) -> TxReceipt:
        """
        Returns the receipt of a transaction by transaction hash.

        Raises :py:class:`TransactionNotFound` if the transaction with this hash
        has not been included in a block yet.
        """
        return self._backend.get_transaction_receipt(transaction_hash)

    def eth_send_raw_transaction(self, raw_transaction: bytes) -> TxHash:
        """
        Attempts to add a signed RLP-encoded transaction to the current block.
        Returns the transaction hash on success.

        If the transaction is invalid, raises :py:class:`ValidationError`.
        If the transaction is sent to the EVM but is reverted during execution,
        raises :py:class:`TransactionReverted`.
        If there were other problems with the transaction, raises :py:class:`TransactionFailed`.
        """
        transaction = self._backend.decode_transaction(raw_transaction)
        transaction_hash = TxHash(transaction.hash)

        for tx_filter in self._pending_transaction_filters.values():
            tx_filter.append(transaction_hash)

        self._backend.send_decoded_transaction(transaction)

        if self._auto_mine_transactions:
            self.mine_block()

        return transaction_hash

    def eth_call(self, params: EthCallParams, block: Block) -> bytes:
        """
        Executes a new message call immediately without creating a transaction on the blockchain.

        If the transaction is invalid, raises :py:class:`ValidationError`.
        If the transaction is sent to the EVM but is reverted during execution,
        raises :py:class:`TransactionReverted`.
        If there were other problems with the transaction, raises :py:class:`TransactionFailed`.
        """
        return self._backend.call(params, block)

    def eth_estimate_gas(self, params: EstimateGasParams, block: Block) -> int:
        """
        Generates and returns an estimate of how much gas is necessary to allow
        the transaction to complete. The transaction will not be added to the blockchain.

        If the transaction is invalid, raises :py:class:`ValidationError`.
        If the transaction is sent to the EVM but is reverted during execution,
        raises :py:class:`TransactionReverted`.
        If there were other problems with the transaction, raises :py:class:`TransactionFailed`.
        """
        return self._backend.estimate_gas(params, block)

    def eth_new_block_filter(self) -> int:
        """
        Creates a filter in the node, to notify when a new block arrives.
        Returns the identifier of the created filter.
        """
        filter_id = self._filter_counter
        self._filter_counter += 1
        self._block_filters[filter_id] = []
        return filter_id

    def eth_new_pending_transaction_filter(self) -> int:
        """
        Creates a filter in the node, to notify when new pending transactions arrive.
        Returns the identifier of the created filter.
        """
        filter_id = self._filter_counter
        self._filter_counter += 1
        self._pending_transaction_filters[filter_id] = []
        return filter_id

    def eth_new_filter(self, params: FilterParams) -> int:
        """
        Creates a filter object, based on filter options, to notify when the state changes (logs).
        Returns the identifier of the created filter.
        """
        filter_id = self._filter_counter
        self._filter_counter += 1

        current_block_number = self._backend.get_latest_block_number()
        log_filter = LogFilter(params, current_block_number)

        self._log_filters[filter_id] = log_filter
        self._log_filter_entries[filter_id] = []

        return filter_id

    def delete_filter(self, filter_id: int) -> None:
        """Deletes the filter with the given identifier."""
        if filter_id in self._block_filters:
            del self._block_filters[filter_id]
        elif filter_id in self._pending_transaction_filters:
            del self._pending_transaction_filters[filter_id]
        elif filter_id in self._log_filters:
            del self._log_filters[filter_id]
        else:
            raise FilterNotFound("Unknown filter id")

    def eth_get_filter_changes(
        self, filter_id: int
    ) -> list[LogEntry] | list[TxHash] | list[BlockHash]:
        """
        Polling method for a filter, which returns an array of logs which occurred since last poll.

        .. note::

            This method will not return the events that happened before the filter creation,
            even if they satisfy the filter predicate.
            Call :py:meth:`eth_get_filter_logs` to get those.
        """
        if filter_id in self._block_filters:
            block_entries = self._block_filters[filter_id]
            self._block_filters[filter_id] = []
            return block_entries

        if filter_id in self._pending_transaction_filters:
            tx_entries = self._pending_transaction_filters[filter_id]
            self._pending_transaction_filters[filter_id] = []
            return tx_entries

        if filter_id in self._log_filters:
            log_entries = self._log_filter_entries[filter_id]
            self._log_filter_entries[filter_id] = []
            return log_entries

        raise FilterNotFound("Unknown filter id")

    def _get_logs(self, log_filter: LogFilter) -> list[LogEntry]:
        entries = []

        current_block_number = self._backend.get_latest_block_number()

        for block_number in log_filter.block_number_range(current_block_number):
            for log_entry in self._backend.get_log_entries_by_block_number(block_number):
                if log_filter.matches(log_entry):
                    entries.append(log_entry)

        return entries

    def eth_get_logs(self, params: FilterParams | FilterParamsEIP234) -> list[LogEntry]:
        """Returns an array of all logs matching a given filter object."""
        current_block_number = self._backend.get_latest_block_number()

        if isinstance(params, FilterParamsEIP234):
            block_number = self._backend.get_block_number_by_hash(params.block_hash)
            params = FilterParams(
                from_block=block_number,
                to_block=block_number,
                address=params.address,
                topics=params.topics,
            )

        log_filter = LogFilter(params, current_block_number)
        return self._get_logs(log_filter)

    def eth_get_filter_logs(self, filter_id: int) -> list[LogEntry]:
        """Returns an array of all logs matching filter with given id."""
        if filter_id in self._log_filters:
            log_filter = self._log_filters[filter_id]
        else:
            raise FilterNotFound("Unknown filter id")

        return self._get_logs(log_filter)

    def eth_accounts(self) -> list[Address]:
        # Returning an empty list allows us to not implement the related methods
        # (eth_sign, eth_signTransaction, eth_sendTransaction).
        #
        # It is generally not a good idea to keep private keys on the provider's side anyway.
        return []
