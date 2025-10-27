Changelog
=========


0.6.3 (2025-10-27)
------------------

Added
^^^^^

- ``eth_accounts``, ``web3_clientVersion``, ``net_listening``, ``net_peerCount``, ``eth_coinbase``, ``eth_uninstallFilter``, ``eth_getBlockTransactionCountByHash``, ``eth_getBlockTransactionCountByNumber``, ``eth_getUncleCountByBlockHash``, ``eth_getUncleCountByBlockNumber``, ``eth_getTransactionByBlockHashAndIndex``, ``eth_getTransactionByBlockNumberAndIndexdex``, ``eth_getUncleByBlockHashAndIndex``, ``eth_getUncleByBlockNumberAndIndex``. (PR_29_)
- ``IndexNotFound`` exception. (PR_29_)


.. _PR_29: https://github.com/fjarri/compages/pull/29



0.6.2 (2025-10-19)
------------------

Fixed
^^^^^

- Fixed error when deep copying ``Node`` in newer Python versions (PR_28_).


.. _PR_28: https://github.com/fjarri/compages/pull/28


0.6.1 (2025-10-18)
------------------

Added
^^^^^

- ``EVMVersion.PRAGUE`` constant (PR_27_).


.. _PR_27: https://github.com/fjarri/compages/pull/27



0.6.0 (2025-09-15)
------------------

Changed
^^^^^^^

- Bump ``py-evm`` to 0.12.1-beta.1. (PR_26_)


.. _PR_26: https://github.com/fjarri/compages/pull/26



0.5.0 (2024-05-28)
------------------

Changed
^^^^^^^

- Bump ``py-evm`` to 0.10.1b1. (PR_24_)
- Using ``ethereum-rpc`` types. (PR_25_)


.. _PR_24: https://github.com/fjarri-eth/alsyis/pull/24
.. _PR_25: https://github.com/fjarri-eth/alsyis/pull/25


0.4.0 (2024-03-15)
------------------

Changed
^^^^^^^

- ``RPCError.data`` is now ``None | bytes`` instead of ``None | str``. (PR_23_)
- ``compages`` dependency bumped to 0.3. (PR_23_)


.. _PR_23: https://github.com/fjarri-eth/alsyis/pull/23


0.3.0 (2024-03-09)
------------------

Changed
^^^^^^^

- ``Node.take_snapshot()`` removed, instead ``Node`` objects are now deep-copyable. (PR_18_)
- ``RPCErrorCode.INVALID_REQEST`` removed. (PR_20_)
- Transaction validation errors now raise ``ValidationError`` instead of ``TransactionFailed``. (PR_20_)
- ``Address`` and ``Hash32`` from ``eth-typing`` are now internal and are replaced with the ones defined in the ``schema`` submodule. (PR_22_)
- All parameters for ``Node`` are now keyword-only. (PR_22_)


Added
^^^^^

- Support for ``blockHash`` parameter in ``eth_getLogs``. (PR_21_)
- ``net_version`` parameters for ``Node``. (PR_22_)


Fixed
^^^^^

- Process transaction validation errors and missing method errors correctly on RPC level. (PR_20_)
- Correctly mismatch if there are more topics in the filter than there is in the log entry. (PR_22_)
- Calculate ``BlockInfo.total_difficulty`` correctly. (PR_22_)


.. _PR_18: https://github.com/fjarri-eth/alsyis/pull/18
.. _PR_20: https://github.com/fjarri-eth/alsyis/pull/20
.. _PR_21: https://github.com/fjarri-eth/alsyis/pull/21
.. _PR_22: https://github.com/fjarri-eth/alsyis/pull/22


0.2.0 (2024-03-05)
------------------

Changed
^^^^^^^

- Minimum Python version bumped to 3.10. (PR_4_)


.. _PR_4: https://github.com/fjarri-eth/alsyis/pull/4
