def test_eth_get_balance(rpc_node, root_account, another_account):
    tx = {
        "type": 2,
        "chainId": rpc_node.rpc("eth_chainId"),
        "to": another_account.address,
        "value": hex(10**9),
        "gas": hex(21000),
        "maxFeePerGas": rpc_node.rpc("eth_gasPrice"),
        "maxPriorityFeePerGas": hex(10**9),
        "nonce": hex(0),
    }
    signed_tx = root_account.sign_transaction(tx).raw_transaction

    rpc_node.rpc("eth_sendRawTransaction", "0x" + signed_tx.hex())

    result = rpc_node.rpc("eth_getBalance", another_account.address, "latest")
    assert result == hex(10**9)


def test_eth_accounts(rpc_node):
    assert rpc_node.rpc("eth_accounts") == []


def test_web3_client_version(rpc_node):
    assert rpc_node.rpc("web3_clientVersion") == "Alysis testerchain"


def test_web3_sha3(rpc_node):
    assert (
        rpc_node.rpc("web3_sha3", "0x68656c6c6f20776f726c64")
        == "0x47173285a8d7341e5e972fc677286384f802f8ef42a5ec5f03bbfa254cb01fad"
    )


def test_net_listening(rpc_node):
    assert rpc_node.rpc("net_listening")
