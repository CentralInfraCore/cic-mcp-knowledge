# cic-mcp-knowledge-mcp-write-confinement-fix-001 Output

## Scope

Ez a job a `cic-mcp-knowledge` repo `mcp-server/server.py`-jában javítja a
path-traversal / write-confinement hibát az `update_companion()` és
`record_decision()` `@mcp.tool()`-okban: a kliens (MCP-agent) által megadott
`file_path`/`companion_path` paraméter abszolút útként, MINDEN
`SOURCE_DIR`-en-belüliség ellenőrzés nélkül került `p.open("w")`-be. A job
egyúttal javít egy különálló, alacsony kockázatú drift-hibát a
`project.yaml`-ban (`metadata.name: base` → `cic-mcp-knowledge`).

A másik 3 érintett repó (`cic-mcp-session`, `cic-mcp-shared`,
`cic-mcp-gateway`) NEM része ennek a jobnak — azokra párhuzamos, külön jobok
futnak ugyanezzel a logikával.

## Inputs Read

- `mcp-server/server.py` — teljes egészében elolvasva (1661 sor), kiemelten:
  - `SOURCE_DIR` definíció: 1167. sor
  - `update_companion()`: eredetileg 1486–1556. sor
  - `record_decision()`: eredetileg 1560–1637. sor
  - `claim_task`/`complete_task`/`fail_task`/`_find_promptmaps()`: 1261–1482. sor
- `project.yaml` — `metadata.name: base` (3. sor)
- `tests/test_tools/test_mcp_server.py` — meglévő teszt-minta (`import server
  as mcp_server`, `sys.path` illesztés, `patch.object(mcp_server, "load_kb",
  ...)`)
- `CLAUDE.md` (repo-szintű) — Makefile/`p_venv` konvenció
- `jobs/index.yaml` (`cic-mcp-factory` klónban) — megerősítve: nincs
  "knowledge"-et tartalmazó `id:` (lásd "Rejected / Out Of Scope")

## Vulnerability Reproduction (Before Fix)

Grep a két sebezhető függvényre:

```
$ grep -rn "def update_companion\|def record_decision" --include="*.py" mcp-server/ | grep -v test_
mcp-server/server.py:1486:def update_companion(
mcp-server/server.py:1560:def record_decision(
```

Saját reprodukciós script (`/tmp/repro_before_fix/repro.py`), a JAVÍTÁS ELŐTTI
`server.py`-t importálva, `SOURCE_DIR`-t egy izolált tmp könyvtárra állítva, és
egy attól FÜGGETLEN másik tmp könyvtárban lévő `victim.yaml`-t megcélozva
`update_companion(file_path=<abszolút, SOURCE_DIR-en kívüli path>, ...)`-vel:

```
SOURCE_DIR (confined root): /tmp/source_dir_bc9gunf0
victim path (OUTSIDE SOURCE_DIR): /tmp/outside_source_dir_59vjt7fl/victim.yaml
victim exists before call: False
update_companion() result: {'success': True, 'path': '/tmp/outside_source_dir_59vjt7fl/victim.yaml', 'updated_fields': ['description'], 'message': "Updated 1 field(s). Commit to trigger Vault Transit signing."}
victim content AFTER call: 'description: PWNED by path-traversal repro (before fix)\n'
VULNERABLE: True
```

A `victim.yaml` tartalma TÉNYLEGESEN felülíródott (`PWNED by path-traversal
repro (before fix)`) — a hiba a javítás előtt LÉTEZIK és reprodukálható, nem
elméleti.

`record_decision()`-nél a `companion_path` paraméter ugyanazon a mintán megy
(`Path(companion_path)`, abszolút esetén nincs `SOURCE_DIR` ellenőrzés) — a
kódolvasás alapján AZONOS sebezhetőség, a `pytest` futtatott bizonyítékot lásd
lent ("Real Test Proof").

## Confinement Check Implementation

Új helper, `SOURCE_DIR` definíciója UTÁN (`mcp-server/server.py:1170-1194`):

