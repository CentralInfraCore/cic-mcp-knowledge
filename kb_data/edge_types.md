# Edge Types Documentation

This document lists all unique edge types automatically discovered in the knowledge graph.

Understanding these relationships is key to querying and interpreting the graph's structure.

The types are not interchangeable. The graph traversal tools (`focus_pack`, `impact_analysis`, `guided_path`) follow every edge by default; pass `edge_types` to restrict them.

- `calls`: call graph: a Go chunk calls a function that is indexed as another Go node (matched by name).
- `references`: explicit reference: the `related_nodes` of a companion YAML names the target.
- `refers-to`: chunk-order chain: every node points to the next chunk in the global index, across file boundaries. Navigation order, not a semantic relation.
- `related-to`: embedding similarity: cosine similarity of the two chunks is above 0.7. A content-similarity signal, not a dependency.
