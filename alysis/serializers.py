from dataclasses import dataclass
from typing import List, Optional, Sequence, Union

import rlp
from eth.abc import (
    BlockAPI,
    BlockHeaderAPI,
    LogAPI,
    ReceiptAPI,
    SignedTransactionAPI,
    TransactionFieldsAPI,
    VirtualMachineAPI,
)
from eth.rlp.transactions import BaseTransaction
from eth.vm.forks.berlin.transactions import TypedTransaction
from eth_typing import Address, Hash32
from eth_utils import keccak, to_canonical_address, to_int
from eth_utils.toolz import merge

from .exceptions import ValidationError


@dataclass
class BlockInfo:
    number: int
    hash: Optional[Hash32]
    parent_hash: Hash32
    nonce: Optional[int]  # TODO: technically, 8 bytes
    sha3_uncles: Hash32
    logs_bloom: Optional[bytes]  # TODO: 256 bytes or None if it's a pending block
    transactions_root: Hash32
    state_root: Hash32
    receipts_root: Hash32
    miner: Optional[Address]
    difficulty: int
    total_difficulty: int
    extra_data: bytes
    size: int
    gas_limit: int
    gas_used: int
    base_fee_per_gas: int
    timestamp: int
    transactions: Union[List["TransactionInfo"], List[Hash32]]
    uncles: List[Hash32]

    def is_pending(self):
        return self.hash is None

    @classmethod
    def from_pyevm(cls, block: BlockAPI, with_transactions: bool, is_pending: bool):
        if with_transactions:
            transactions = [
                TransactionInfo.from_pyevm(block, transaction, index, is_pending)
                for index, transaction in enumerate(block.transactions)
            ]
        else:
            transactions = [transaction.hash for transaction in block.transactions]

        return cls(
            # While the docs for major provider say that `number` is `null` for pending blocks,
            # it actually isn't in their return values.
            number=block.header.block_number,
            hash=block.header.hash if not is_pending else None,
            parent_hash=block.header.parent_hash,
            nonce=block.header.nonce if not is_pending else None,
            sha3_uncles=block.header.uncles_hash,
            logs_bloom=block.header.bloom if not is_pending else None,
            transactions_root=block.header.transaction_root,
            state_root=block.header.state_root,
            receipts_root=block.header.receipt_root,
            miner=block.header.coinbase if not is_pending else None,
            difficulty=block.header.difficulty if not is_pending else 0,
            # TODO: actual total difficulty
            total_difficulty=block.header.difficulty if not is_pending else None,
            extra_data=pad32(block.header.extra_data),
            size=len(rlp.encode(block)),  # TODO: is this right?
            gas_limit=block.header.gas_limit,
            gas_used=block.header.gas_used,
            # Note: this appears after EIP-1559 upgrade. Ethereum.org does not list this field,
            # but it's returned by providers.
            base_fee_per_gas=block.header.base_fee_per_gas,
            timestamp=block.header.timestamp,
            transactions=transactions,
            uncles=[uncle.hash for uncle in block.uncles],
        )


@dataclass
class TransactionInfo:
    chain_id: int
    block_hash: Optional[Hash32]
    block_number: int
    from_: Address
    gas: int
    gas_price: int
    max_fee_per_gas: int
    max_priority_fee_per_gas: int
    hash: Hash32
    input: bytes
    nonce: int
    to: Address
    transaction_index: int
    type: int
    value: int
    v: int
    r: int
    s: int

    @classmethod
    def from_pyevm(
        cls,
        block: BlockAPI,
        transaction: TransactionFieldsAPI,
        transaction_index: int,
        is_pending: bool,
    ):
        txn_type = _extract_transaction_type(transaction)
        return cls(
            chain_id=transaction.chain_id,
            block_hash=None if is_pending else block.hash,
            hash=transaction.hash,
            nonce=transaction.nonce,
            # While the docs for major provider say that `number` is `null` for pending transactions,
            # it actually isn't in their return values.
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


@dataclass
class TransactionReceipt:
    transaction_hash: Hash32
    transaction_index: int
    block_hash: Hash32
    block_number: int
    from_: Address
    to: Optional[Address]
    cumulative_gas_used: int
    effective_gas_price: int
    gas_used: int
    contract_address: Optional[Address]
    logs: List["LogEntry"]
    logs_bloom: bytes  # 256 bytes
    type: int
    status: int

    @classmethod
    def from_pyevm(
        cls,
        block: BlockAPI,
        transaction: TransactionFieldsAPI,
        receipts: Sequence[ReceiptAPI],
        transaction_index: int,
    ):
        txn_type = _extract_transaction_type(transaction)
        receipt = receipts[transaction_index]

        if transaction.to == b"":
            contract_addr = generate_contract_address(
                transaction.sender,
                transaction.nonce,
            )
        else:
            contract_addr = None

        if transaction_index == 0:
            origin_gas = 0
        else:
            origin_gas = receipts[transaction_index - 1].gas_used

        return cls(
            block_hash=block.hash,
            block_number=block.number,
            contract_address=contract_addr,
            cumulative_gas_used=receipt.gas_used,
            effective_gas_price=_calculate_effective_gas_price(transaction, block, txn_type),
            from_=transaction.sender,
            gas_used=receipt.gas_used - origin_gas,
            logs=[
                LogEntry.from_pyevm(block, transaction, transaction_index, log, log_index)
                for log_index, log in enumerate(receipt.logs)
            ],
            logs_bloom=receipt.bloom.to_bytes(256, byteorder="big"),
            status=1 if receipt.state_root == b"\x01" else 0,
            to=transaction.to or None,
            transaction_hash=transaction.hash,
            transaction_index=transaction_index,
            type=txn_type,
        )


@dataclass
class LogEntry:
    address: Address
    block_hash: Hash32
    block_number: int
    data: bytes
    log_index: int
    removed: bool
    topics: List[Hash32]  # TODO: technically not a hash, but still 32 bytes
    transaction_index: int
    transaction_hash: Hash32

    @classmethod
    def from_pyevm(
        cls,
        block: BlockAPI,
        transaction: TransactionFieldsAPI,
        transaction_index: int,
        log: LogAPI,
        log_index: int,
    ):
        return cls(
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


def pad32(value):
    return value.rjust(32, b"\x00")


def generate_contract_address(address, nonce):
    next_account_hash = keccak(rlp.encode([address, nonce]))
    return to_canonical_address(next_account_hash[-20:])


def _extract_transaction_type(transaction):
    if isinstance(transaction, TypedTransaction):
        try:
            transaction.gas_price
            return 1
        except AttributeError:
            return 2
    # legacy transactions being '0x0' taken from current geth version v1.10.10
    return 0


def _calculate_effective_gas_price(transaction, block, transaction_type):
    return (
        min(
            transaction.max_fee_per_gas,
            transaction.max_priority_fee_per_gas + block.header.base_fee_per_gas,
        )
        if transaction_type == 2
        else transaction.gas_price
    )
