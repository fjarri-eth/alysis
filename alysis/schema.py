from dataclasses import dataclass
from enum import Enum
from typing import Any, List, Optional, Union

from eth_typing import Address, Hash32

from .structure import Structurer
from .unstructure import Unstructurer


class BlockLabel(Enum):
    LATEST = "latest"
    PENDING = "pending"
    SAFE = "safe"
    FINALIZED = "finalized"
    EARLIEST = "earliest"


Block = Union[int, BlockLabel]


@dataclass
class FilterParams:
    # TODO: support block_hash field
    from_block: Optional[Block] = None
    to_block: Optional[Block] = None
    address: Optional[Union[Address, List[Address]]] = None
    topics: Optional[List[Union[None, Hash32, List[Hash32]]]] = None


@dataclass
class EthCallParams:
    to: Address
    from_: Optional[Address] = None
    gas: Optional[int] = None
    gas_price: int = 0
    value: int = 0
    data: Optional[bytes] = None


@dataclass
class EstimateGasParams:
    from_: Address
    to: Optional[Address] = None
    gas: Optional[int] = None
    gas_price: int = 0
    nonce: Optional[int] = None
    value: int = 0
    data: Optional[bytes] = None


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
    logs: List[LogEntry]
    logs_bloom: bytes  # 256 bytes
    type: int
    status: int


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
    transactions: Union[List[TransactionInfo], List[Hash32]]
    uncles: List[Hash32]

    def is_pending(self) -> bool:
        return self.hash is None


def structure_address(val: Any) -> Address:
    if not isinstance(val, str) or not val.startswith("0x"):
        raise ValueError("The value must be a 0x-prefixed hex-encoded data")
    res = bytes.fromhex(val[2:])
    if len(res) != 20:
        raise ValueError("The value must encode 20 bytes")
    return Address(res)


def structure_hash32(val: Any) -> Hash32:
    if not isinstance(val, str) or not val.startswith("0x"):
        raise ValueError("The value must be a 0x-prefixed hex-encoded data")
    res = bytes.fromhex(val[2:])
    if len(res) != 32:
        raise ValueError("The value must encode 30 bytes")
    return Hash32(res)


def structure_bytes(val: Any) -> bytes:
    if not isinstance(val, str) or not val.startswith("0x"):
        raise ValueError("The value must be a 0x-prefixed hex-encoded data")
    return bytes.fromhex(val[2:])


def structure_int(val: Any) -> int:
    if not isinstance(val, str) or not val.startswith("0x"):
        raise ValueError("The value must be a 0x-prefixed hex-encoded integer")
    return int(val, 0)


def structure_block(val: Any) -> BlockLabel:
    return BlockLabel(val)


def structure_bool(val: Any) -> bool:
    if not isinstance(val, bool):
        raise TypeError("Expected a boolean value")
    return val


def unstructure_int_as_hex(_unstructurer: Unstructurer, obj: int) -> str:
    return hex(obj)


def unstructure_bytes_as_hex(_unstructurer: Unstructurer, obj: bytes) -> str:
    return "0x" + obj.hex()


def unstructure_bool(_unstructurer: Unstructurer, obj: bool) -> bool:  # noqa: FBT001
    return obj


def to_camel_case(name: str) -> str:
    if name.endswith("_"):
        name = name[:-1]
    parts = name.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


STRUCTURER = Structurer.with_defaults(
    {
        Address: structure_address,
        Hash32: structure_hash32,
        int: structure_int,
        bool: structure_bool,
        bytes: structure_bytes,
        BlockLabel: structure_block,
    },
    to_camel_case,
)

UNSTRUCTURER = Unstructurer.with_defaults(
    {
        int: unstructure_int_as_hex,
        bytes: unstructure_bytes_as_hex,
        bool: unstructure_bool,
    },
    to_camel_case,
)


structure = STRUCTURER.structure
unstructure = UNSTRUCTURER.unstructure
