# CLAUDE.md — cic-mcp-knowledge

## Mi ez a repo?

Ez a `cic-mcp-*` család **knowledge / KB graph rétege**: deklarált source-okból generált,
kereshető tudásgráfot szolgál ki MCP-n keresztül.

A repo a `base-repo` MCP template-jéből örökli a build/release infrastruktúrát, de a domain
tartalma a `knowledge.sources.yaml`, a `source/` alatti checkoutok és a generált `kb_data/`
artifactok köré szerveződik.

## Fő határok

**Igen:**
- knowledge source manifest és profile-alapú `.gitmodules` generálás
- markdown/YAML companion alapú KB build
- BM25/inverted index, FAISS embedding index, graph node/edge artifactok
- KB graph MCP toolok (`search_query`, `get_chunk`, `neighbors`, `focus_pack`, stb.)
- companion YAML és agent decision write toolok, SOURCE_DIR confinementtel

**Nem:**
- session/raw event ingest
- shared cross-session aggregáció
- automatikus canonical promotion
- DB-backed human review/audit lifecycle a canonical státuszhoz

## Trust modell

```yaml
knowledge_role: generated_kb_graph
source_manifest: knowledge.sources.yaml
canonical_runtime_enforced: false
write_scope: SOURCE_DIR-confined companion/task files
```

Fontos: a gateway `canonical_facts[]` mappingje jelenleg abból indul ki, hogy a
`cic-mcp-knowledge` a reviewed/canonical réteg. Ebben a repóban azonban még nincs olyan
runtime constraint vagy auditált promotion flow, mint a `cic-mcp-shared` review lifecycle
esetén. Ezt vagy implementálni kell, vagy a gateway trust mappinget kell szűkíteni.

## Jelenlegi állapot

`experimental` — van működő KB graph szerver és source manifest, de a canonical szerződés és a
dependency lock állapota rendezendő.

- `knowledge.sources.yaml` deklarálja a source-okat és a public/internal profile-okat.
- `tools/generate_gitmodules.py` ebből generálja a `.gitmodules` artifactot.
- `make_source.py` generálja a `kb_data/` és `sqlite_data/` artifactokat.
- `mcp-server/server.py` FastMCP KB szervert ad kereséshez, graph traversalhoz és task/companion
  íráshoz.
- `tests/test_tools/test_mcp_server_write_confinement.py` bizonyítja, hogy az író toolok nem
  írhatnak `SOURCE_DIR` alá zárt fán kívülre.

Korlátok: nincs formális canonical promotion pipeline; a `requirements.txt` jelenleg driftben
van a `requirements.in` runtime dependency listájához képest, ezért lockfile regenerálás kell.

## MCP szerver

A repo egy FastMCP-alapú knowledge base szervert tartalmaz, ami a `source/` könyvtár tartalmából épít kereshető tudásgráfot.

```
source/          ← ide kerülnek a repo docs + a CIC ökoszisztéma repo-k
    ↓
make kb.build    ← make_source.py: TF-IDF + cosine similarity gráf
    ↓
kb_data/pkl/     ← generált pickle fájlok (gitignore-d)
    ↓
make mcp.run     ← mcp-server/server.py (FastMCP, stdio)
```

## Kulcs parancsok

```bash
make mcp.config     # .mcp.json generálás (első lépés, repo clone után!)
make kb.build       # Knowledge base generálás a source/ tartalmából
make mcp.run        # MCP szerver indítás (stdio, Claude Code-hoz)
make mcp.run.sse    # MCP szerver indítás (SSE/HTTP)

make up             # Docker dev környezet (release tooling-hoz)
make validate       # Schema validáció
make release-check VERSION=x.y.z
make release-prepare VERSION=x.y.z
make release-close VERSION=x.y.z
```

## Könyvtár struktúra

```
make_source.py        ← KB generátor
mcp-server/server.py  ← FastMCP szerver (12 tool)
source/               ← forrás docs (gitkeep, a fogadó repo tölti fel)
kb_data/              ← generált KB (pkl/, json/ — gitignore-d)
sqlite_data/          ← generált SQLite (gitignore-d)
schemas.json          ← adat struktúra sémák
sqlite_data/db_schema.json ← SQLite tábla definíciók
.mcp.json             ← MCP szerver konfiguráció Claude Code-hoz
p_venv/               ← Python venv (gitignore-d)

tools/                ← release tooling (compiler.py, infra.py, vault signing)
docs/                 ← architektúra és koncept dokumentáció (EN + HU)
features/             ← feature specifikációk
mk/infra.mk           ← Makefile implementáció
```

## Python környezet

Az MCP szerver és a KB generátor a lokális `p_venv/`-et használja (nem Docker):
```bash
p_venv/bin/python make_source.py
p_venv/bin/python mcp-server/server.py
```

