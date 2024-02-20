from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any, List, Optional, Sequence, Union, cast

import rlp  # type: ignore[import-untyped]
from eth.abc import (
    BlockAPI,
    SignedTransactionAPI,
    TransactionFieldsAPI,
)
from eth.chains.base import MiningChain
from eth.constants import (
    GENESIS_PARENT_HASH,
    POST_MERGE_DIFFICULTY,
    POST_MERGE_MIX_HASH,
    POST_MERGE_NONCE,
)
from eth.db import get_db_backend
from eth.db.header import HeaderDB
from eth.exceptions import HeaderNotFound, Revert, VMError
from eth.typing import AccountDetails
from eth.vm.forks import ShanghaiVM
from eth.vm.forks.berlin.transactions import TypedTransaction
from eth.vm.spoof import SpoofTransaction
from eth_keys import KeyAPI
from eth_typing import Address, BlockNumber, Hash32
from eth_utils import encode_hex, keccak
from eth_utils.exceptions import ValidationError

from .exceptions import (
    BlockNotFound,
    TransactionFailed,
    TransactionNotFound,
    TransactionReverted,
)
from .schema import (
    Block,
    BlockInfo,
    BlockLabel,
    EstimateGasParams,
    EthCallParams,
    LogEntry,
    TransactionInfo,
    TransactionReceipt,
)

if TYPE_CHECKING:
    from eth.abc import (
        BlockAPI,
        BlockHeaderAPI,
        LogAPI,
        ReceiptAPI,
        SignedTransactionAPI,
        TransactionFieldsAPI,
        VirtualMachineAPI,
    )
    from eth.typing import AccountDetails


ZERO_ADDRESS = Address(20 * b"\x00")


def rlp_encode(obj: Any) -> bytes:
    # Force typing here, since `rlp` is not typed
    return cast(bytes, rlp.encode(obj))