```python
def _resolve_within_source_dir(file_path: str) -> Path:
    """Build a path the same way callers already do (absolute stays absolute,
    relative is joined to SOURCE_DIR), then verify it actually resolves to a
    location inside SOURCE_DIR.

    Raises:
        ValueError: if the resolved path escapes SOURCE_DIR (path traversal,
            symlink escape, or an absolute path outside SOURCE_DIR supplied by
            the MCP client).
    """
    p = Path(file_path)
    if not p.is_absolute():
        p = SOURCE_DIR / file_path

    resolved = p.resolve()
    resolved_source_dir = SOURCE_DIR.resolve()

    if not resolved.is_relative_to(resolved_source_dir):
        raise ValueError(
            f"path escapes SOURCE_DIR: {resolved} is not within {resolved_source_dir}"
        )

    return resolved
```

`Path.resolve()` MINDKÉT oldalra (kapott path ÉS `SOURCE_DIR`) +
`Path.is_relative_to()` — NEM string-prefix összehasonlítás (a Forbidden
Shortcuts szerint ez symlink-kel/`..`-szegmenssel megkerülhető lenne).

Bevezetve MINDKÉT helyre, a path-felépítés helyén, a `p.open()` ELŐTT:

- `update_companion()` — `mcp-server/server.py:1537-1541`:
  ```python
  try:
      p = _resolve_within_source_dir(file_path)
  except ValueError:
      return {"success": False, "path": file_path, "message": "path escapes SOURCE_DIR, refused"}

  if not p.exists():
      return {"success": False, "path": str(p), "message": "file not found"}
  ```

- `record_decision()` — `mcp-server/server.py:1613-1639` (KÉT ágon: az
  explicit `companion_path` paraméteren ÉS a `node_id`-ből levezetett
  candidate-eken egyaránt, mert a `node["source_file"]` is tartalmazhat
  SOURCE_DIR-en kívüli abszolút path-ot):
  ```python
  if companion_path:
      try:
          p = _resolve_within_source_dir(companion_path)
      except ValueError:
          return {"success": False, "path": companion_path, "message": "path escapes SOURCE_DIR, refused"}
  else:
      node = kb["nodes"].get(str(node_id))
      ...
      if p is not None:
          try:
              p = _resolve_within_source_dir(str(p))
          except ValueError:
              return {"success": False, "path": str(p), "message": "path escapes SOURCE_DIR, refused"}
  ```

`claim_task`/`complete_task`/`fail_task` NEM módosítva — megerősítve grep-pel,
hogy nem épít `Path(...)`-ot kliens-megadott paraméterből:

```
$ grep -n "def claim_task\|def complete_task\|def fail_task" -A8 mcp-server/server.py | grep -n "Path("
(nincs egyezés)
```
Mindhárom kizárólag `_find_promptmaps()` (szerver-kontrollált fájl-discovery)
találatain iterál, a kliens csak `task_id`/`repo`/`reason`/`result_note`
string-eket ad — ez a scope MÁR biztonságos, nincs hozzá nyúlás.

## Real Test Proof — Rejection AND No-Regression

Új teszt-fájl: `tests/test_tools/test_mcp_server_write_confinement.py`, a
meglévő `test_mcp_server.py` mintáját követve (`import server as mcp_server`,
`sys.path` illesztés). `SOURCE_DIR`-t `monkeypatch.setattr` izolálja egy
`tmp_path`-alapú könyvtárra (a modul-szintű konstans miatt env-várral nem
módosítható import után).

Futtatott pytest kimenet:

```
$ p_venv/bin/python -m pytest tests/test_tools/test_mcp_server_write_confinement.py -v --no-cov
============================= test session starts ==============================
collected 10 items

tests/test_tools/test_mcp_server_write_confinement.py::TestResolveWithinSourceDir::test_rejects_absolute_path_outside_source_dir PASSED [ 10%]
tests/test_tools/test_mcp_server_write_confinement.py::TestResolveWithinSourceDir::test_rejects_dotdot_traversal PASSED [ 20%]
tests/test_tools/test_mcp_server_write_confinement.py::TestResolveWithinSourceDir::test_accepts_relative_path_inside_source_dir PASSED [ 30%]
tests/test_tools/test_mcp_server_write_confinement.py::TestResolveWithinSourceDir::test_accepts_absolute_path_inside_source_dir PASSED [ 40%]
tests/test_tools/test_mcp_server_write_confinement.py::TestUpdateCompanionRejection::test_rejects_outside_source_dir_absolute_path PASSED [ 50%]
tests/test_tools/test_mcp_server_write_confinement.py::TestUpdateCompanionNoRegression::test_updates_legit_companion_inside_source_dir PASSED [ 60%]
tests/test_tools/test_mcp_server_write_confinement.py::TestUpdateCompanionNoRegression::test_updates_legit_companion_via_relative_path PASSED [ 70%]
tests/test_tools/test_mcp_server_write_confinement.py::TestRecordDecisionRejection::test_rejects_outside_source_dir_companion_path PASSED [ 80%]
tests/test_tools/test_mcp_server_write_confinement.py::TestRecordDecisionNoRegression::test_records_decision_in_legit_companion PASSED [ 90%]
tests/test_tools/test_mcp_server_write_confinement.py::TestRecordDecisionNoRegression::test_records_decision_via_relative_companion_path PASSED [100%]

============================== 10 passed in 3.74s ===============================
```

