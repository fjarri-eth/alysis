Public API
==========

.. module:: alysis


Typed
-----

.. autoclass:: Node
   :members:


RPC
---

.. autoclass:: RPCNode
   :members:

.. autoclass:: RPCError()
   :members:


Exceptions
----------

.. autoclass:: ValidationError()

.. autoclass:: BlockNotFound()

.. autoclass:: TransactionNotFound()

.. autoclass:: FilterNotFound()

.. autoclass:: TransactionFailed()

.. autoclass:: TransactionReverted()


Schema
------

.. module:: alysis.schema

.. autoclass:: JSON

.. autoclass:: Address

.. autoclass:: Hash32

.. autoclass:: BlockInfo

.. autoclass:: BlockNonce

.. autoenum:: BlockLabel

.. autoclass:: EthCallParams

.. autoclass:: EstimateGasParams

.. autoclass:: FilterParams

.. autoclass:: FilterParamsEIP234

.. autoclass:: LogEntry

.. autoclass:: LogsBloom

.. autoclass:: LogTopic

.. autoclass:: TransactionInfo

.. autoclass:: TransactionReceipt
