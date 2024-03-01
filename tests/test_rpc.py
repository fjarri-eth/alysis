from eth_utils import to_checksum_address


def test_eth_get_balance(rpc_node, root_address):
    result = rpc_node.rpc("eth_getBalance", to_checksum_address(root_address), "latest")
    assert result == hex(10**18)
