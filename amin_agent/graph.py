"""Simple StateGraph fallback used by the agent runner.

This is intentionally minimal and deterministic for local testing.
"""

END = "__END__"


class StateGraph:
    def __init__(self, state_type=None):
        self.nodes = {}
        self.edges = {}
        self.conditional = {}
        self.entry = None

    def add_node(self, name, func):
        self.nodes[name] = func

    def add_edge(self, src, dst):
        self.edges.setdefault(src, []).append(dst)

    def add_conditional_edges(self, source, path):
        # path is a function(state)->node_name
        self.conditional[source] = path

    def set_entry_point(self, name):
        self.entry = name

    def compile(self):
        graph = self

        class Runnable:
            def invoke(self, state):
                current = graph.entry
                visited = 0
                while current != END and visited < 50:
                    visited += 1
                    func = graph.nodes.get(current)
                    if func is None:
                        raise RuntimeError(f"No node named {current}")
                    res = func(state)
                    # merge outputs into state
                    if res is None:
                        res = {}
                    state.update(res)
                    # conditional routing
                    if current in graph.conditional:
                        # conditional path function will decide next node name
                        next_node = graph.conditional[current](state)
                        current = next_node
                        continue
                    # otherwise pick first outgoing edge
                    outs = graph.edges.get(current, [])
                    if not outs:
                        current = END
                    else:
                        current = outs[0]
                return state

        return Runnable()
