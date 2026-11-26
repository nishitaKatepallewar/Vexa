"""Walking shader node trees, including the node groups inside them."""

from typing import Iterator


def all_nodes(tree, _seen=None) -> Iterator:
    """Every node in a node tree and in the node groups it uses, at any depth.

    Each group is visited once, so a group used twice (or a group that contains
    itself) is never walked again.
    """
    if tree is None:
        return
    seen = set() if _seen is None else _seen
    if tree.as_pointer() in seen:
        return
    seen.add(tree.as_pointer())
    for node in tree.nodes:
        yield node
        if node.type == "GROUP" and getattr(node, "node_tree", None) is not None:
            yield from all_nodes(node.node_tree, seen)


def material_nodes(mat) -> Iterator:
    """Every node a material uses, including inside node groups."""
    return all_nodes(getattr(mat, "node_tree", None))