class PyEVMBackend:
    def __init__(self, root_balance_wei: int, chain_id: int):
        chain_id_ = chain_id

        class MainnetTesterPosChain(MiningChain):
            chain_id = chain_id_
            vm_configuration = ((BlockNumber(0), ShanghaiVM),)

            def create_header_from_parent(
                self, parent_header: BlockHeaderAPI, **header_params: Any
            ) -> BlockHeaderAPI:
                """
                Call the parent class method maintaining the same gas_limit as the
                previous block.
                """
                header_params["gas_limit"] = parent_header.gas_limit
                return super().create_header_from_parent(parent_header, **header_params)

        blank_root_hash = keccak(rlp_encode(b""))

        genesis_params: dict[str, Union[int, BlockNumber, bytes, Address, Hash32, None]] = {
            "coinbase": ZERO_ADDRESS,
            "difficulty": POST_MERGE_DIFFICULTY,
            "extra_data": b"",
            "gas_limit": 30029122,  # gas limit at London fork block 12965000 on mainnet
            "mix_hash": POST_MERGE_MIX_HASH,
            "nonce": POST_MERGE_NONCE,
            "receipt_root": blank_root_hash,
            "timestamp": int(time.time()),
            "transaction_root": blank_root_hash,
        }

        account_state: AccountDetails = {
            "balance": root_balance_wei,
            "storage": {},
            "code": b"",
            "nonce": 0,
        }

        # TODO: this seems to be hardcoded in PyEVM somehow?
        root_private_key = KeyAPI().PrivateKey(b"\x00" * 31 + b"\x01")

        genesis_state = {Address(root_private_key.public_key.to_canonical_address()): account_state}

        self.chain_id = chain_id
        self.root_private_key = root_private_key
        self.chain = cast(
            MiningChain,
            MainnetTesterPosChain.from_genesis(get_db_backend(), genesis_params, genesis_state),
        )

    def revert_to_block(self, block_hash: Hash32) -> None:
        block = self.chain.get_block_by_hash(Hash32(block_hash))
        chaindb = self.chain.chaindb

        # A little hacky. Is there a better way?
        assert isinstance(chaindb, HeaderDB)
        chaindb._set_as_canonical_chain_head(chaindb.db, block.header, GENESIS_PARENT_HASH)  # noqa: SLF001
        if block.number > 0:
            self.chain.import_block(block)
        else:
            self.chain = cast(MiningChain, self.chain.from_genesis_header(chaindb.db, block.header))

    def advance_time(self, to_timestamp: int) -> None:
        # timestamp adjusted by 1 b/c a second is added in mine_blocks
        self.chain.header = self.chain.header.copy(timestamp=(to_timestamp - 1))
        self.mine_block()

    def get_current_timestamp(self) -> int:
        return self.chain.header.timestamp

    def mine_block(self) -> Hash32:
        # ParisVM and forward, generate a random `mix_hash` to simulate the `prevrandao` value.
        return self.chain.mine_block(coinbase=ZERO_ADDRESS, mix_hash=os.urandom(32)).hash

    def _get_block_by_number(self, block: Block) -> BlockAPI:
        if block in (BlockLabel.LATEST, BlockLabel.SAFE, BlockLabel.FINALIZED):
            head_block = self.chain.get_block()
            return self.chain.get_canonical_block_by_number(
                BlockNumber(max(0, head_block.number - 1))
            )

        if block == BlockLabel.EARLIEST:
            return self.chain.get_canonical_block_by_number(BlockNumber(0))

        if block == BlockLabel.PENDING:
            return self.chain.get_block()

        if isinstance(block, int):
            # Note: The head block is the pending block. If a block number is passed
            # explicitly here, return the block only if it is already part of the chain
            # (i.e. not pending).
            head_block = self.chain.get_block()
            if block < head_block.number:
                return self.chain.get_canonical_block_by_number(BlockNumber(block))

        # fallback
        raise BlockNotFound(f"No block found for block number: {block}")

    def _get_log_entries(self, block: BlockAPI) -> List[LogEntry]:
        receipts = block.get_receipts(self.chain.chaindb)
        entries = []
        for transaction_index, transaction in enumerate(block.transactions):
            receipt = receipts[transaction_index]
            for log_index, log in enumerate(receipt.logs):
                entries.append(
                    make_log_entry(block, transaction, transaction_index, log, log_index)
                )
        return entries

    def get_log_entries_by_block_hash(self, block_hash: Hash32) -> List[LogEntry]:
        return self._get_log_entries(self._get_block_by_hash(block_hash))

    def get_log_entries_by_block_number(self, block: Block) -> List[LogEntry]:
        return self._get_log_entries(self._get_block_by_number(block))

    def get_latest_block_hash(self) -> Hash32:
        return self._get_block_by_number(BlockLabel.LATEST).hash

    def get_latest_block_number(self) -> int:
        return self._get_block_by_number(BlockLabel.LATEST).number

    def get_block_by_number(self, block: Block, *, with_transactions: bool) -> BlockInfo:
        block_api = self._get_block_by_number(block)
        is_pending = block_api.number == self.chain.get_block().number
        return make_block_info(
            self.chain_id, block_api, with_transactions=with_transactions, is_pending=is_pending
        )

    def _get_block_by_hash(self, block_hash: Hash32) -> BlockAPI:
        try:
            block = self.chain.get_block_by_hash(Hash32(block_hash))
        except HeaderNotFound as exc:
            raise BlockNotFound(f"No block found for block hash: {block_hash.hex()}") from exc

        if block.number >= self.chain.get_block().number:
            raise BlockNotFound(f"No block found for block hash: {block_hash.hex()}")

        return block

    def get_block_by_hash(self, block_hash: Hash32, *, with_transactions: bool) -> BlockInfo:
        block = self._get_block_by_hash(block_hash)
        is_pending = block.number == self.chain.get_block().number
        return make_block_info(
            self.chain_id, block, with_transactions=with_transactions, is_pending=is_pending
        )

    def _get_transaction_by_hash(
        self, transaction_hash: Hash32
    ) -> tuple[BlockAPI, TransactionFieldsAPI, int]:
        head_block = self.chain.get_block()
        for index, transaction in enumerate(head_block.transactions):
            if transaction.hash == transaction_hash:
                return head_block, transaction, index
        for block_number in range(head_block.number - 1, -1, -1):
            # TODO: the chain should be able to look these up directly by hash...
            block = self.chain.get_canonical_block_by_number(BlockNumber(block_number))
            for index, transaction in enumerate(block.transactions):
                if transaction.hash == transaction_hash:
                    return block, transaction, index

        raise TransactionNotFound(
            f"No transaction found for transaction hash: {encode_hex(transaction_hash)}"
        )

    def get_transaction_by_hash(self, transaction_hash: Hash32) -> TransactionInfo:
        block, transaction, transaction_index = self._get_transaction_by_hash(
            transaction_hash,
        )
        is_pending = block.number == self.chain.get_block().number
        return make_transaction_info(
            self.chain_id, block, transaction, transaction_index, is_pending=is_pending
        )

    def _get_vm_for_block_number(self, block: Block) -> VirtualMachineAPI:
        block_api = self._get_block_by_number(block)
        return self.chain.get_vm(at_header=block_api.header)

    def get_transaction_receipt(self, transaction_hash: Hash32) -> Optional[TransactionReceipt]:
        block, transaction, transaction_index = self._get_transaction_by_hash(
            transaction_hash,
        )
        is_pending = block.number == self.chain.get_block().number
        if is_pending:
            return None

        block_receipts = block.get_receipts(self.chain.chaindb)

        return make_transaction_receipt(
            block,
            transaction,
            block_receipts,
            transaction_index,
        )

    def get_transaction_count(self, address: Address, block: Block) -> int:
        vm = self._get_vm_for_block_number(block)
        return vm.state.get_nonce(Address(address))

    def get_balance(self, address: Address, block: Block) -> int:
        vm = self._get_vm_for_block_number(block)
        return vm.state.get_balance(Address(address))

    def get_code(self, address: Address, block: Block) -> bytes:
        vm = self._get_vm_for_block_number(block)
        return vm.state.get_code(Address(address))

    def get_storage(self, address: Address, slot: int, block: Block) -> int:
        vm = self._get_vm_for_block_number(block)
        return vm.state.get_storage(Address(address), slot)

    def get_base_fee(self, block: Block) -> int:
        vm = self._get_vm_for_block_number(block)
        return vm.state.base_fee

    def decode_transaction(self, raw_transaction: bytes) -> SignedTransactionAPI:
        vm = self._get_vm_for_block_number(BlockLabel.LATEST)
        return vm.get_transaction_builder().decode(raw_transaction)

    def send_decoded_transaction(self, evm_transaction: SignedTransactionAPI) -> bytes:
        try:
            self.chain.apply_transaction(evm_transaction)
        except ValidationError as exc:
            raise TransactionFailed(exc.args[0]) from exc
        return evm_transaction.hash

    def estimate_gas(self, params: EstimateGasParams, block: Block) -> int:
        from_ = params.from_
        header = self._get_block_by_number(block).header
        nonce = self.get_transaction_count(from_, block) if params.nonce is None else params.nonce
        to = Address(b"") if params.to is None else params.to

        evm_transaction = self.chain.create_unsigned_transaction(
            gas_price=params.gas_price,
            gas=params.gas if params.gas is not None else header.gas_limit,
            nonce=nonce,
            value=params.value,
            data=params.data if params.data is not None else b"",
            to=to,
        )

        spoofed_transaction = SpoofTransaction(evm_transaction, from_=from_)

        try:
            # For whatever reason `SpoofTransaction` does not implement `SignedTransactionAPI`,
            # but has the same duck type.
            return self.chain.estimate_gas(cast(SignedTransactionAPI, spoofed_transaction), header)

        except ValidationError as exc:
            raise TransactionFailed(exc.args[0]) from exc

        except Revert as exc:
            raise TransactionReverted(exc.args[0]) from exc

        except VMError as exc:
            raise TransactionFailed(exc.args[0]) from exc

    def call(self, params: EthCallParams, block: Block) -> bytes:
        from_ = params.from_ or ZERO_ADDRESS
        header = self._get_block_by_number(block).header
        nonce = self.get_transaction_count(from_, block)
        evm_transaction = self.chain.create_unsigned_transaction(
            gas_price=params.gas_price,
            gas=params.gas if params.gas is not None else header.gas_limit,
            nonce=nonce,
            value=params.value,
            data=params.data if params.data is not None else b"",
            to=params.to,
        )
        spoofed_transaction = SpoofTransaction(evm_transaction, from_=from_)

        try:
            # For whatever reason `SpoofTransaction` does not implement `SignedTransactionAPI`,
            # but has the same duck type.
            return self.chain.get_transaction_result(
                cast(SignedTransactionAPI, spoofed_transaction), header
            )

        except ValidationError as exc:
            raise TransactionFailed(exc.args[0]) from exc

        except Revert as exc:
            raise TransactionReverted(exc.args[0]) from exc

        except VMError as exc:
            raise TransactionFailed(exc.args[0]) from exc


