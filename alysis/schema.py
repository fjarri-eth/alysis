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


Block = int | BlockLabel


@dataclass
class FilterParams:
    # TODO: support block_hash field
    from_block: Optional[Block] = None
    to_block: Optional[Block] = None
    address: Optional[Union[Address, List[Address]]] = None
    topics: Optional[List[Union[None, Hash32, List[Hash32]]]] = None


@dataclass
class TransactionCall:
    to: Address
    from_: Optional[Address] = None
    gas: Optional[int] = None
    gas_price: int = 0
    value: int = 0
    data: Optional[bytes] = None


@dataclass
class EstimateGas:
    from_: Address
    to: Optional[Address] = None
    gas: Optional[int] = None
    gas_price: int = 0
    nonce: Optional[int] = None
    value: int = 0
    data: Optional[bytes] = None


def structure_address(val: Any) -> Address:
    if not isinstance(val, str) or not val.startswith("0x"):
        raise Exception("The value must be a 0x-prefixed hex-encoded data")
    res = bytes.fromhex(val[2:])
    assert len(res) == 20, "The value must encode 20 bytes"
    return Address(res)


def structure_hash32(val: Any) -> Hash32:
    if not isinstance(val, str) or not val.startswith("0x"):
        raise Exception("The value must be a 0x-prefixed hex-encoded data")
    res = bytes.fromhex(val[2:])
    assert len(res) == 32, "The value must encode 30 bytes"
    return Hash32(res)


def structure_bytes(val: Any) -> bytes:
    if not isinstance(val, str) or not val.startswith("0x"):
        raise Exception("The value must be a 0x-prefixed hex-encoded data")
    return bytes.fromhex(val[2:])


def structure_int(val: Any) -> int:
    if not isinstance(val, str) or not val.startswith("0x"):
        raise Exception("The value must be a 0x-prefixed hex-encoded integer")
    return int(val, 0)


def structure_block(val: Any) -> BlockLabel:
    assert isinstance(val, str)
    try:
        return BlockLabel(val)
    except ValueError as exc:
        raise Exception(f"{repr(val)} is not a known block label") from exc


def structure_bool(val: Any) -> bool:
    assert isinstance(val, bool)
    return val


def unstructure_int_as_hex(unstructure, obj: int):
    return hex(obj)


def unstructure_bytes_as_hex(unstructure, obj: bytes):
    return "0x" + obj.hex()


def unstructure_bool(unstructure, obj):
    return obj


def to_camel_case(name):
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
