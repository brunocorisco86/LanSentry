# Graph Report - 14_LanSentry  (2026-09-19)

## Corpus Check
- cluster-only mode — file stats not available

## Summary
- 47 nodes · 79 edges · 12 communities (7 shown, 5 thin omitted)
- Extraction: 99% EXTRACTED · 1% INFERRED · 0% AMBIGUOUS · INFERRED: 1 edges (avg confidence: 0.85)
- Token cost: 0 input · 0 output

## Graph Freshness
- Built from commit: `fedccae5`
- Run `git rev-parse HEAD` and compare to check if the graph is stale.
- Run `graphify update .` after code changes (no API cost).

## Community Hubs (Navigation)
- custom.js
- sidecar.py
- LanSentryProxyHandler
- auto_classify_devices
- enrich_devices
- get_pg_connection
- reload_pihole_lists
- backup_lansentry.sh
- lookup_mac_vendor_api
- suggest_device_name
- sync_names_to_pihole_ftl
- sync_blocks

## God Nodes (most connected - your core abstractions)
1. `main()` - 8 edges
2. `enrich_devices()` - 7 edges
3. `get_pg_connection()` - 7 edges
4. `handle_block_toggle()` - 7 edges
5. `sync_blocks()` - 6 edges
6. `auto_classify_devices()` - 6 edges
7. `LanSentryProxyHandler` - 5 edges
8. `enhanceTable()` - 5 edges
9. `reload_pihole_lists()` - 5 edges
10. `set_pihole_device_group()` - 5 edges

## Surprising Connections (you probably didn't know these)
- `main()` --calls--> `auto_classify_devices()`  [EXTRACTED]
  sidecar/sidecar.py → sidecar/sidecar.py  _Bridges community 1 → community 3_
- `main()` --calls--> `enrich_devices()`  [EXTRACTED]
  sidecar/sidecar.py → sidecar/sidecar.py  _Bridges community 1 → community 4_
- `main()` --calls--> `sync_blocks()`  [EXTRACTED]
  sidecar/sidecar.py → sidecar/sidecar.py  _Bridges community 1 → community 11_
- `main()` --calls--> `sync_names_to_pihole_ftl()`  [EXTRACTED]
  sidecar/sidecar.py → sidecar/sidecar.py  _Bridges community 1 → community 10_
- `sync_names_to_pihole_ftl()` --calls--> `get_pg_connection()`  [EXTRACTED]
  sidecar/sidecar.py → sidecar/sidecar.py  _Bridges community 10 → community 5_

## Import Cycles
- None detected.

## Communities (12 total, 5 thin omitted)

### Community 0 - "custom.js"
Cohesion: 0.54
Nodes (7): enhanceHostPage(), enhanceTable(), getGroupBadge(), getHostIdFromRow(), loadData(), runEnhancements(), toggleBlock()

### Community 1 - "sidecar.py"
Cohesion: 0.43
Nodes (6): get_pihole_client_groups(), init_pihole_group(), main(), Garante que o grupo de bloqueio e a regra wildcard existam no gravity.db do Pi-…, Retorna dicionário mapeando identificador (MAC ou IP em maiúsculas) para seus…, run_proxy()

### Community 2 - "LanSentryProxyHandler"
Cohesion: 0.33
Nodes (4): BaseHTTPRequestHandler, get_pihole_groups(), LanSentryProxyHandler, Retorna todos os grupos configurados no Pi-hole.

### Community 3 - "auto_classify_devices"
Cohesion: 0.50
Nodes (4): auto_classify_devices(), Classifica automaticamente dispositivos novos no grupo correto do Pi-hole com…, Envia notificação via ntfy.sh com link direto por ID., send_ntfy_message()

### Community 4 - "enrich_devices"
Cohesion: 0.50
Nodes (4): enrich_devices(), lookup_reverse_dns(), Consulta PTR no servidor DNS (Unbound/Pi-hole)., Percorre aparelhos no PostgreSQL e preenche HW e Name faltantes.

### Community 5 - "get_pg_connection"
Cohesion: 0.67
Nodes (3): get_pg_connection(), handle_block_toggle(), Atualiza o nome no banco com ou sem a tag [BLOCK], roda sync_blocks…

### Community 6 - "reload_pihole_lists"
Cohesion: 0.50
Nodes (4): Define ou altera o grupo de um dispositivo no Pi-hole por MAC ou IP., Envia sinal RTMIN para o pihole-FTL recarregar as listas e grupos…, reload_pihole_lists(), set_pihole_device_group()

## Knowledge Gaps
- **1 isolated node(s):** `backup_lansentry.sh script`
  These have ≤1 connection - possible missing edges or undocumented components. (Counts symbols only; 18 node(s) total have ≤1 connection when file, concept and rationale nodes are included.)
- **5 thin communities (<3 nodes) omitted from report** — run `graphify query` to explore isolated nodes.

## Suggested Questions
_Questions this graph is uniquely positioned to answer:_

- **Why does `LanSentryProxyHandler` connect `LanSentryProxyHandler` to `sidecar.py`, `get_pg_connection`?**
  _High betweenness centrality (0.080) - this node is a cross-community bridge._
- **Why does `enrich_devices()` connect `enrich_devices` to `lookup_mac_vendor_api`, `sidecar.py`, `get_pg_connection`, `suggest_device_name`?**
  _High betweenness centrality (0.047) - this node is a cross-community bridge._
- **Why does `handle_block_toggle()` connect `get_pg_connection` to `sync_blocks`, `sidecar.py`, `auto_classify_devices`, `reload_pihole_lists`?**
  _High betweenness centrality (0.046) - this node is a cross-community bridge._
- **What connects `backup_lansentry.sh script` to the rest of the system?**
  _1 weakly-connected nodes found - possible documentation gaps or missing edges._