def make_block_info(
    chain_id: int, block: BlockAPI, *, with_transactions: bool, is_pending: bool
) -> BlockInfo:
    transactions: Union[List[Hash32], List[TransactionInfo]]
    if with_transactions:
        transactions = [
            make_transaction_info(chain_id, block, transaction, index, is_pending=is_pending)
            for index, transaction in enumerate(block.transactions)
        ]
    else:
        transactions = [transaction.hash for transaction in block.transactions]

    return BlockInfo(
        # While the docs for major provider say that `number` is `null` for pending blocks,
        # it actually isn't in their return values.
        number=block.header.block_number,
        hash=block.header.hash if not is_pending else None,
        parent_hash=block.header.parent_hash,
        nonce=block.header.nonce if not is_pending else None,
        sha3_uncles=block.header.uncles_hash,
        logs_bloom=block.header.bloom.to_bytes(256, byteorder="big") if not is_pending else None,
        transactions_root=block.header.transaction_root,
        state_root=block.header.state_root,
        receipts_root=block.header.receipt_root,
        miner=block.header.coinbase if not is_pending else None,
        difficulty=block.header.difficulty if not is_pending else 0,
        # TODO: actual total difficulty
        total_difficulty=block.header.difficulty if not is_pending else None,
        extra_data=block.header.extra_data.rjust(32, b"\x00"),
        size=len(rlp_encode(block)),  # TODO: is this right?
        gas_limit=block.header.gas_limit,
        gas_used=block.header.gas_used,
        # Note: this appears after EIP-1559 upgrade. Ethereum.org does not list this field,
        # but it's returned by providers.
        base_fee_per_gas=block.header.base_fee_per_gas,
        timestamp=block.header.timestamp,
        transactions=transactions,
        uncles=[uncle.hash for uncle in block.uncles],
    )


