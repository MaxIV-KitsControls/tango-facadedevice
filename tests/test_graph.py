
import mock
import numpy
import pytest

from facadedevice.graph import Node, triplet, Graph
from facadedevice.graph import VALID, INVALID


def test_compare_triplet():
    a = triplet([1, 2], 0.0)
    b = triplet(numpy.array([1, 2]), 0.0)
    assert a == b == a == ([1, 2], 0.0, VALID) == b
    c = triplet([1, 3], 0.0)
    d = triplet([1, 2], 0.1)
    e = triplet([1, 2], 0.0, INVALID)
    f = triplet(numpy.array([1, 3]), 0.0)
    g = None
    assert a != c != b
    assert a != d != b
    assert a != e != b
    assert a != f != b
    assert a != g != b
    assert a != 1 != b
    assert a != 'test' != b
    assert a != 'tes' != b


def test_assert_triplet():
    with pytest.raises(TypeError):
        triplet([1], 'not a float')
    with pytest.raises(TypeError):
        triplet([1], 0.0, 'not a quality')


def test_node_setters():
    mocks = [mock.Mock() for _ in range(3)]
    n = Node('test', description='desc', callbacks=mocks)
    assert n.name == 'test'
    assert n.description == 'desc'
    assert repr(n) == "node <test>"
    assert n.exception() is None
    assert n.result() is None
    for m in mocks:
        assert not m.called
    # Set triplet
    a = triplet([1], 0.0)
    n.set_result(a)
    assert n.exception() is None
    assert n.result() == a
    for m in mocks:
        m.assert_called_with(n)
        m.reset_mock()
    # Set same triplet
    b = triplet(numpy.array([1]), 0.0)
    n.set_result(b)
    assert n.exception() is None
    assert n.result() == b
    for m in mocks:
        assert not m.called
    # Set different triplet
    c = triplet([2], 0.0)
    n.set_result(c)
    assert n.exception() is None
    assert n.result() == c
    for m in mocks:
        m.assert_called_with(n)
        m.reset_mock()
    # Set exception
    d = RuntimeError('Ooops')
    n.set_exception(d)
    assert n.exception() == d
    with pytest.raises(RuntimeError):
        n.result()
    for m in mocks:
        m.assert_called_with(n)
        m.reset_mock()
    # Set same exception
    n.set_exception(d)
    assert n.exception() == d
    with pytest.raises(RuntimeError):
        n.result()
    for m in mocks:
        assert not m.called
    # Set different exception
    e = IOError('Bim!')
    n.set_exception(e)
    assert n.exception() == e
    with pytest.raises(IOError):
        n.result()
    for m in mocks:
        m.assert_called_with(n)
        m.reset_mock()
    # Reset
    n.set_result(None)
    assert n.exception() is None
    assert n.result() is None
    for m in mocks:
        m.assert_called_with(n)
        m.reset_mock()
    # Already reset
    n.set_result(None)
    assert n.result() is None
    assert n.exception() is None
    for m in mocks:
        assert not m.called


def test_fail_node():
    mocks = [mock.Mock(side_effect=RuntimeError)]
    n = Node('test', description='desc', callbacks=mocks)
    assert n.name == 'test'
    assert n.description == 'desc'
    assert n.exception() is None
    assert n.result() is None
    for m in mocks:
        assert not m.called
    # Set wrong exception
    with pytest.raises(TypeError):
        n.set_exception(1)
    assert n.exception() is None
    assert n.result() is None
    # Wrong callback
    a = triplet(1, 0.0)
    with pytest.warns(UserWarning) as record:
        n.set_result(a)
    assert n.exception() is None
    assert n.result() == a
    assert "RuntimeError" in record[0].message.args[0]


def test_simple_graph():
    a = Node('a')
    b = Node('b')
    g = Graph()
    g.add_node(a)
    g.add_node(b)
    assert len(g) == 2
    assert set(g) == {'a', 'b'}
    g.add_rule(b, lambda a: a.result()*2, ['a'])
    # Test 1
    g.build()
    a.set_result(2)
    assert a.result() == 2
    assert b.result() == 4
    g.reset()
    # Test 2
    g.build()
    a.set_result(3)
    assert a.result() == 3
    assert b.result() == 6
    g.reset()
    # Test 3
    ma = mock.Mock()
    mb = mock.Mock()
    a.callbacks.append(ma)
    b.callbacks.append(mb)
    g.build()
    a.set_result(4)
    assert a.result() == 4
    assert b.result() == 8
    ma.assert_called_once_with(a)
    mb.assert_called_once_with(b)
    g.reset()
    # Test 4
    ma = mock.Mock()
    mb = mock.Mock()
    a.callbacks.append(ma)
    b.callbacks.append(mb)
    g.build()
    a.set_exception(RuntimeError('Oops'))
    with pytest.raises(RuntimeError):
        a.result()
    with pytest.raises(RuntimeError):
        b.result()
    ma.assert_called_once_with(a)
    mb.assert_called_once_with(b)
    g.reset()


