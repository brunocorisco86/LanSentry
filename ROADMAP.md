# 🗺️ LanSentry Roadmap & Evolução

Este documento registra o ciclo de desenvolvimento, marcos concluídos e os próximos passos planejados para o **LanSentry**.

---

## 🏁 Versão Atual: v1.1.0 (Produção Ativa)

### ✅ Marco 1: Fundação & Catálogo L2
- [x] Motor de escaneamento ARP de Camada 2 via container `aceberg/watchyourlan:v2`.
- [x] Persistência relacional em PostgreSQL 15 (`postgres_db`).
- [x] Modo `network_mode: host` na interface física `eth0`.
- [x] Deploy modular em Docker Compose (Dev local + Prod Raspberry Pi).

### ✅ Marco 2: Auto-Enricher & Identificação Inteligente
- [x] Base OUI local para tradução rápida de MAC para fabricante.
- [x] Fallback automático para `api.macvendors.com` para fabricantes não catalogados na OUI.
- [x] Cache local em memória e controle de taxa (rate-limiting) para consultas externas.
- [x] Resolução reversa de DNS PTR via Unbound/Pi-hole local (`.lan`).
- [x] Nomenclatura contextual inteligente baseada em fabricante (Tuya, Espressif, Midea, Amazon Echo, Raspberry Pi, Motorola, etc.).

### ✅ Marco 3: Mecanismo de Bloqueio & Alertas
- [x] Política estrita de **"Allow by Default"** (novos aparelhos entram sempre liberados).
- [x] Criação automática do grupo `LANSENTRY_BLOCKED` com regex coringa `.*` no `gravity.db` do Pi-hole.
- [x] Injeção dinâmica no frontend (`custom.js` via proxy transparente na porta 8840).
- [x] Toggle switch de bloqueio na **tabela principal** (`/`) e na **tela de detalhes** (`/#/host/:id`).
- [x] Notificações push via `ntfy` (`bruno-casa-dallas`) com prioridade e links clicáveis diretamente para a tela do host.

### ✅ Marco 4: Sinergia Bidirecional com Pi-hole v6
- [x] Mapeamento dos 8 grupos de rede do Pi-hole (`Infraestrutura`, `IoT & Smart Home`, `Assistentes & Streaming`, `Dispositivos Móveis`, `Workstations & PCs`, `Kids & Família`, `Default`, `Bloqueado`).
- [x] Coluna com badges coloridos de grupos na tabela principal do LanSentry.
- [x] Seletor interativo `<select>` na tela de detalhes do aparelho para trocar o grupo do Pi-hole diretamente pelo LanSentry com feedback em tempo real.
- [x] Sincronização automática de nomes amigáveis para a tabela `network_addresses` do `pihole-FTL.db` (fim dos IPs anônimos no Query Log e Top Clients do Pi-hole).
- [x] Auto-classificação de novos dispositivos no grupo apropriado do Pi-hole com envio de alerta informativo.

### ✅ Marco 5: Resiliência, Backup & Documentação
- [x] Migração para o pendrive USB (`/mnt/pendrive_cinza/14_LanSentry/`) preservando o cartão SD do Raspberry Pi.
- [x] Script de backup atômico (`backup_lansentry.sh`): dump compactado do PostgreSQL + snapshot do `gravity.db`.
- [x] Rotação automática de backups com retenção de 14 dias agendada no crontab (`03:45 AM`).
- [x] Grafo de conhecimento interativo gerado via `graphifyy` (`graphify-out/`).
- [x] Skill autônoma do agente criada em `.gemini/skills/lansentry/SKILL.md` e `~/.gemini/config/skills/lansentry/`.

---

## 🔮 Próximas Entregas (v1.2.0+)

### 📡 1. Auditoria de Segurança: Detecção de DNS Bypass (Dispositivos Furtivos)
- [ ] Monitorar se dispositivos que estão online e transmitindo pacotes ARP na rede possuem consultas registradas no `pihole-FTL.db`.
- [ ] Alertar via `ntfy` quando um aparelho estiver ativo na LAN por mais de 3 horas sem realizar nenhuma consulta DNS no Pi-hole (identificando DoH, DNS estático como 8.8.8.8 ou bypass de DHCP).

### 📊 2. Telemetria DNS Integrada no Card do Dispositivo
- [ ] Exibir na tela `/#/host/:id` um pequeno resumo de atividade do Pi-hole:
  - Total de consultas DNS realizadas nas últimas 24 horas.
  - Porcentagem de consultas bloqueadas por listas de anúncios.
  - Último domínio consultado.

### 🏷️ 3. Agrupamento em Lote e Ações Rápidas
- [ ] Permitir selecionar múltiplos dispositivos na tabela principal para mover em lote para um grupo do Pi-hole (ex: selecionar todos os sensores recém-descobertos e mover para `IoT & Smart Home`).
- [ ] Exportação do catálogo de inventário em formatos CSV e JSON.

### 🌐 4. Suporte a Múltiplas Sub-redes e VLANs
- [ ] Suporte a escaneamento de interfaces virtuais adicionais (ex: VLAN de visitantes `vlan10`, VLAN de automação `vlan20`).
