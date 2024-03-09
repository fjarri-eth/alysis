Public API
==========

.. automodule:: alysis


Typed
-----

.. autoclass:: Node
   :members:


RPC
---

.. autoclass:: RPCNode
   :members:

.. autoclass:: JSON

.. autoclass:: RPCError()
   :members:


Schema
------

.. class:: eth_typing.evm.Address

   See https://eth-typing.readthedocs.io/en/latest/eth_typing.html#address

.. class:: eth_typing.evm.Hash32

   See https://eth-typing.readthedocs.io/en/latest/eth_typing.html#hash32


.. autoclass:: BlockInfo

.. autoenum:: BlockLabel

.. autoclass:: EthCallParams

.. autoclass:: EstimateGasParams

.. autoclass:: FilterParams

.. autoclass:: LogEntry

.. autoclass:: TransactionInfo

.. autoclass:: TransactionReceipt


Exceptions
----------

.. autoclass:: ValidationError()

.. autoclass:: BlockNotFound()

.. autoclass:: TransactionNotFound()

.. autoclass:: FilterNotFound()

.. autoclass:: TransactionFailed()

.. autoclass:: TransactionReverted()
