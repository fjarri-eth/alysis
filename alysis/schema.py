"""Ethereum RPC schema."""

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import Enum
from types import MappingProxyType, NoneType, UnionType
from typing import Any, NewType, TypeVar, Union, cast

from compages import (
    StructureDictIntoDataclass,
    Structurer,
    StructuringError,
    UnstructureDataclassToDict,
    Unstructurer,
    simple_structure,
    simple_typechecked_unstructure,
    structure_into_bool,
    structure_into_list,
    structure_into_none,
    structure_into_tuple,
    structure_into_union,
    unstructure_as_bool,
    unstructure_as_list,
    unstructure_as_none,
    unstructure_as_union,
)

Address = NewType("Address", bytes)
"""Ethereum address (20 bytes)."""

Hash32 = NewType("Hash32", bytes)
"""A keccak hash (32 bytes)."""

LogTopic = NewType("LogTopic", bytes)
"""Encoded log topic (32 bytes)."""

BlockNonce = NewType("BlockNonce", bytes)
"""Block nonce (8 bytes)."""

LogsBloom = NewType("LogsBloom", bytes)
"""Bloom filter for logs (256 bytes)."""


class BlockLabel(Enum):
    """Block label."""

    LATEST = "latest"
    PENDING = "pending"
    SAFE = "safe"
    FINALIZED = "finalized"
    EARLIEST = "earliest"


Block = int | BlockLabel


@dataclass
class FilterParams:
    """Filter parameters for ``eth_getLogs`` or ``eth_newFilter``."""

    from_block: None | Block = None
    to_block: None | Block = None
    address: None | Address | list[Address] = None
    topics: None | list[None | LogTopic | list[LogTopic]] = None


@dataclass
class FilterParamsEIP234:
    """Alternative filter parameters for ``eth_getLogs`` (introduced in EIP-234)."""

    block_hash: Hash32
    address: None | Address | list[Address] = None
    topics: None | list[None | LogTopic | list[LogTopic]] = None


@dataclass
class EthCallParams:
    """Transaction fields for ``eth_call``."""

    to: Address
    from_: None | Address = None
    gas: None | int = None
    gas_price: int = 0
    value: int = 0
    data: None | bytes = None


@dataclass
class EstimateGasParams:
    """Transaction fields for ``eth_estimateGas``."""

    from_: Address
    to: None | Address = None
    gas: None | int = None
    gas_price: int = 0
    nonce: None | int = None
    value: int = 0
    data: None | bytes = None


@dataclass
class TransactionInfo:
    """Transaction info."""

    chain_id: int
    block_hash: None | Hash32
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
    transaction_index: None | int
    type: int
    value: int
    v: int
    r: int
    s: int


@dataclass
class LogEntry:
    """Log entry."""

    address: Address
    block_hash: Hash32
    block_number: int
    data: bytes
    log_index: int
    removed: bool
    topics: list[LogTopic]
    transaction_index: int
    transaction_hash: Hash32


@dataclass
class TransactionReceipt:
    """Transaction receipt."""

    transaction_hash: Hash32
    transaction_index: int
    block_hash: Hash32
    block_number: int
    from_: Address
    to: None | Address
    cumulative_gas_used: int
    effective_gas_price: int
    gas_used: int
    contract_address: None | Address
    logs: list[LogEntry]
    logs_bloom: LogsBloom
    type: int
    status: int


@dataclass
class BlockInfo:
    """Block info."""

    number: int
    hash: None | Hash32
    parent_hash: Hash32
    nonce: None | BlockNonce
    sha3_uncles: Hash32
    logs_bloom: None | LogsBloom
    transactions_root: Hash32
    state_root: Hash32
    receipts_root: Hash32
    miner: None | Address
    difficulty: int
    total_difficulty: None | int
    extra_data: bytes
    size: int
    gas_limit: int
    gas_used: int
    base_fee_per_gas: int
    timestamp: int
    transactions: list[TransactionInfo] | list[Hash32]
    uncles: list[Hash32]


@simple_structure
def _structure_into_address(val: Any) -> Address:
    res = _structure_into_bytes_common(val)
    if len(res) != 20:
        raise StructuringError("The value must encode 20 bytes")
    return Address(res)


@simple_structure
def _structure_into_hash32(val: Any) -> Hash32:
    res = _structure_into_bytes_common(val)
    if len(res) != 32:
        raise StructuringError("The value must encode 32 bytes")
    return Hash32(res)


@simple_structure
def _structure_into_bytes(val: Any) -> bytes:
    return _structure_into_bytes_common(val)


def _structure_into_bytes_common(val: Any) -> bytes:
    if not isinstance(val, str) or not val.startswith("0x"):
        raise StructuringError("The value must be a 0x-prefixed hex-encoded data")
    try:
        return bytes.fromhex(val[2:])
    except ValueError as exc:
        raise StructuringError(str(exc)) from exc


@simple_structure
def _structure_into_int(val: Any) -> int:
    if not isinstance(val, str) or not val.startswith("0x"):
        raise StructuringError("The value must be a 0x-prefixed hex-encoded integer")
    return int(val, 0)


@simple_structure
def _structure_into_block(val: Any) -> BlockLabel:
    try:
        return BlockLabel(val)
    except ValueError as exc:
        raise StructuringError(str(exc)) from exc


@simple_typechecked_unstructure
def _unstructure_int_to_hex(obj: int) -> str:
    return hex(obj)


@simple_typechecked_unstructure
def _unstructure_bytes_to_hex(obj: bytes) -> str:
    return "0x" + obj.hex()


def _to_camel_case(name: str, _metadata: MappingProxyType[Any, Any]) -> str:
    if name.endswith("_"):
        name = name[:-1]
    parts = name.split("_")
    return parts[0] + "".join(part.capitalize() for part in parts[1:])


STRUCTURER = Structurer(
    {
        Address: _structure_into_address,
        Hash32: _structure_into_hash32,
        int: _structure_into_int,
        bool: structure_into_bool,
        bytes: _structure_into_bytes,
        list: structure_into_list,
        tuple: structure_into_tuple,
        UnionType: structure_into_union,
        Union: structure_into_union,
        NoneType: structure_into_none,
        BlockLabel: _structure_into_block,
    },
    [StructureDictIntoDataclass(_to_camel_case)],
)

UNSTRUCTURER = Unstructurer(
    {
        int: _unstructure_int_to_hex,
        bytes: _unstructure_bytes_to_hex,
        bool: unstructure_as_bool,
        NoneType: unstructure_as_none,
        list: unstructure_as_list,
        UnionType: unstructure_as_union,
        Union: unstructure_as_union,
    },
    [UnstructureDataclassToDict(_to_camel_case)],
)


JSON = None | bool | int | float | str | Sequence["JSON"] | Mapping[str, "JSON"]
"""Values serializable to JSON."""


_T = TypeVar("_T")


def structure(structure_into: type[_T], obj: JSON) -> _T:
    """Structures incoming JSON data."""
    return STRUCTURER.structure_into(structure_into, obj)


def unstructure(obj: Any, unstructure_as: Any = None) -> JSON:
    """Unstructures node results into JSON-serializable values."""
    # The result is `JSON` by virtue of the hooks we defined
    return cast(JSON, UNSTRUCTURER.unstructure_as(unstructure_as or type(obj), obj))
