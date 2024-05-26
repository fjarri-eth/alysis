Changelog
=========


0.5.0 (unreleased)
------------------

Changed
^^^^^^^

- Bump ``py-evm`` to 0.10.1b1. (PR_24_)


.. _PR_24: https://github.com/fjarri/alsyis/pull/24


0.4.0 (2024-03-15)
------------------

Changed
^^^^^^^

- ``RPCError.data`` is now ``None | bytes`` instead of ``None | str``. (PR_23_)
- ``compages`` dependency bumped to 0.3. (PR_23_)


.. _PR_23: https://github.com/fjarri/alsyis/pull/23


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


.. _PR_18: https://github.com/fjarri/alsyis/pull/18
.. _PR_20: https://github.com/fjarri/alsyis/pull/20
.. _PR_21: https://github.com/fjarri/alsyis/pull/21
.. _PR_22: https://github.com/fjarri/alsyis/pull/22


0.2.0 (2024-03-05)
------------------

Changed
^^^^^^^

- Minimum Python version bumped to 3.10. (PR_4_)


.. _PR_4: https://github.com/fjarri/alsyis/pull/4
