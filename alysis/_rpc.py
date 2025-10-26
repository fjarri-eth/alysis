"""RPC-like API, mimicking the behavior of major Ethereum providers."""

from compages import StructuringError, UnstructuringError
from ethereum_rpc import (
    JSON,
    Address,
    Block,
    BlockHash,
    EstimateGasParams,
    EthCallParams,
    FilterParams,
    FilterParamsEIP234,
    LogEntry,
    RPCError,
    RPCErrorCode,
    TxHash,
    structure,
    unstructure,
)

from ._exceptions import (
    BlockNotFound,
    TransactionFailed,
    TransactionNotFound,
    TransactionReverted,
    ValidationError,
)
from ._node import Node


class RPCNode:
    """
    A wrapper for :py:class:`Node` exposing an RPC-like interface,
    taking and returning JSON-compatible data structures.
    """

    def __init__(self, node: Node):
        self.node = node
        self._methods = dict(
            net_version=self._net_version,
            web3_clientVersion=self._web3_client_version,
            eth_accounts=self._eth_accounts,
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
            web3_sha3=self._web3_sha3,
        )

    def rpc(self, method_name: str, *params: JSON) -> JSON:
        """
        Makes an RPC request to the chain and returns the result on success,
        or raises :py:class:`ethereum_rpc.RPCError` on failure.
        """
        if method_name not in self._methods:
            raise RPCError.with_code(
                RPCErrorCode.METHOD_NOT_FOUND, f"Unknown method: {method_name}"
            )

        try:
            return self._methods[method_name](params)

        except (BlockNotFound, TransactionNotFound) as exc:
            # If we didn't process it earlier, it's a SERVER_ERROR
            raise RPCError.with_code(RPCErrorCode.SERVER_ERROR, str(exc)) from exc

        except (StructuringError, ValidationError) as exc:
            raise RPCError.with_code(RPCErrorCode.INVALID_PARAMETER, str(exc)) from exc

        except UnstructuringError as exc:
            raise RPCError.with_code(RPCErrorCode.SERVER_ERROR, str(exc)) from exc

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

            raise RPCError.with_code(error, message, data) from exc

        except TransactionFailed as exc:
            raise RPCError.with_code(RPCErrorCode.SERVER_ERROR, exc.args[0]) from exc

    def _net_version(self, params: tuple[JSON, ...]) -> JSON:
        _ = structure(tuple[()], params)
        # Note: it's not hex encoded, but just stringified!
        return str(self.node.net_version())

    def _web3_client_version(self, params: tuple[JSON, ...]) -> JSON:
        _ = structure(tuple[()], params)
        return self.node.web3_client_version()

    def _eth_chain_id(self, params: tuple[JSON, ...]) -> JSON:
        _ = structure(tuple[()], params)
        return unstructure(self.node.eth_chain_id())

    def _eth_block_number(self, params: tuple[JSON, ...]) -> JSON:
        _ = structure(tuple[()], params)
        return unstructure(self.node.eth_block_number())

    def _eth_get_balance(self, params: tuple[JSON, ...]) -> JSON:
        address, block = structure(tuple[Address, Block], params)
        return unstructure(self.node.eth_get_balance(address, block))

    def _eth_get_code(self, params: tuple[JSON, ...]) -> JSON:
        address, block = structure(tuple[Address, Block], params)
        return unstructure(self.node.eth_get_code(address, block))

    def _eth_get_storage_at(self, params: tuple[JSON, ...]) -> JSON:
        address, slot, block = structure(tuple[Address, int, Block], params)
        return unstructure(self.node.eth_get_storage_at(address, slot, block))

    def _eth_get_transaction_count(self, params: tuple[JSON, ...]) -> JSON:
        address, block = structure(tuple[Address, Block], params)
        return unstructure(self.node.eth_get_transaction_count(address, block))

    def _eth_get_transaction_by_hash(self, params: tuple[JSON, ...]) -> JSON:
        (transaction_hash,) = structure(tuple[TxHash], params)
        try:
            transaction = self.node.eth_get_transaction_by_hash(transaction_hash)
        except TransactionNotFound:
            return None
        return unstructure(transaction)

    def _eth_get_block_by_number(self, params: tuple[JSON, ...]) -> JSON:
        block, with_transactions = structure(tuple[Block, bool], params)
        try:
            block_info = self.node.eth_get_block_by_number(
                block, with_transactions=with_transactions
            )
        except BlockNotFound:
            return None
        return unstructure(block_info)

    def _eth_get_block_by_hash(self, params: tuple[JSON, ...]) -> JSON:
        block_hash, with_transactions = structure(tuple[BlockHash, bool], params)
        try:
            block_info = self.node.eth_get_block_by_hash(
                block_hash, with_transactions=with_transactions
            )
        except BlockNotFound:
            return None
        return unstructure(block_info)

    def _eth_get_transaction_receipt(self, params: tuple[JSON, ...]) -> JSON:
        (transaction_hash,) = structure(tuple[TxHash], params)
        try:
            receipt = self.node.eth_get_transaction_receipt(transaction_hash)
        except TransactionNotFound:
            return None
        return unstructure(receipt)

    def _eth_send_raw_transaction(self, params: tuple[JSON, ...]) -> JSON:
        (raw_transaction,) = structure(tuple[bytes], params)
        return unstructure(self.node.eth_send_raw_transaction(raw_transaction))

    def _eth_call(self, params: tuple[JSON, ...]) -> JSON:
        transaction, block = structure(tuple[EthCallParams, Block], params)
        return unstructure(self.node.eth_call(transaction, block))

    def _eth_estimate_gas(self, params: tuple[JSON, ...]) -> JSON:
        transaction, block = structure(tuple[EstimateGasParams, Block], params)
        return unstructure(self.node.eth_estimate_gas(transaction, block))

    def _eth_gas_price(self, params: tuple[JSON, ...]) -> JSON:
        _ = structure(tuple[()], params)
        return unstructure(self.node.eth_gas_price())

    def _eth_new_block_filter(self, params: tuple[JSON, ...]) -> JSON:
        _ = structure(tuple[()], params)
        return unstructure(self.node.eth_new_block_filter())

    def _eth_new_pending_transaction_filter(self, params: tuple[JSON, ...]) -> JSON:
        _ = structure(tuple[()], params)
        return unstructure(self.node.eth_new_pending_transaction_filter())

    def _eth_new_filter(self, params: tuple[JSON, ...]) -> JSON:
        (typed_params,) = structure(tuple[FilterParams], params)
        return unstructure(self.node.eth_new_filter(typed_params))

    def _eth_get_filter_changes(self, params: tuple[JSON, ...]) -> JSON:
        (filter_id,) = structure(tuple[int], params)
        return unstructure(
            self.node.eth_get_filter_changes(filter_id),
            list[LogEntry] | list[TxHash] | list[BlockHash],
        )

    def _eth_get_filter_logs(self, params: tuple[JSON, ...]) -> JSON:
        (filter_id,) = structure(tuple[int], params)
        return unstructure(self.node.eth_get_filter_logs(filter_id), list[LogEntry])

    def _eth_get_logs(self, params: tuple[JSON, ...]) -> JSON:
        (typed_params,) = structure(tuple[FilterParams | FilterParamsEIP234], params)
        return unstructure(self.node.eth_get_logs(typed_params), list[LogEntry])

    def _eth_accounts(self, params: tuple[JSON, ...]) -> JSON:
        _ = structure(tuple[()], params)
        return unstructure(self.node.eth_accounts(), list[Address])

    def _web3_sha3(self, params: tuple[JSON, ...]) -> JSON:
        (data,) = structure(tuple[bytes], params)
        return unstructure(self.node.web3_sha3(data))
