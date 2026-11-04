"""The knowledge graph in a graph database (Neo4j).

The graph model is the ledger's `ledger_nodes` / `ledger_edges` views (carbonroom/ledger/graph.py);
store.py copies exactly that graph into Neo4j, queries.py asks it questions in Cypher.
"""
