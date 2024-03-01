import pytest
from alysis import Node, RPCNode
from eth_keys import KeyAPI


@pytest.fixture
def node():
    return Node(root_balance_wei=10**18)


@pytest.fixture
def rpc_node(node):
    return RPCNode(node)


@pytest.fixture
def root_address(node):
    return KeyAPI().PrivateKey(node.root_private_key).public_key.to_canonical_address()
