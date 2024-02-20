import itertools
from typing import List, Union

from eth_typing import Address, Hash32
from eth_utils import encode_hex

from .backend import PyEVMBackend
from .exceptions import (
    FilterNotFound,
    SnapshotNotFound,
    TransactionNotFound,
    ValidationError,
)
from .schema import Block, BlockLabel, EstimateGas, FilterParams, TransactionCall
from .serializers import BlockInfo, LogEntry, TransactionInfo, TransactionReceipt


class LogFilter:
    def __init__(self, params: FilterParams, current_block_number: int):
        if isinstance(params.from_block, int):
            from_block = params.from_block
        elif params.from_block in (BlockLabel.LATEST, BlockLabel.SAFE, BlockLabel.FINALIZED):
            # TODO: don't need the whole block here
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

        if isinstance(params.address, list):
            addresses = params.address
        elif params.address is None:
            addresses = None
        else:
            addresses = [params.address]

        self._from_block = from_block
        self._to_block = to_block
        self._addresses = addresses
        self._topics = params.topics

    def matches(self, entry: LogEntry) -> bool:
        if entry.block_number < self._from_block:
            return False

        if self._to_block is not None and entry.block_number > self._to_block:
            return False

        if self._addresses is not None and entry.address not in self._addresses:
            return False

        if self._topics is None:
            return True

        # TODO: what's the behavior if the length of topics in the filter
        # is larger than that in the log? Just mismatch? Error?
        for topics, logged_topic in zip(self._topics, entry.topics):
            if topics is None:
                continue

            if not isinstance(topics, list):
                filter_topics = [topics]
            else:
                filter_topics = topics

            for filter_topic in filter_topics:
                if filter_topic == logged_topic:
                    break
            else:
                return False

        return True