def make_transaction_info(
    chain_id: int,
    block: BlockAPI,
    transaction: TransactionFieldsAPI,
    transaction_index: int,
    *,
    is_pending: bool,
) -> TransactionInfo:
    txn_type = _extract_transaction_type(transaction)
    return TransactionInfo(
        chain_id=chain_id,
        block_hash=None if is_pending else block.hash,
        hash=transaction.hash,
        nonce=transaction.nonce,
        # While the docs for major provider say that `number` is `null`
        # for pending transactions, it actually isn't in their return values.
        block_number=block.number,
        transaction_index=None if is_pending else transaction_index,
        from_=transaction.sender,
        to=transaction.to,
        value=transaction.value,
        gas=transaction.gas,
        max_fee_per_gas=transaction.max_fee_per_gas,
        max_priority_fee_per_gas=transaction.max_priority_fee_per_gas,
        # It is still being returned by providers
        gas_price=(
            transaction.max_fee_per_gas
            if is_pending
            else _calculate_effective_gas_price(transaction, block, txn_type)
        ),
        input=transaction.data,
        type=txn_type,
        r=transaction.r,
        s=transaction.s,
        v=transaction.y_parity,
    )


def make_transaction_receipt(
    block: BlockAPI,
    transaction: TransactionFieldsAPI,
    receipts: Sequence[ReceiptAPI],
    transaction_index: int,
) -> TransactionReceipt:
    txn_type = _extract_transaction_type(transaction)
    receipt = receipts[transaction_index]

    if transaction.to == b"":
        contract_addr = _generate_contract_address(
            transaction.sender,
            transaction.nonce,
        )
    else:
        contract_addr = None

    if transaction_index == 0:
        origin_gas = 0
    else:
        origin_gas = receipts[transaction_index - 1].gas_used

    return TransactionReceipt(
        block_hash=block.hash,
        block_number=block.number,
        contract_address=contract_addr,
        cumulative_gas_used=receipt.gas_used,
        effective_gas_price=_calculate_effective_gas_price(transaction, block, txn_type),
        from_=transaction.sender,
        gas_used=receipt.gas_used - origin_gas,
        logs=[
            make_log_entry(block, transaction, transaction_index, log, log_index)
            for log_index, log in enumerate(receipt.logs)
        ],
        logs_bloom=receipt.bloom.to_bytes(256, byteorder="big"),
        status=1 if receipt.state_root == b"\x01" else 0,
        to=transaction.to or None,
        transaction_hash=transaction.hash,
        transaction_index=transaction_index,
        type=txn_type,
    )


def make_log_entry(
    block: BlockAPI,
    transaction: TransactionFieldsAPI,
    transaction_index: int,
    log: LogAPI,
    log_index: int,
) -> LogEntry:
    return LogEntry(
        address=log.address,
        block_hash=block.hash,
        block_number=block.number,
        data=log.data,
        log_index=log_index,
        removed=False,
        topics=[topic.to_bytes(32, byteorder="big") for topic in log.topics],
        transaction_index=transaction_index,
        transaction_hash=transaction.hash,
    )


def _generate_contract_address(address: Address, nonce: int) -> Address:
    next_account_hash = keccak(rlp_encode([address, nonce]))
    return next_account_hash[-20:]


def _extract_transaction_type(transaction: TransactionFieldsAPI) -> int:
    if isinstance(transaction, TypedTransaction):
        try:
            _ = transaction.gas_price
        except AttributeError:
            return 2
        return 1
    # legacy transactions being '0x0' taken from current geth version v1.10.10
    return 0


def _calculate_effective_gas_price(
    transaction: TransactionFieldsAPI, block: BlockAPI, transaction_type: int
) -> int:
    return (
        min(
            transaction.max_fee_per_gas,
            transaction.max_priority_fee_per_gas + block.header.base_fee_per_gas,
        )
        if transaction_type == 2
        else transaction.gas_price
    )
