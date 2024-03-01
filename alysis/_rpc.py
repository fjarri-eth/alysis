"""RPC-like API, mimicking the behavior of major Ethereum providers."""

from __future__ import annotations

from contextlib import contextmanager
from enum import Enum
from typing import TYPE_CHECKING, Iterator, Optional, Tuple, cast

from ._exceptions import BlockNotFound, TransactionFailed, TransactionNotFound, TransactionReverted
from ._node import Node
from ._schema import (
    JSON,
    Address,
    Block,
    EstimateGasParams,
    EthCallParams,
    FilterParams,
    Hash32,
    structure,
    unstructure,
)


class RPCErrorCode(Enum):
    """Known RPC error codes returned by providers."""

    SERVER_ERROR = -32000
    """Reserved for implementation-defined server-errors. See the message for details."""

    INVALID_REQUEST = -32600
    """The JSON sent is not a valid Request object."""

    METHOD_NOT_FOUND = -32601
    """The method does not exist / is not available."""

    INVALID_PARAMETER = -32602
    """Invalid method parameter(s)."""

    EXECUTION_ERROR = 3
    """Contract transaction failed during execution. See the data for details."""


class RPCError(Exception):
    """
    An exception raised in case of a known error, that is something that would be returned as
    ``"error": {"code": ..., "message": ..., "data": ...}`` sub-dictionary in an RPC response.
    """

    code: int
    """The error type."""

    message: str
    """The associated message."""

    data: Optional[str]
    """The associated hex-encoded data (if any)."""

    def __init__(self, code: RPCErrorCode, message: str, data: Optional[bytes] = None):
        super().__init__(f"Error {code}: {message}")
        self.code = code.value
        self.message = message
        self.data = cast(str, unstructure(data)) if data is not None else None


@contextmanager
def into_rpc_errors() -> Iterator[None]:
    try:
        yield

    except TransactionReverted as exc:
        reason_data = exc.args[0]

        if reason_data == b"":
            # Empty `revert()`, or `require()` without a message.

            # who knows why it's different in this specific case,
            # but that's how Infura and Quicknode work
            error = RPCErrorCode.SERVER_ERROR

            message = "execution reverted"
            data = None

        else:
            error = RPCErrorCode.EXECUTION_ERROR
            message = "execution reverted"
            data = reason_data

        raise RPCError(error, message, data) from exc

    except TransactionFailed as exc:
        raise RPCError(RPCErrorCode.SERVER_ERROR, exc.args[0]) from exc