def test_cyclic_graph():
    # Test 1
    a = Node('a')
    b = Node('b')
    g = Graph()
    g.add_node(a)
    g.add_node(b)
    g.add_rule(b, lambda a: a.result()*2, ['a'])
    g.add_rule(a, lambda b: b.result()/2, ['b'])
    with pytest.raises(ValueError) as context:
        g.build()
    assert "cyclic" in str(context.value)
    assert a.callbacks == []
    assert b.callbacks == []
    # Test 2
    a = Node('a')
    g = Graph()
    g.add_node(a)
    g.add_rule(a, lambda a: a.result()*2, ['a'])
    with pytest.raises(ValueError) as context:
        g.build()
    assert "cyclic" in str(context.value)
    assert a.callbacks == []
    # Test 3
    a = Node('a')
    g = Graph()
    g.build()
    g._dependencies[a].add(a)
    g._subscriptions[a].add(a)
    g._updates[a] = lambda: a.result()
    a.callbacks.append(g.callback)
    with pytest.warns(UserWarning) as record:
        a.set_result(1)
    assert "deadlock" in record[0].message.args[0]


def test_diamond_graph():
    # Create graph
    graph = Graph()
    for x in "abcdefg":
        graph.add_node(Node(x))
    assert len(graph) == len("abcdefg")
    assert set(graph) == set("abcdefg")

    def recover(x):
        try:
            return x.result()
        except ZeroDivisionError:
            return float('inf')

    def add(x, y):
        return x.result() + y.result()

    # Set the rules
    graph.add_rule(graph['b'], lambda a: a.result() * 10, ['a'])
    graph.add_rule(graph['c'], lambda a: a.result() * 100, ['a'])
    graph.add_rule(graph['d'], lambda c: c.result() // 100, ['c'])
    graph.add_rule(graph['e'], add, ['b', 'd'])
    graph.add_rule(graph['f'], lambda a: 1. / a.result(), ['a'])
    graph.add_rule(graph['g'], recover, ['f'])

    # Build graph
    graph.build()

    # Test 1
    graph['a'].set_result(0)
    for x in 'abcde':
        assert graph[x].result() == 0
    with pytest.raises(ZeroDivisionError):
        assert graph['f'].result()
    assert graph['g'].result() == float('inf')

    # Test 2
    graph['a'].set_result(1)
    assert graph['b'].result() == 10
    assert graph['c'].result() == 100
    assert graph['d'].result() == 1
    assert graph['e'].result() == 11
    assert graph['f'].result() == 1
    assert graph['g'].result() == 1

    # Test 3
    mocks = {}
    for x in "abcdefg":
        mocks[x] = mock.Mock()
        graph[x].callbacks.append(mocks[x])
    graph['a'].set_result(2)
    assert graph['b'].result() == 20
    assert graph['c'].result() == 200
    assert graph['d'].result() == 2
    assert graph['e'].result() == 22
    assert graph['f'].result() == 0.5
    assert graph['g'].result() == 0.5
    for x in "abcdefg":
        mocks[x].assert_called_once_with(graph[x])

    # Test 3
    for x in "abcdefg":
        mocks[x].reset_mock()
    graph['a'].set_exception(RuntimeError('Ooops'))
    for x in "bcdefg":
        with pytest.raises(RuntimeError):
            graph[x].result()
    for x in "abcdefg":
        mocks[x].assert_called_once_with(graph[x])


def test_wrong_graph():
    g = Graph()
    g.add_node(Node('a'))
    with pytest.raises(ValueError):
        g.add_node(Node('a'))
    with pytest.raises(ValueError):
        g.add_rule(Node('b'), lambda a: a.result(), ['a'])
    b = Node('b')
    g.add_node(b)
    g.add_rule(b, lambda a: a.result(), ['a'])
    with pytest.raises(ValueError):
        g.add_rule(b, lambda a: a.result(), ['a'])
