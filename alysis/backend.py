from __future__ import annotations

import os
import time
from typing import TYPE_CHECKING, Any, Optional, Union, cast

import rlp
from eth.chains.base import MiningChain
from eth.constants import (
    GENESIS_PARENT_HASH,
    POST_MERGE_DIFFICULTY,
    POST_MERGE_MIX_HASH,
    POST_MERGE_NONCE,
)
from eth.db import get_db_backend
from eth.exceptions import HeaderNotFound, Revert, VMError
from eth.typing import AccountDetails
from eth.vm.forks import ShanghaiVM
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
from .schema import Block, BlockLabel, EstimateGas, TransactionCall
from .serializers import BlockInfo, TransactionInfo, TransactionReceipt

if TYPE_CHECKING:
    from eth.abc import (
        BlockAPI,
        BlockHeaderAPI,
        SignedTransactionAPI,
        TransactionFieldsAPI,
        VirtualMachineAPI,
    )
    from eth.typing import AccountDetails


ZERO_ADDRESS = Address(20 * b"\x00")


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

        blank_root_hash = keccak(rlp.encode(b""))

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

        genesis_state = {root_private_key.public_key.to_canonical_address(): account_state}

        self.chain_id = chain_id
        self.root_private_key = root_private_key
        self.chain = cast(
            MiningChain,
            MainnetTesterPosChain.from_genesis(get_db_backend(), genesis_params, genesis_state),
        )

    def revert_to_block(self, block_hash: bytes) -> None:
        block = self.chain.get_block_by_hash(Hash32(block_hash))
        chaindb = self.chain.chaindb

        chaindb._set_as_canonical_chain_head(chaindb.db, block.header, GENESIS_PARENT_HASH)  # noqa: SLF001, type: ignore
        if block.number > 0:
            self.chain.import_block(block)
        else:
            self.chain = cast(MiningChain, self.chain.from_genesis_header(chaindb.db, block.header))

    def advance_time(self, to_timestamp: int) -> None:
        # timestamp adjusted by 1 b/c a second is added in mine_blocks
        self.chain.header = self.chain.header.copy(timestamp=(to_timestamp - 1))
        self.mine_block()

    def mine_block(self) -> BlockAPI:
        # ParisVM and forward, generate a random `mix_hash` to simulate the `prevrandao` value.
        return self.chain.mine_block(coinbase=ZERO_ADDRESS, mix_hash=os.urandom(32))

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

    def get_block_by_number(self, block: Block, *, with_transactions: bool) -> BlockInfo:
        block = self._get_block_by_number(block)
        is_pending = block.number == self.chain.get_block().number
        return BlockInfo.from_pyevm(block, with_transactions, is_pending)

    def _get_block_by_hash(self, block_hash: bytes) -> BlockAPI:
        try:
            block = self.chain.get_block_by_hash(Hash32(block_hash))
        except HeaderNotFound as exc:
            raise BlockNotFound(f"No block found for block hash: {block_hash.hex()}") from exc

        if block.number >= self.chain.get_block().number:
            raise BlockNotFound(f"No block found for block hash: {block_hash.hex()}")

        return block

    def get_block_by_hash(self, block_hash: bytes, *, with_transactions: bool) -> BlockInfo:
        block = self._get_block_by_hash(block_hash)
        is_pending = block.number == self.chain.get_block().number
        return BlockInfo.from_pyevm(block, with_transactions, is_pending)

    def _get_transaction_by_hash(
        self, transaction_hash: bytes
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

    def get_transaction_by_hash(self, transaction_hash: bytes) -> TransactionInfo:
        block, transaction, transaction_index = self._get_transaction_by_hash(
            transaction_hash,
        )
        is_pending = block.number == self.chain.get_block().number
        return TransactionInfo.from_pyevm(block, transaction, transaction_index, is_pending)

    def _get_vm_for_block_number(self, block: Block) -> VirtualMachineAPI:
        block = self._get_block_by_number(block)
        return self.chain.get_vm(at_header=block.header)

    def get_transaction_receipt(self, transaction_hash: bytes) -> Optional[TransactionReceipt]:
        block, transaction, transaction_index = self._get_transaction_by_hash(
            transaction_hash,
        )
        is_pending = block.number == self.chain.get_block().number
        if is_pending:
            return None

        block_receipts = block.get_receipts(self.chain.chaindb)

        return TransactionReceipt.from_pyevm(
            block,
            transaction,
            block_receipts,
            transaction_index,
        )

    def get_transaction_count(self, address: bytes, block: Block) -> int:
        vm = self._get_vm_for_block_number(block)
        return vm.state.get_nonce(Address(address))

    def get_balance(self, address: bytes, block: Block) -> int:
        vm = self._get_vm_for_block_number(block)
        return vm.state.get_balance(Address(address))

    def get_code(self, address: bytes, block: Block) -> bytes:
        vm = self._get_vm_for_block_number(block)
        return vm.state.get_code(Address(address))

    def get_storage(self, address: bytes, slot: int, block: Block) -> int:
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

    def estimate_gas(self, transaction: EstimateGas, block: Block) -> int:
        from_ = transaction.from_
        header = self._get_block_by_number(block).header
        nonce = (
            self.get_transaction_count(from_, block)
            if transaction.nonce is None
            else transaction.nonce
        )
        to = b"" if transaction.to is None else transaction.to

        evm_transaction = self.chain.create_unsigned_transaction(
            gas_price=transaction.gas_price,
            gas=transaction.gas if transaction.gas is not None else header.gas_limit,
            nonce=nonce,
            value=transaction.value,
            data=transaction.data if transaction.data is not None else b"",
            to=to,
        )

        spoofed_transaction = SpoofTransaction(evm_transaction, from_=from_)

        try:
            return self.chain.estimate_gas(spoofed_transaction, header)

        except ValidationError as exc:
            raise TransactionFailed(exc.args[0]) from exc

        except Revert as exc:
            raise TransactionReverted(exc.args[0]) from exc

        except VMError as exc:
            raise TransactionFailed(exc.args[0]) from exc

    def call(self, transaction: TransactionCall, block: Block) -> bytes:
        from_ = transaction.from_ or ZERO_ADDRESS
        header = self._get_block_by_number(block).header
        nonce = self.get_transaction_count(from_, block)
        evm_transaction = self.chain.create_unsigned_transaction(
            gas_price=transaction.gas_price,
            gas=transaction.gas if transaction.gas is not None else header.gas_limit,
            nonce=nonce,
            value=transaction.value,
            data=transaction.data if transaction.data is not None else b"",
            to=transaction.to,
        )
        spoofed_transaction = SpoofTransaction(evm_transaction, from_=from_)

        try:
            return self.chain.get_transaction_result(spoofed_transaction, header)

        except ValidationError as exc:
            raise TransactionFailed(exc.args[0]) from exc

        except Revert as exc:
            raise TransactionReverted(exc.args[0]) from exc

        except VMError as exc:
            raise TransactionFailed(exc.args[0]) from exc
