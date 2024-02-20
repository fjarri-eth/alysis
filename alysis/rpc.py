from contextlib import contextmanager
from enum import Enum
from typing import Iterator, List, Mapping, Optional, Sequence, Tuple, Union

from .exceptions import BlockNotFound, TransactionFailed, TransactionNotFound, TransactionReverted
from .node import Node
from .schema import (
    Address,
    Block,
    EstimateGas,
    FilterParams,
    Hash32,
    TransactionCall,
    structure,
    unstructure,
)

JSON = Union[bool, int, float, str, None, Sequence["JSON"], Mapping[str, "JSON"]]


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
    def __init__(self, code: RPCErrorCode, message: str, data: Optional[str] = None):
        super().__init__(f"Error {code}: {message}")
        self.code = code
        self.message = message
        self.data = data


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
            data = unstructure(reason_data)

        raise RPCError(error, message, data) from exc

    except TransactionFailed as exc:
        raise RPCError(RPCErrorCode.SERVER_ERROR, exc.args[0]) from exc


class RPCNode:
    def __init__(self, node: Node):
        self.node = node

    def rpc(self, method_name: str, *params: JSON) -> JSON:
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
        _ = structure(Tuple[()], params)
        # Note: it's not hex encoded, but just stringified!
        return str(self.node.net_version())

    def _eth_chain_id(self, params: Tuple[JSON, ...]) -> JSON:
        _ = structure(Tuple[()], params)
        return unstructure(self.node.chain_id())

    def _eth_block_number(self, params: Tuple[JSON, ...]) -> JSON:
        _ = structure(Tuple[()], params)
        return unstructure(self.node.block_number())

    def _eth_get_balance(self, params: Tuple[JSON, ...]) -> JSON:
        address, block = structure(Tuple[Address, Block], params)
        return unstructure(self.node.get_balance(address, block))

    def _eth_get_code(self, params: Tuple[JSON, ...]) -> JSON:
        address, block = structure(Tuple[Address, Block], params)
        return unstructure(self.node.get_code(address, block))

    def _eth_get_storage_at(self, params: Tuple[JSON, ...]) -> JSON:
        address, slot, block = structure(Tuple[Address, int, Block], params)
        return unstructure(
            self.node.get_storage_at(address, slot, block).to_bytes(32, byteorder="big")
        )

    def _eth_get_transaction_count(self, params: Tuple[JSON, ...]) -> JSON:
        address, block = structure(Tuple[Address, Block], params)
        return unstructure(self.node.get_transaction_count(address, block))

    def _eth_get_transaction_by_hash(self, params: Tuple[JSON, ...]) -> JSON:
        (transaction_hash,) = structure(Tuple[Hash32], params)
        try:
            transaction = self.node.get_transaction_by_hash(transaction_hash)
        except TransactionNotFound:
            return None
        return unstructure(transaction)

    def _eth_get_block_by_number(self, params: Tuple[JSON, ...]) -> JSON:
        block, with_transactions = structure(Tuple[Block, bool], params)
        try:
            block = self.node.get_block_by_number(block, with_transactions=with_transactions)
        except BlockNotFound:
            return None
        return unstructure(block)

    def _eth_get_block_by_hash(self, params: Tuple[JSON, ...]) -> JSON:
        block_hash, with_transactions = structure(Tuple[Hash32, bool], params)
        try:
            block = self.node.get_block_by_hash(block_hash, with_transactions=with_transactions)
        except BlockNotFound:
            return None
        return unstructure(block)

    def _eth_get_transaction_receipt(self, params: Tuple[JSON, ...]) -> JSON:
        (transaction_hash,) = structure(Tuple[Hash32], params)
        try:
            receipt = self.node.get_transaction_receipt(transaction_hash)
        except TransactionNotFound:
            return None
        return unstructure(receipt)

    def _eth_send_raw_transaction(self, params: Tuple[JSON, ...]) -> JSON:
        (raw_transaction,) = structure(Tuple[bytes], params)
        return unstructure(self.node.send_raw_transaction(raw_transaction))

    def _eth_call(self, params: Tuple[JSON, ...]) -> JSON:
        transaction, block = structure(Tuple[TransactionCall, Block], params)
        return unstructure(self.node.call(transaction, block))

    def _eth_estimate_gas(self, params: Tuple[JSON, ...]) -> JSON:
        transaction, block = structure(Tuple[EstimateGas, Block], params)
        return unstructure(self.node.estimate_gas(transaction, block))

    def _eth_gas_price(self, params: Tuple[JSON, ...]) -> JSON:
        _ = structure(Tuple[()], params)
        return unstructure(self.node.gas_price())

    def _eth_new_block_filter(self, params: Tuple[JSON, ...]) -> JSON:
        _ = structure(Tuple[()], params)
        return unstructure(self.node.new_block_filter())

    def _eth_new_pending_transaction_filter(self, params: Tuple[JSON, ...]) -> JSON:
        _ = structure(Tuple[()], params)
        return unstructure(self.node.new_pending_transaction_filter())

    def _eth_new_filter(self, params: Tuple[JSON, ...]) -> JSON:
        (params,) = structure(Tuple[FilterParams], params)
        return unstructure(self.node.new_filter(params))

    def _eth_get_filter_changes(self, params: Tuple[JSON, ...]) -> JSON:
        (filter_id,) = structure(Tuple[int], params)
        return unstructure(self.node.get_filter_changes(filter_id))

    def _eth_get_filter_logs(self, params: Tuple[JSON, ...]) -> JSON:
        (filter_id,) = structure(Tuple[int], params)
        return unstructure(self.node.get_filter_logs(filter_id))

    def _eth_get_logs(self, params: Tuple[JSON, ...]) -> JSON:
        (params,) = structure(Tuple[FilterParams], params)
        return unstructure(self.node.get_logs(params))
