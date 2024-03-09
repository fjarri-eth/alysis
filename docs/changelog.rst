Changelog
=========

0.3.0 (unreleased)
------------------

Changed
^^^^^^^

- ``Node.take_snapshot()`` removed, instead ``Node`` objects are now deep-copyable. (PR_18_)
- ``RPCErrorCode.INVALID_REQEST`` removed. (PR_20_)
- Transaction validation errors now raise ``ValidationError`` instead of ``TransactionFailed``. (PR_20_)


Added
^^^^^

- Support for ``blockHash`` parameter in ``eth_getLogs``. (PR_21_)


Fixed
^^^^^

- Process transaction validation errors and missing method errors correctly on RPC level. (PR_20_)


.. _PR_18: https://github.com/fjarri/compages/pull/18
.. _PR_20: https://github.com/fjarri/compages/pull/20
.. _PR_21: https://github.com/fjarri/compages/pull/21


0.2.0 (2024-03-05)
------------------

Changed
^^^^^^^

- Minimum Python version bumped to 3.10. (PR_4_)


.. _PR_4: https://github.com/fjarri/compages/pull/4