Lefedett esetek:
1. `update_companion(file_path=<SOURCE_DIR-en kívüli abszolút path>)` →
   `{"success": False, "message": "path escapes SOURCE_DIR, refused"}`, ÉS a
   célfájl bizonyítottan ÉRINTETLEN (`outside_file.read_text() == before`,
   `"PWNED" not in ...`).
2. `update_companion(file_path=<legitim, SOURCE_DIR-en belüli companion>)` →
   `success: True`, a mező TÉNYLEGESEN frissül — abszolút ÉS relatív path
   mindkettő tesztelve, NINCS regresszió.
3. Ugyanaz `record_decision()`-re: `companion_path` SOURCE_DIR-en kívüli →
   elutasítva, érintetlen fájl; SOURCE_DIR-en belüli (abszolút és relatív) →
   sikeres `agent_decisions` append.

A meglévő, érintetlen `test_mcp_server.py` suite is futtatva regresszió-
ellenőrzésként:

```
$ p_venv/bin/python -m pytest tests/test_tools/test_mcp_server.py tests/test_tools/test_mcp_server_write_confinement.py -v --no-cov
...
12 passed, 1 failed (TestSearchQuerySemantic::test_result_has_required_fields)
+ mind a 10 új write-confinement teszt PASSED
```

A 1 FAILED (`test_result_has_required_fields`, `search_query()` `file_paths`
vs `file_path` kulcs-eltérés) ELŐZETESEN létezik, FÜGGETLEN ettől a jobtól —
megerősítve `git stash` + ugyanaz a teszt a javítás ELŐTTI commit-on
(`23d08e8`) is ugyanígy bukik. A "Nem cél" szekció szerint a `search_query`-t
és más KB-funkciókat ez a job NEM módosítja.

## project.yaml Fix

```diff
 metadata:
-  name: base
+  name: cic-mcp-knowledge
```

Csak ez az egy mező változott (`git diff project.yaml` ellenőrizve) —
`description`/`tags`/`version`/`license`/`owner`/`validatedBy` ÉRINTETLEN.

## Findings

- A sebezhetőség MINDKÉT `@mcp.tool()`-ban (`update_companion`,
  `record_decision`) valós és futtatható volt — nem csak elméleti review-
  állítás.
- `record_decision()`-ben a `node_id`-ből levezetett ág is potenciálisan
  kockázatos volt (`node.get("source_file")` lehet abszolút, kontrollálatlan
  path egy korrupt/manipulált KB node-ból) — a fix ezt az ágat is lefedi, nem
  csak az explicit `companion_path`-ot.
- `claim_task`/`complete_task`/`fail_task` MEGERŐSÍTVE biztonságos (grep-pel,
  nincs `Path()` kliens-paraméterből) — nem igényelt módosítást.
- A `project.yaml` `metadata.name: base` egy különálló, alacsony kockázatú
  drift-hiba volt, a fő commit/PR review-jával együtt javítva.
- A README/CLAUDE.md "base-repo" szövege JELENLEG TÉNYSZERŰEN igaz (a
  `cic-mcp-knowledge` repo még soha nem ment át specializációs/bootstrap
  jobon) — ezt a job SZÁNDÉKOSAN NEM írja át, lásd "Rejected / Out Of Scope".

## Claim-Evidence Matrix

