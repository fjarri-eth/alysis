from copy import deepcopy

from alysis import RPCNode


def transfer(rpc_node, signer, to, value, nonce):
    tx = {
        "type": 2,
        "chainId": rpc_node.rpc("eth_chainId"),
        "to": to.address,
        "value": hex(value),
        "gas": hex(21000),
        "maxFeePerGas": rpc_node.rpc("eth_gasPrice"),
        "maxPriorityFeePerGas": hex(10**9),
        "nonce": hex(nonce),
    }
    signed_tx = signer.sign_transaction(tx).raw_transaction
    rpc_node.rpc("eth_sendRawTransaction", "0x" + signed_tx.hex())


def get_balance(rpc_node, account):
    return int(rpc_node.rpc("eth_getBalance", account.address, "latest"), 16)


def test_snapshots(node, root_account, another_account):
    rpc_node1 = RPCNode(node)

    transfer(rpc_node1, root_account, another_account, 10**9, 0)

    node2 = deepcopy(node)
    rpc_node2 = RPCNode(node2)

    transfer(rpc_node1, root_account, another_account, 10**9, 1)
    assert get_balance(rpc_node1, another_account) == 2 * 10**9

    assert get_balance(rpc_node2, another_account) == 10**9