class Node:
    DEFAULT_ID = int.from_bytes(b"alysis", byteorder="big")

    def __init__(
        self,
        root_balance_wei: int,
        chain_id: int = DEFAULT_ID,
        *,
        auto_mine_transactions: bool = True,
    ):
        backend = PyEVMBackend(root_balance_wei=root_balance_wei, chain_id=chain_id)

        self.root_private_key = backend.root_private_key

        self.backend = backend

        self._auto_mine_transactions = auto_mine_transactions

        # filter tracking
        self._filter_counter = itertools.count()
        self._log_filters = {}
        self._log_filter_entries = {}
        self._block_filters = {}
        self._pending_transaction_filters = {}

        # snapshot tracking
        self._snapshot_counter = itertools.count()
        self._snapshots = {}

    def advance_time(self, to_timestamp: int) -> None:
        # make sure we are not traveling back in time as this is not possible.
        # TODO: don't need the whole block here
        current_timestamp = self.get_block_by_number(
            BlockLabel.PENDING, with_transactions=False
        ).timestamp
        if to_timestamp == current_timestamp:
            # no change, return immediately
            return
        if to_timestamp < current_timestamp:
            raise ValidationError(
                f"The new timestamp ({to_timestamp}) must be greater than "
                f"the current one ({current_timestamp})"
            )
        self.backend.advance_time(to_timestamp)

    def enable_auto_mine_transactions(self) -> None:
        self._auto_mine_transactions = True
        self.mine_block()

    def disable_auto_mine_transactions(self) -> None:
        self._auto_mine_transactions = False

    def mine_block(self) -> None:
        block = self.backend.mine_block()

        # feed the block hash to any block filters
        for block_filter in self._block_filters.values():
            block_filter.append(block.hash)

        for filter_id, log_filter in self._log_filters.items():
            for transaction in block.transactions:
                # TODO: only need log entries here
                receipt = self.backend.get_transaction_receipt(transaction.hash)
                for log_entry in receipt.logs:
                    if log_filter.matches(log_entry):
                        self._log_filter_entries[filter_id].append(log_entry)

    def take_snapshot(self) -> int:
        # TODO: don't need the whole block here
        block = self.backend.get_block_by_number(BlockLabel.LATEST, with_transactions=False)
        snapshot_id = next(self._snapshot_counter)
        self._snapshots[snapshot_id] = block.hash
        return snapshot_id

    def revert_to_snapshot(self, snapshot_id: int) -> None:
        try:
            block_hash = self._snapshots[snapshot_id]
        except KeyError as exc:
            raise SnapshotNotFound(f"No snapshot found for id: {snapshot_id}") from exc
        else:
            self.backend.revert_to_block(block_hash)

        # TODO: revert the filter state

    def net_version(self) -> int:
        # TODO: make adjustable
        return 1

    def chain_id(self) -> int:
        return self.backend.chain_id

    def gas_price(self) -> int:
        # The specific algorithm is not enforced in the standard,
        # but this is the logic Infura uses. Seems to work for them.
        block_info = self.get_block_by_number(BlockLabel.LATEST, with_transactions=False)

        # Base fee plus 1 GWei
        return block_info.base_fee_per_gas + 10**9

    def block_number(self) -> int:
        # TODO: don't need the whole block here
        block = self.backend.get_block_by_number(BlockLabel.LATEST, with_transactions=False)
        return block.number

    def get_balance(self, address: Address, block: Block) -> int:
        return self.backend.get_balance(address, block)

    def get_code(self, address: Address, block: Block) -> bytes:
        return self.backend.get_code(address, block)

    def get_storage_at(
        self,
        address: Address,
        slot: int,
        block: Block,
    ) -> int:
        return self.backend.get_storage(address, slot, block)

    def get_transaction_count(self, address: Address, block: Block) -> int:
        return self.backend.get_transaction_count(address, block)

    def get_transaction_by_hash(self, transaction_hash: Hash32) -> TransactionInfo:
        return self.backend.get_transaction_by_hash(transaction_hash)

    def get_block_by_number(self, block: Block, *, with_transactions: bool) -> BlockInfo:
        return self.backend.get_block_by_number(block, with_transactions=with_transactions)

    def get_block_by_hash(self, block_hash: Hash32, *, with_transactions: bool) -> BlockInfo:
        return self.backend.get_block_by_hash(block_hash, with_transactions=with_transactions)

    def get_transaction_receipt(self, transaction_hash: Hash32) -> TransactionReceipt:
        result = self.backend.get_transaction_receipt(transaction_hash)
        if result is None:
            raise TransactionNotFound(
                f"No transaction found for transaction hash: {encode_hex(transaction_hash)}"
            )
        return result

    def send_raw_transaction(self, raw_transaction: bytes) -> Hash32:
        transaction = self.backend.decode_transaction(raw_transaction)
        transaction_hash = transaction.hash

        for tx_filter in self._pending_transaction_filters.values():
            tx_filter.append(transaction_hash)

        self.backend.send_decoded_transaction(transaction)

        if self._auto_mine_transactions:
            self.mine_block()

        return transaction_hash

    def call(self, transaction: TransactionCall, block: Block) -> bytes:
        return self.backend.call(transaction, block)

    def estimate_gas(self, transaction: EstimateGas, block: Block) -> int:
        return self.backend.estimate_gas(transaction, block)

    def new_block_filter(self) -> int:
        filter_id = next(self._filter_counter)
        self._block_filters[filter_id] = []
        return filter_id

    def new_pending_transaction_filter(self) -> int:
        filter_id = next(self._filter_counter)
        self._pending_transaction_filters[filter_id] = []
        return filter_id

    def new_filter(self, params: FilterParams) -> int:
        filter_id = next(self._filter_counter)

        # TODO: don't need the whole block here
        current_block_number = self.get_block_by_number(
            BlockLabel.LATEST, with_transactions=False
        ).number
        log_filter = LogFilter(params, current_block_number)

        self._log_filters[filter_id] = log_filter
        self._log_filter_entries[filter_id] = []

        return filter_id

    def delete_filter(self, filter_id: int) -> None:
        if filter_id in self._block_filters:
            del self._block_filters[filter_id]
        elif filter_id in self._pending_transaction_filters:
            del self._pending_transaction_filters[filter_id]
        elif filter_id in self._log_filters:
            del self._log_filters[filter_id]
        else:
            raise FilterNotFound("Unknown filter id")

    def get_filter_changes(
        self, filter_id: int
    ) -> Union[List[LogEntry], List[BlockInfo], List[TransactionInfo]]:
        if filter_id in self._block_filters:
            entries = self._block_filters[filter_id]
            self._block_filters[filter_id] = []
            return entries

        if filter_id in self._pending_transaction_filters:
            entries = self._pending_transaction_filters[filter_id]
            self._pending_transaction_filters[filter_id] = []
            return entries

        if filter_id in self._log_filters:
            entries = self._log_filter_entries[filter_id]
            self._log_filter_entries[filter_id] = []
            return entries

        raise FilterNotFound("Unknown filter id")

    def _get_logs(self, log_filter: LogFilter) -> List[LogEntry]:
        entries = []

        # TODO: don't need the whole block here
        current_block_number = self.get_block_by_number(
            BlockLabel.LATEST, with_transactions=False
        ).number

        # Enumerate the blocks in the block range to find all log entries which match.
        to_block = (
            log_filter._to_block if log_filter._to_block is not None else current_block_number
        )
        for block_number in range(log_filter._from_block, to_block + 1):
            block = self.get_block_by_number(block_number, with_transactions=False)
            for transaction_hash in block.transactions:
                # TODO: only need log entries here
                receipt = self.backend.get_transaction_receipt(transaction_hash)
                entries.extend(
                    log_entry for log_entry in receipt.logs if log_filter.matches(log_entry)
                )

        return entries

    def get_logs(self, params: FilterParams) -> List[LogEntry]:
        # TODO: don't need the whole block here
        current_block_number = self.get_block_by_number(
            BlockLabel.LATEST, with_transactions=False
        ).number
        log_filter = LogFilter(params, current_block_number)
        return self._get_logs(log_filter)

    def get_filter_logs(self, filter_id: int) -> List[LogEntry]:
        if filter_id in self._log_filters:
            log_filter = self._log_filters[filter_id]
        else:
            raise FilterNotFound("Unknown filter id")

        return self._get_logs(log_filter)
