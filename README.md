# cic-mcp-knowledge

Knowledge/KB graph réteg a CIC agent-kontextus (`cic-mcp-*` család) számára.

Ez a repo jelenleg kereshető, generált knowledge graphot szolgál ki MCP-n keresztül. A források
deklarált listája a `knowledge.sources.yaml`, a generált KB artifactok pedig `kb_data/` és
`sqlite_data/` alatt jönnek létre.

## Mi ez és mi nem

**Igen:**
- deklarált knowledge source manifest (`knowledge.sources.yaml`)
- `.gitmodules` generálás profile alapján
- `source/` tartalom feldolgozása markdown/YAML companion fájlokból
- BM25/inverted index, FAISS embedding index és graph node/edge artifactok generálása
- FastMCP KB toolok: keresés, chunk/node lookup, graph traversal, focus pack
- companion YAML és agent döntésjegyzet író toolok, SOURCE_DIR confinementtel

**Nem:**
- automatikus canonical promotion pipeline
- DB-backed review/audit lifecycle a canonical státuszhoz
- shared-memory vagy session ingest réteg
- production-grade source freshness/sync rendszer

## Státusz

`experimental` — működő KB graph server és source manifest van, de a repo dokumentációja és
canonical szerződése még nincs azon a szinten, mint a `session`/`shared` rétegeké.

Fontos határ: a `gateway` jelenleg a `cic-mcp-knowledge` találatait `canonical_facts[]` alá tudja
tenni, de ebben a repóban még nincs formális, DB-vel vagy audit traillel kikényszerített
canonical review/promotion modell. Amíg ez nincs meg, a "knowledge canonical" állítást csak a
forrásprofil/repo-governance szintjén lehet értelmezni, nem runtime constraintként.

## Kulcs fájlok

- `knowledge.sources.yaml` — deklarált source lista és public/internal profile-ok
- `tools/generate_gitmodules.py` — `.gitmodules` generálás a source manifestből
- `make_source.py` — KB artifact generálás `source/` tartalomból
- `mcp-server/server.py` — FastMCP KB graph server
- `tests/test_tools/test_mcp_server_write_confinement.py` — write tool path-confinement regressziók

## Ismert teendők

- README/CLAUDE státusz további bontása capability-szinten
- `requirements.txt` regenerálása `requirements.in` alapján
- canonical review/promotion szerződés definiálása vagy a gateway trust mapping pontosítása