class RPCNode:
    """
    A wrapper for :py:class:`Node` exposing an RPC-like interface,
    taking and returning JSON-compatible data structures.
    """

    def __init__(self, node: Node):
        self.node = node

    def rpc(self, method_name: str, *params: JSON) -> JSON:
        """
        Makes an RPC request to the chain and returns the result on success,
        or raises :py:class:`RPCError` on failure.
        """
        methods = dict(
            net_version=self._net_version,
            eth_chainId=self._eth_chain_id,
            eth_getBalance=self._eth_get_balance,
            eth_getTransactionReceipt=self._eth_get_transaction_receipt,
            eth_getTransactionCount=self._eth_get_transaction_count,
            eth_getCode=self._eth_get_code,
            eth_getStorageAt=self._eth_get_storage_at,
            eth_call=self._eth_call,
            eth_sendRawTransaction=self._eth_send_raw_transaction,
            eth_estimateGas=self._eth_estimate_gas,
            eth_gasPrice=self._eth_gas_price,
            eth_blockNumber=self._eth_block_number,
            eth_getTransactionByHash=self._eth_get_transaction_by_hash,
            eth_getBlockByHash=self._eth_get_block_by_hash,
            eth_getBlockByNumber=self._eth_get_block_by_number,
            eth_newBlockFilter=self._eth_new_block_filter,
            eth_newPendingTransactionFilter=self._eth_new_pending_transaction_filter,
            eth_newFilter=self._eth_new_filter,
            eth_getFilterChanges=self._eth_get_filter_changes,
            eth_getLogs=self._eth_get_logs,
            eth_getFilterLogs=self._eth_get_filter_logs,
        )
        with into_rpc_errors():
            return methods[method_name](params)

    def _net_version(self, params: Tuple[JSON, ...]) -> JSON:
        # TODO: currently `mypy` has problems with generic Tuples in Type:
        # https://github.com/python/mypy/issues/16935
        _ = structure(Tuple[()], params)  # type: ignore[arg-type]
        # Note: it's not hex encoded, but just stringified!
        return str(self.node.net_version())

    def _eth_chain_id(self, params: Tuple[JSON, ...]) -> JSON:
        _ = structure(Tuple[()], params)  # type: ignore[arg-type]
        return unstructure(self.node.eth_chain_id())

    def _eth_block_number(self, params: Tuple[JSON, ...]) -> JSON:
        _ = structure(Tuple[()], params)  # type: ignore[arg-type]
        return unstructure(self.node.eth_block_number())

    def _eth_get_balance(self, params: Tuple[JSON, ...]) -> JSON:
        address, block = cast(Tuple[Address, Block], structure(Tuple[Address, Block], params))  # type: ignore[arg-type]
        return unstructure(self.node.eth_get_balance(address, block))

    def _eth_get_code(self, params: Tuple[JSON, ...]) -> JSON:
        address, block = cast(Tuple[Address, Block], structure(Tuple[Address, Block], params))  # type: ignore[arg-type]
        return unstructure(self.node.eth_get_code(address, block))

    def _eth_get_storage_at(self, params: Tuple[JSON, ...]) -> JSON:
        address, slot, block = cast(
            Tuple[Address, int, Block],
            structure(Tuple[Address, int, Block], params),  # type: ignore[arg-type]
        )
        return unstructure(self.node.eth_get_storage_at(address, slot, block))

    def _eth_get_transaction_count(self, params: Tuple[JSON, ...]) -> JSON:
        address, block = cast(Tuple[Address, Block], structure(Tuple[Address, Block], params))  # type: ignore[arg-type]
        return unstructure(self.node.eth_get_transaction_count(address, block))

    def _eth_get_transaction_by_hash(self, params: Tuple[JSON, ...]) -> JSON:
        (transaction_hash,) = cast(Tuple[Hash32], structure(Tuple[Hash32], params))  # type: ignore[arg-type]
        try:
            transaction = self.node.eth_get_transaction_by_hash(transaction_hash)
        except TransactionNotFound:
            return None
        return unstructure(transaction)

    def _eth_get_block_by_number(self, params: Tuple[JSON, ...]) -> JSON:
        block, with_transactions = cast(Tuple[Block, bool], structure(Tuple[Block, bool], params))  # type: ignore[arg-type]
        try:
            block_info = self.node.eth_get_block_by_number(
                block, with_transactions=with_transactions
            )
        except BlockNotFound:
            return None
        return unstructure(block_info)

    def _eth_get_block_by_hash(self, params: Tuple[JSON, ...]) -> JSON:
        block_hash, with_transactions = cast(
            Tuple[Hash32, bool],
            structure(Tuple[Hash32, bool], params),  # type: ignore[arg-type]
        )
        try:
            block_info = self.node.eth_get_block_by_hash(
                block_hash, with_transactions=with_transactions
            )
        except BlockNotFound:
            return None
        return unstructure(block_info)

    def _eth_get_transaction_receipt(self, params: Tuple[JSON, ...]) -> JSON:
        (transaction_hash,) = cast(Tuple[Hash32], structure(Tuple[Hash32], params))  # type: ignore[arg-type]
        try:
            receipt = self.node.eth_get_transaction_receipt(transaction_hash)
        except TransactionNotFound:
            return None
        return unstructure(receipt)

    def _eth_send_raw_transaction(self, params: Tuple[JSON, ...]) -> JSON:
        (raw_transaction,) = cast(Tuple[bytes], structure(Tuple[bytes], params))  # type: ignore[arg-type]
        return unstructure(self.node.eth_send_raw_transaction(raw_transaction))

    def _eth_call(self, params: Tuple[JSON, ...]) -> JSON:
        transaction, block = cast(
            Tuple[EthCallParams, Block],
            structure(Tuple[EthCallParams, Block], params),  # type: ignore[arg-type]
        )
        return unstructure(self.node.eth_call(transaction, block))

    def _eth_estimate_gas(self, params: Tuple[JSON, ...]) -> JSON:
        transaction, block = cast(
            Tuple[EstimateGasParams, Block],
            structure(Tuple[EstimateGasParams, Block], params),  # type: ignore[arg-type]
        )
        return unstructure(self.node.eth_estimate_gas(transaction, block))

    def _eth_gas_price(self, params: Tuple[JSON, ...]) -> JSON:
        _ = structure(Tuple[()], params)  # type: ignore[arg-type]
        return unstructure(self.node.eth_gas_price())

    def _eth_new_block_filter(self, params: Tuple[JSON, ...]) -> JSON:
        _ = structure(Tuple[()], params)  # type: ignore[arg-type]
        return unstructure(self.node.eth_new_block_filter())

    def _eth_new_pending_transaction_filter(self, params: Tuple[JSON, ...]) -> JSON:
        _ = structure(Tuple[()], params)  # type: ignore[arg-type]
        return unstructure(self.node.eth_new_pending_transaction_filter())

    def _eth_new_filter(self, params: Tuple[JSON, ...]) -> JSON:
        (typed_params,) = cast(Tuple[FilterParams], structure(Tuple[FilterParams], params))  # type: ignore[arg-type]
        return unstructure(self.node.eth_new_filter(typed_params))

    def _eth_get_filter_changes(self, params: Tuple[JSON, ...]) -> JSON:
        (filter_id,) = cast(Tuple[int], structure(Tuple[int], params))  # type: ignore[arg-type]
        return unstructure(self.node.eth_get_filter_changes(filter_id))

    def _eth_get_filter_logs(self, params: Tuple[JSON, ...]) -> JSON:
        (filter_id,) = cast(Tuple[int], structure(Tuple[int], params))  # type: ignore[arg-type]
        return unstructure(self.node.eth_get_filter_logs(filter_id))

    def _eth_get_logs(self, params: Tuple[JSON, ...]) -> JSON:
        (typed_params,) = cast(Tuple[FilterParams], structure(Tuple[FilterParams], params))  # type: ignore[arg-type]
        return unstructure(self.node.eth_get_logs(typed_params))
