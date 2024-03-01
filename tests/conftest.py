import pytest
from alysis import Node, RPCNode
from eth_account import Account


@pytest.fixture
def node():
    return Node(root_balance_wei=10**18)


@pytest.fixture
def rpc_node(node):
    return RPCNode(node)


@pytest.fixture
def root_account(node):
    return Account.from_key(node.root_private_key)


@pytest.fixture
def another_account():
    return Account.create()
