# GitHub Repository Setup

After pushing, configure the public repo page (Settings → General):

| Field | Suggested value |
|-------|-----------------|
| **Description** | Personal file knowledge graph with explainable hybrid retrieval (vector + graph expansion) |
| **Website** | `https://github.com/S1M0nLEE/File-Describer#5-minute-demo` |
| **Topics** | `knowledge-graph`, `semantic-search`, `rag`, `fastapi`, `neo4j`, `chromadb`, `python`, `information-retrieval`, `multimodal` |

## Social preview

Upload **1280×640** image: use `docs/assets/social-preview.png` (architecture / UI screenshot).

## Branches

Delete stale remote branch if it contains pre-cleanup history:

```bash
git push origin --delete tois-eval   # optional, after verifying content
```

## Releases

Tag first public demo:

```bash
git tag -a v0.1.0 -m "First public release: core indexing, search, Web UI"
git push origin v0.1.0
```

Then create a GitHub Release from the tag and paste Quick Demo steps from README.