| Claim | Status | Evidence | Verification Method | Risk |
|---|---|---|---|---|
| `update_companion()`/`record_decision()` a javítás ELŐTT írhat SOURCE_DIR-en kívülre | proven | repro script kimenet: `VULNERABLE: True`, `victim content AFTER call` tartalmazza a `PWNED` payload-ot | saját reprodukciós script futtatása a javítás előtti kódon | n/a (ez a kiinduló állapot) |
| `_resolve_within_source_dir()` `Path.resolve()`+`is_relative_to()`-alapú, NEM string-prefix | proven | `mcp-server/server.py:1170-1194` forráskód + `TestResolveWithinSourceDir` 4 teszt PASSED | kód olvasás + futtatott pytest | low — jól ismert, biztonságos minta |
| `update_companion()` MOST elutasítja a SOURCE_DIR-en kívüli path-ot, célfájl érintetlen | proven | `TestUpdateCompanionRejection::test_rejects_outside_source_dir_absolute_path` PASSED, asszertálja a fájl-tartalom változatlanságát | futtatott pytest | low |
| `update_companion()` legitim, SOURCE_DIR-en belüli írás TOVÁBBRA IS működik (nincs regresszió) | proven | `TestUpdateCompanionNoRegression` 2 teszt PASSED (abszolút + relatív path) | futtatott pytest | low |
| `record_decision()` MOST elutasítja a SOURCE_DIR-en kívüli `companion_path`-ot, célfájl érintetlen | proven | `TestRecordDecisionRejection::test_rejects_outside_source_dir_companion_path` PASSED | futtatott pytest | low |
| `record_decision()` legitim, SOURCE_DIR-en belüli írás TOVÁBBRA IS működik (nincs regresszió) | proven | `TestRecordDecisionNoRegression` 2 teszt PASSED (abszolút + relatív path) | futtatott pytest | low |
| `claim_task`/`complete_task`/`fail_task` NEM sebezhető, NEM módosítva | proven | grep kimenet (nincs `Path(` egyezés a 3 függvény testében) | statikus grep-ellenőrzés | low |
| `project.yaml` `metadata.name` javítva, más mező érintetlen | proven | `git diff project.yaml` — kizárólag 1 sor változik | `git diff` inspekció | low |
| A README/CLAUDE.md "base-repo" állítás jelenleg igaz, ezért nincs átírva | proven | `grep -n "id:.*knowledge" jobs/index.yaml` (a `cic-mcp-factory` klónban) — nincs korábbi "knowledge" job a fixen kívül | grep a job-index-en | low |
| A meglévő `test_mcp_server.py` suite-on nincs ÚJ regresszió a fix miatt | proven | a fixszel és nélküle futtatva AZONOS 1 pre-existing failure (`test_result_has_required_fields`), `git stash` összehasonlítással megerősítve | futtatott pytest, kétszer (fix előtt/után) | low |

## Decisions Proposed

- A `_resolve_within_source_dir()` helper legyen az egyetlen, közös belépési
  pont MINDEN jövőbeli `@mcp.tool()` write-funkcióhoz, ami `SOURCE_DIR`-en
  belüli fájlt érint — ne íródjon újra ad-hoc ellenőrzés máshol.
- A hibaüzenet formátuma (`"path escapes SOURCE_DIR, refused"`) legyen
  egységes a másik 3 repó (`session`/`shared`/`gateway`) párhuzamos
  javításában is, hogy a kliens-oldali hibakezelés konzisztens legyen.

## Rejected / Out Of Scope

- `claim_task`/`complete_task`/`fail_task` módosítása — MÁR biztonságos,
  csak grep-pel megerősítve, NEM nyúltam hozzá.
- `project.yaml` `description`/`tags`/`version`/`license`/`owner`/
  `validatedBy` módosítása — kizárólag `metadata.name` változott.
- A másik 3 repó (`cic-mcp-session`/`cic-mcp-shared`/`cic-mcp-gateway`)
  javítása — külön, párhuzamos jobok feladata.
- A generikus KB-szerver egyéb funkcióinak (`search_query`/`focus_pack`/stb.)
  módosítása — beleértve az ELŐZETESEN létező, ezzel a jobbal nem összefüggő
  `test_result_has_required_fields` teszthibát is, amit szándékosan
  ÉRINTETLENÜL hagytam.
