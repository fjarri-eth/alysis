"""PyEVM-specific logic. Everything imported from ``eth`` is contained within this module."""

import os
import time
from collections.abc import Sequence
from typing import Any, cast

import rlp  # type: ignore[import-untyped]
from eth.abc import (
    BlockAPI,
    BlockHeaderAPI,
    LogAPI,
    ReceiptAPI,
    SignedTransactionAPI,
    TransactionFieldsAPI,
    VirtualMachineAPI,
)
from eth.chains.base import MiningChain
from eth.constants import (
    POST_MERGE_DIFFICULTY,
    POST_MERGE_MIX_HASH,
    POST_MERGE_NONCE,
)
from eth.db import get_db_backend
from eth.exceptions import HeaderNotFound, Revert, VMError
from eth.tools.builder.chain import copy as copy_chain
from eth.typing import AccountDetails
from eth.vm.forks import ShanghaiVM
from eth.vm.forks.berlin.transactions import TypedTransaction
from eth.vm.spoof import SpoofTransaction
from eth_keys import KeyAPI
from eth_typing import Address as EthAddress
from eth_typing import BlockNumber as EthBlockNumber
from eth_typing import Hash32 as EthHash32
from eth_utils import encode_hex, keccak
from eth_utils.exceptions import ValidationError as EthValidationError

from ._exceptions import (
    BlockNotFound,
    TransactionFailed,
    TransactionNotFound,
    TransactionReverted,
    ValidationError,
)
from .schema import (
    Address,
    Block,
    BlockInfo,
    BlockLabel,
    BlockNonce,
    EstimateGasParams,
    EthCallParams,
    Hash32,
    LogEntry,
    LogsBloom,
    LogTopic,
    TransactionInfo,
    TransactionReceipt,
)

ZERO_ADDRESS = EthAddress(20 * b"\x00")


def _rlp_encode(obj: Any) -> bytes:
    # Force typing here, since `rlp` is not typed
    return cast(bytes, rlp.encode(obj))