A release tooling (validate, test, fmt) Docker containerben fut.

## MCP szerver tool-ok

| Tool | Leírás |
|------|--------|
| `search_query` | Multi-token keresés TF-IDF invertált indexen |
| `search_token` | Single token lookup |
| `search_code` | Substring keresés chunk tartalomban |
| `search_nodes` | Node keresés név/label/tag alapján |
| `resolve_path` | Chunk keresés fájlút alapján |
| `get_chunk` | Chunk lekérés ID alapján |
| `get_node` | Node lekérés ID alapján |
| `neighbors` | Graph szomszédok lekérése |
| `focus_pack` | Kontextus csomag (rule prioritizálással) |
| `explain_node` | Node mély elemzése |
| `kb_status` | KB állapot és fájl info |
| `reload_kb` | KB újratöltés lemezről |

## AI Reasoning Protocol

### Boot fázis (kötelező session-indításkor)

Mielőtt szakmai kérdésre válaszolsz, futtasd le ezt a szekvenciát:

1. `kb_status` — KB artifact állapot ellenőrzése
2. Keress rá az `axioms` és `symbols` node-okra (`search_nodes`)
3. Keress rá a `limits` és `contract` fogalmakra
4. Határozd meg a runtime státuszt: **production / scaffold / concept**

A boot végén internalizáld:
- Mit tekintesz invariánsnak
- Melyek a kulcsfogalmak
- Mi runtime, mi scaffold, mi csak koncepció

**Amíg ez nem teljesült, ne válaszolj szakmai kérdésre.**

### Graph-first reasoning (ne search→snippet→answer)

Query helyett subgraph-építés:

1. Azonosítsd a fogalmat
2. Keresd meg az induló node-okat (`search_nodes`, `find_nodes`)
3. Járd be az 1–2 hop szomszédokat (`neighbors`)
4. Szűrj kapcsolattípus szerint
5. Építs lokális subgraphot
6. Csak ebből válaszolj

A chunk nem elsődleges tudáselem — csak bizonyíték. Elsődleges: **node, edge, status, provenance**.

### Háromrétegű státusz-kényszer

Minden állítás előtt kötelező meghatározni:

- `implemented` — van kód, van runtime belépési pont
- `scaffold` — van kód, de nincs éles runtime híd
- `concept` — csak dokumentáció vagy graph node, kód nincs

Ha node- vagy file-szinten nem tudod alátámasztani, **nem mondhatod ki tényként**.

### Kötelező ellenőrző lánc

Minden fontos állításhoz belső validáció:

```
fogalom → definíciós doc → companion/meta → graph kapcsolat → kód/scaffold hely → runtime belépési pont
```

Ha a lánc megszakad:
> "a modell itt létezik, de az implementációs lánc itt megszakad: [hely]"

Nem azt mondod, hogy "nincs" — hanem megnevezed, hol törik el.

### Bridge detector

Minden válasz előtt ellenőrizd a hidakat:

- `concept → code` bridge: van-e implementáció?
- `code → runtime` bridge: van-e belépési pont?
- `runtime → audit` bridge: van-e trace/log/proof?

Ha hiányzik: státusz = scaffold vagy concept, nem implemented.

### Immersion mód

Ha a feladat fogalmi megértés (nem implementáció, nem audit):

**Tilos:**
- Javaslatot tenni
- Kritikát mondani
- Hiányt feltételezni

**Csak:**
- Axiómákat felvenni
- Fogalmi szerkezetet és relációkat térképezni
- Rendszerlogikát internalizálni

### Válasz formátum (strukturált állításokhoz)

| Mező | Tartalom |
|------|----------|
| **fogalom** | mi ez |
| **mit jelent a rendszerben** | szerepe, funkciója |
| **hol él** | node ID, fájlút |
| **státusz** | implemented / scaffold / concept |
| **mihez kapcsolódik** | szomszédos node-ok, edge-típusok |
| **bizonyíték** | chunk ID vagy doc referencia |
| **nyitott híd** | hol törik el az implementációs lánc |

---

## Repo konvenciók

- Branch naming: `{component}/releases/v{VERSION}` (release), `mcp/devel` (MCP fejlesztés)
- Tag format: `{component}@v{VERSION}`
- Commit signing: Vault Transit engine (git hook)
- `project.yaml`: minden release metaadatot és kriptográfiai aláírást tartalmaz
- `md.meta.schema.yaml`: dokumentáció metadata sémája (tags, categories, used_in)

## Kapcsolódó rendszerek

- **CIC-Relay**: Go-alapú control plane (Nexus orchestrator, WASM)
- **CIC-Schemas**: Schema compiler és Vault signing
- **CIC-Registry**: 3-rétegű registry (schemas/mods/agents)
- **HashiCorp Vault**: Transit signing, KV v2 cert storage