- `README.md`/`CLAUDE.md` "base-repo" szövegének átírása — EXPLICIT tiltott a
  job specifikációban. Megerősítve grep-pel: `jobs/index.yaml`-ben (a
  `cic-mcp-factory` klónban) NINCS egyetlen "knowledge"-et tartalmazó `id:`
  sem (ezen a fix jobon kívül), tehát a `cic-mcp-knowledge` repo MÉG SOHA nem
  ment át specializációs/bootstrap jobon — a README "base-repo" állítása
  JELENLEG TÉNYSZERŰEN igaz, NEM elavult dokumentáció. Lásd "Next Jobs".

## Risks

- A `record_decision()` `node_id`-ből levezetett ágában a confinement-check
  most a candidate path-ot validálja, MIUTÁN az `.exists()`-szel már
  megerősítettük a candidate-et — ez nem információszivárgás (csak azt
  mondja meg, hogy LÉTEZIK-e a fájl egy adott helyen, amit a hívó már
  ismeri a `node_id`/`source_file` mezőből), de érdemes a párhuzamos
  repókban ugyanígy validálni a sorrendet.
- A teszt-suite `p_venv`-je ehhez a job-workspace-hez lett létrehozva
  (nem a "live" repo `p_venv`-je) — a `cic-mcp-knowledge` repo saját,
  hosszútávú `p_venv`-jét a merge után újra kell építeni/ellenőrizni
  (`make mcp.config` + a `requirements.txt`-ből, nem a job alatt
  ad-hoc telepített csomag-listából).
- A `record_decision()` és `update_companion()` továbbra sem ellenőrzi,
  hogy a célfájl KITERJESZTÉSE `.yaml`/`.yml` — ez nem ennek a jobnak a
  hatóköre (a "Sources" csak a SOURCE_DIR-confinement-et nevezi meg), de
  jövőbeli hardening célpont lehet.

## Definition Of Done Check

- [x] a sebezhetőség REPRODUKÁLVA a javítás ELŐTT, TÉNYLEGES kimenettel —
      lásd "Vulnerability Reproduction (Before Fix)"
- [x] `_resolve_within_source_dir()` implementálva,
      `mcp-server/server.py:1170-1194`
- [x] MINDKÉT érintett függvény (`update_companion`, `record_decision`)
      javítva — `mcp-server/server.py:1537-1541` és `1613-1639`
- [x] valós teszt: path-traversal ELUTASÍTVA ÉS legitim eset TOVÁBBRA IS
      működik, MINDKÉT függvényre, TÉNYLEGES pytest kimenettel (10/10 PASSED)
- [x] `claim_task`/`complete_task`/`fail_task` biztonsága megerősítve
      grep-pel (NEM módosítva)
- [x] `project.yaml` `metadata.name` javítva, más mező érintetlen
- [x] claim-evidence tábla kitöltve, nem üres (10 sor)

## Next Jobs

- `knowledge-repo-baseline-or-bootstrap-001` — a `session-repo-baseline-or-
  bootstrap-001`/`gateway-repo-baseline-or-bootstrap-001` mintájára: a
  `cic-mcp-knowledge` repo MÉG SOHA nem ment át specializációs/bootstrap
  jobon (megerősítve `jobs/index.yaml` grep-pel) — ez a job döntené el és
  hajtaná végre a `README.md`/`CLAUDE.md` "base-repo" szövegének
  specializált, `cic-mcp-knowledge`-specifikus tartalomra cserélését, a
  tényleges repo-identitás (knowledge KB szerver) alapján.
- `cic-mcp-session-mcp-write-confinement-fix-001`,
  `cic-mcp-shared-mcp-write-confinement-fix-001`,
  `cic-mcp-gateway-mcp-write-confinement-fix-001` — ugyanezen
  `update_companion()`/`record_decision()` confinement-hiba javítása a másik
  3, byte-azonos `server.py`-t öröklő repóban, AZONOS logikával
  (`_resolve_within_source_dir()`).
- (opcionális, alacsony prioritás) `search_query()` `file_path` vs
  `file_paths` kulcs-drift javítása — a `test_mcp_server.py` ELŐZETESEN
  létező, ezzel a jobbal nem összefüggő teszthibája jelzi; ennek a jobnak
  EXPLICIT NEM volt hatóköre.