class PyEVMBackend:
    def __init__(self, root_balance_wei: int, chain_id: int):
        chain_id_ = chain_id

        class MainnetTesterPosChain(MiningChain):
            chain_id = chain_id_
            vm_configuration = ((EthBlockNumber(0), ShanghaiVM),)

            def create_header_from_parent(
                self, parent_header: BlockHeaderAPI, **header_params: Any
            ) -> BlockHeaderAPI:
                """
                Call the parent class method maintaining the same gas_limit as the
                previous block.
                """
                header_params["gas_limit"] = parent_header.gas_limit
                return super().create_header_from_parent(parent_header, **header_params)

        blank_root_hash = keccak(_rlp_encode(b""))

        genesis_params: dict[str, None | int | EthBlockNumber | bytes | EthAddress | EthHash32] = {
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

        # This seems to be hardcoded in PyEVM somehow.
        root_private_key = KeyAPI().PrivateKey(b"\x00" * 31 + b"\x01")

        genesis_state = {
            EthAddress(root_private_key.public_key.to_canonical_address()): account_state
        }

        chain = cast(
            MiningChain,
            MainnetTesterPosChain.from_genesis(get_db_backend(), genesis_params, genesis_state),
        )

        self._initialize(chain, root_private_key.to_bytes())

    def _initialize(self, chain: MiningChain, root_private_key: bytes) -> None:
        self.chain_id = chain.chain_id
        self.root_private_key = root_private_key
        self.chain = chain

    def __deepcopy__(self, _memo: None | dict[Any, Any]) -> "PyEVMBackend":
        obj = object.__new__(self.__class__)
        obj._initialize(copy_chain(self.chain), self.root_private_key)  # noqa: SLF001
        return obj

    def mine_block(self, timestamp: None | int = None) -> Hash32:
        if timestamp is not None:
            current_timestamp = self.chain.header.timestamp
            if timestamp < current_timestamp:
                raise ValidationError(
                    f"The new timestamp ({timestamp}) must be greater than "
                    f"the current one ({current_timestamp})"
                )

            # timestamp adjusted by 1 b/c a second is added in mine_blocks
            self.chain.header = self.chain.header.copy(timestamp=timestamp - 1)

        # ParisVM and forward, generate a random `mix_hash` to simulate the `prevrandao` value.
        mix_hash = os.urandom(32)

        return Hash32(self.chain.mine_block(coinbase=ZERO_ADDRESS, mix_hash=mix_hash).hash)

    def _get_block_by_number(self, block: Block) -> BlockAPI:
        if isinstance(block, int):
            # Note: The head block is the pending block. If a block number is passed
            # explicitly here, return the block only if it is already part of the chain
            # (i.e. not pending).
            head_block = self.chain.get_block()
            if block < head_block.number:
                return self.chain.get_canonical_block_by_number(EthBlockNumber(block))

        if block in (BlockLabel.LATEST, BlockLabel.SAFE, BlockLabel.FINALIZED):
            head_block = self.chain.get_block()
            return self.chain.get_canonical_block_by_number(
                EthBlockNumber(max(0, head_block.number - 1))
            )

        if block == BlockLabel.EARLIEST:
            return self.chain.get_canonical_block_by_number(EthBlockNumber(0))

        if block == BlockLabel.PENDING:
            return self.chain.get_block()

        # fallback
        raise BlockNotFound(f"No block found for block number: {block}")

    def _get_log_entries(self, block: BlockAPI) -> list[LogEntry]:
        receipts = block.get_receipts(self.chain.chaindb)
        entries = []
        for transaction_index, transaction in enumerate(block.transactions):
            receipt = receipts[transaction_index]
            for log_index, log in enumerate(receipt.logs):
                entries.append(
                    make_log_entry(block, transaction, transaction_index, log, log_index)
                )
        return entries

    def get_log_entries_by_block_hash(self, block_hash: Hash32) -> list[LogEntry]:
        return self._get_log_entries(self._get_block_by_hash(block_hash))

    def get_log_entries_by_block_number(self, block: Block) -> list[LogEntry]:
        return self._get_log_entries(self._get_block_by_number(block))

    def get_latest_block_hash(self) -> Hash32:
        return Hash32(self._get_block_by_number(BlockLabel.LATEST).hash)

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
            block = self.chain.get_block_by_hash(EthHash32(block_hash))
        except HeaderNotFound as exc:
            raise BlockNotFound(f"No block found for block hash: {block_hash.hex()}") from exc

        if block.number >= self.chain.get_block().number:
            raise BlockNotFound(f"No block found for block hash: {block_hash.hex()}")

        return block

    def get_block_number_by_hash(self, block_hash: Hash32) -> int:
        return self._get_block_by_hash(block_hash).number

    def get_block_by_hash(self, block_hash: Hash32, *, with_transactions: bool) -> BlockInfo:
        block = self._get_block_by_hash(block_hash)
        is_pending = block.number == self.chain.get_block().number
        return make_block_info(
            self.chain_id, block, with_transactions=with_transactions, is_pending=is_pending
        )

    def _get_transaction_by_hash(
        self, transaction_hash: Hash32
    ) -> tuple[BlockAPI, SignedTransactionAPI, int]:
        head_block = self.chain.get_block()
        for index, transaction in enumerate(head_block.transactions):
            if Hash32(transaction.hash) == transaction_hash:
                return head_block, transaction, index
        # Since there is no method in PyEvm to get a transaction by hash directly,
        # we have to go through all the blocks, starting from the most recent ones.
        for block_number in range(head_block.number - 1, -1, -1):
            block = self._get_block_by_number(block_number)
            for index, transaction in enumerate(block.transactions):
                if Hash32(transaction.hash) == transaction_hash:
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

    def get_transaction_receipt(self, transaction_hash: Hash32) -> TransactionReceipt:
        block, transaction, transaction_index = self._get_transaction_by_hash(
            transaction_hash,
        )
        is_pending = block.number == self.chain.get_block().number
        if is_pending:
            raise TransactionNotFound(
                f"Transaction {encode_hex(transaction_hash)} is not yet included in a block"
            )

        block_receipts = block.get_receipts(self.chain.chaindb)

        return make_transaction_receipt(
            block,
            transaction,
            block_receipts,
            transaction_index,
        )

    def get_transaction_count(self, address: Address, block: Block) -> int:
        vm = self._get_vm_for_block_number(block)
        return vm.state.get_nonce(EthAddress(address))

    def get_balance(self, address: Address, block: Block) -> int:
        vm = self._get_vm_for_block_number(block)
        return vm.state.get_balance(EthAddress(address))

    def get_code(self, address: Address, block: Block) -> bytes:
        vm = self._get_vm_for_block_number(block)
        return vm.state.get_code(EthAddress(address))

    def get_storage(self, address: Address, slot: int, block: Block) -> bytes:
        vm = self._get_vm_for_block_number(block)
        return vm.state.get_storage(EthAddress(address), slot).to_bytes(32, byteorder="big")

    def get_base_fee(self, block: Block) -> int:
        vm = self._get_vm_for_block_number(block)
        return vm.state.base_fee

    def decode_transaction(self, raw_transaction: bytes) -> SignedTransactionAPI:
        vm = self._get_vm_for_block_number(BlockLabel.LATEST)
        try:
            return vm.get_transaction_builder().decode(raw_transaction)
        except rlp.exceptions.DecodingError as exc:
            raise ValidationError(f"Could not decode transaction: {exc}") from exc

    def send_decoded_transaction(self, evm_transaction: SignedTransactionAPI) -> bytes:
        try:
            self.chain.apply_transaction(evm_transaction)
        except EthValidationError as exc:
            raise ValidationError(f"Invalid transaction: {exc}") from exc
        return evm_transaction.hash

    def estimate_gas(self, params: EstimateGasParams, block: Block) -> int:
        from_ = params.from_
        header = self._get_block_by_number(block).header
        nonce = self.get_transaction_count(from_, block) if params.nonce is None else params.nonce
        to = EthAddress(b"" if params.to is None else params.to)

        evm_transaction = self.chain.create_unsigned_transaction(
            gas_price=params.gas_price,
            gas=params.gas if params.gas is not None else header.gas_limit,
            nonce=nonce,
            value=params.value,
            data=params.data if params.data is not None else b"",
            to=to,
        )

        spoofed_transaction = SpoofTransaction(evm_transaction, from_=EthAddress(from_))

        try:
            # For whatever reason `SpoofTransaction` does not implement `SignedTransactionAPI`,
            # but has the same duck type.
            return self.chain.estimate_gas(cast(SignedTransactionAPI, spoofed_transaction), header)

        except EthValidationError as exc:
            raise ValidationError(f"Invalid transaction: {exc}") from exc

        except Revert as exc:
            raise TransactionReverted(exc.args[0]) from exc

        except VMError as exc:
            raise TransactionFailed(exc.args[0]) from exc

    def call(self, params: EthCallParams, block: Block) -> bytes:
        nonce = self.get_transaction_count(params.from_, block) if params.from_ else 0
        from_ = EthAddress(params.from_) if params.from_ is not None else ZERO_ADDRESS
        header = self._get_block_by_number(block).header
        evm_transaction = self.chain.create_unsigned_transaction(
            gas_price=params.gas_price,
            gas=params.gas if params.gas is not None else header.gas_limit,
            nonce=nonce,
            value=params.value,
            data=params.data if params.data is not None else b"",
            to=EthAddress(params.to),
        )
        spoofed_transaction = SpoofTransaction(evm_transaction, from_=from_)

        try:
            # For whatever reason `SpoofTransaction` does not implement `SignedTransactionAPI`,
            # but has the same duck type.
            return self.chain.get_transaction_result(
                cast(SignedTransactionAPI, spoofed_transaction), header
            )

        except EthValidationError as exc:
            raise ValidationError(f"Invalid transaction: {exc}") from exc

        except Revert as exc:
            raise TransactionReverted(exc.args[0]) from exc

        except VMError as exc:
            raise TransactionFailed(exc.args[0]) from exc


def make_block_info(
    chain_id: int, block: BlockAPI, *, with_transactions: bool, is_pending: bool
) -> BlockInfo:
    transactions: list[Hash32] | list[TransactionInfo]
    if with_transactions:
        transactions = [
            make_transaction_info(chain_id, block, transaction, index, is_pending=is_pending)
            for index, transaction in enumerate(block.transactions)
        ]
    else:
        transactions = [Hash32(transaction.hash) for transaction in block.transactions]

    return BlockInfo(
        # While the docs for major provider say that `number` is `null` for pending blocks,
        # it actually isn't in their return values.
        number=block.header.block_number,
        hash=Hash32(block.header.hash) if not is_pending else None,
        parent_hash=Hash32(block.header.parent_hash),
        nonce=BlockNonce(block.header.nonce) if not is_pending else None,
        sha3_uncles=Hash32(block.header.uncles_hash),
        logs_bloom=LogsBloom(block.header.bloom.to_bytes(256, byteorder="big"))
        if not is_pending
        else None,
        transactions_root=Hash32(block.header.transaction_root),
        state_root=Hash32(block.header.state_root),
        receipts_root=Hash32(block.header.receipt_root),
        miner=Address(block.header.coinbase) if not is_pending else None,
        difficulty=block.header.difficulty if not is_pending else 0,
        # TODO (#15): actual total difficulty
        total_difficulty=block.header.difficulty if not is_pending else None,
        extra_data=block.header.extra_data.rjust(32, b"\x00"),
        size=len(_rlp_encode(block)),  # TODO (#16): is this right?
        gas_limit=block.header.gas_limit,
        gas_used=block.header.gas_used,
        # Note: this appears after EIP-1559 upgrade. Ethereum.org does not list this field,
        # but it's returned by providers.
        # Since we create the VM with Shanghai fork, we can safely cast to int here.
        base_fee_per_gas=cast(int, block.header.base_fee_per_gas),
        timestamp=block.header.timestamp,
        transactions=transactions,
        uncles=[Hash32(uncle.hash) for uncle in block.uncles],
    )


def make_transaction_info(
    chain_id: int,
    block: BlockAPI,
    transaction: SignedTransactionAPI,
    transaction_index: int,
    *,
    is_pending: bool,
) -> TransactionInfo:
    txn_type = _extract_transaction_type(transaction)
    return TransactionInfo(
        chain_id=chain_id,
        block_hash=Hash32(block.hash) if not is_pending else None,
        hash=Hash32(transaction.hash),
        nonce=transaction.nonce,
        # While the docs for major provider say that `number` is `null`
        # for pending transactions, it actually isn't in their return values.
        block_number=block.number,
        transaction_index=None if is_pending else transaction_index,
        from_=Address(transaction.sender),
        to=Address(transaction.to),
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
    transaction: SignedTransactionAPI,
    receipts: Sequence[ReceiptAPI],
    transaction_index: int,
) -> TransactionReceipt:
    txn_type = _extract_transaction_type(transaction)
    receipt = receipts[transaction_index]

    if transaction.to == b"":
        contract_addr = Address(
            _generate_contract_address(
                transaction.sender,
                transaction.nonce,
            )
        )
    else:
        contract_addr = None

    if transaction_index == 0:
        origin_gas = 0
    else:
        origin_gas = receipts[transaction_index - 1].gas_used

    return TransactionReceipt(
        block_hash=Hash32(block.hash),
        block_number=block.number,
        contract_address=contract_addr,
        cumulative_gas_used=receipt.gas_used,
        effective_gas_price=_calculate_effective_gas_price(transaction, block, txn_type),
        from_=Address(transaction.sender),
        gas_used=receipt.gas_used - origin_gas,
        logs=[
            make_log_entry(block, transaction, transaction_index, log, log_index)
            for log_index, log in enumerate(receipt.logs)
        ],
        logs_bloom=LogsBloom(receipt.bloom.to_bytes(256, byteorder="big")),
        status=1 if receipt.state_root == b"\x01" else 0,
        to=Address(transaction.to) or None,
        transaction_hash=Hash32(transaction.hash),
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
        address=Address(log.address),
        block_hash=Hash32(block.hash),
        block_number=block.number,
        data=log.data,
        log_index=log_index,
        removed=False,
        topics=[LogTopic(topic.to_bytes(32, byteorder="big")) for topic in log.topics],
        transaction_index=transaction_index,
        transaction_hash=Hash32(transaction.hash),
    )


def _generate_contract_address(address: EthAddress, nonce: int) -> EthAddress:
    next_account_hash = keccak(_rlp_encode([address, nonce]))
    return EthAddress(next_account_hash[-20:])


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
    base_fee_per_gas = block.header.base_fee_per_gas
    # It is not None after the London fork.
    assert base_fee_per_gas is not None  # noqa: S101
    return (
        min(
            transaction.max_fee_per_gas,
            transaction.max_priority_fee_per_gas + base_fee_per_gas,
        )
        if transaction_type == 2
        else transaction.gas_price
    )
