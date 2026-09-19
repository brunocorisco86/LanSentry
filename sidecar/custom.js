// LanSentry UI Enhancement
// Injeta dinamicamente a coluna e o toggle de bloqueio na tabela inicial e na tela de detalhes do host,
// além de exibir e permitir a alteração do Grupo do Pi-hole em tempo real.

(function() {
  console.log("🛡️ LanSentry UI Enhancement carregado com suporte a Grupos do Pi-hole!");

  // Injeta estilos CSS
  const style = document.createElement('style');
  style.innerHTML = `
    .lansentry-block-toggle:checked {
      background-color: #dc3545 !important;
      border-color: #dc3545 !important;
    }
    .lansentry-blocked-row {
      background-color: rgba(220, 53, 69, 0.15) !important;
    }
    .lansentry-block-badge {
      font-size: 0.8rem;
      padding: 0.25rem 0.5rem;
    }
    .lansentry-pihole-badge {
      font-size: 0.78rem;
      font-weight: 500;
      letter-spacing: 0.02em;
    }
  `;
  document.head.appendChild(style);

  let piholeData = { groups: [], clients: {} };
  let deviceMap = {};
  let isFetching = false;

  async function loadData() {
    if (isFetching) return;
    isFetching = true;
    try {
      const [piholeResp, allResp] = await Promise.all([
        fetch('/api/pihole/info').then(r => r.json()).catch(() => null),
        fetch('/api/all').then(r => r.json()).catch(() => null)
      ]);

      if (piholeResp) {
        piholeData = piholeResp;
      }

      if (allResp && Array.isArray(allResp)) {
        deviceMap = {};
        for (const dev of allResp) {
          deviceMap[String(dev.ID)] = dev;
        }
      }
    } catch (e) {
      console.warn("Aviso ao carregar dados LanSentry/Pi-hole:", e);
    } finally {
      isFetching = false;
    }
  }

  // Carrega inicialmente e a cada 15 segundos
  loadData();
  setInterval(loadData, 15000);

  function getGroupBadge(groupName) {
    const name = groupName || 'Default';
    switch (name) {
      case 'Infraestrutura':
        return '<span class="badge bg-info text-dark lansentry-pihole-badge">🌐 Infraestrutura</span>';
      case 'IoT & Smart Home':
        return '<span class="badge bg-success lansentry-pihole-badge">💡 IoT & Automação</span>';
      case 'Assistentes & Streaming':
        return '<span class="badge bg-primary lansentry-pihole-badge">📺 Streaming & Alexa</span>';
      case 'Dispositivos Móveis':
        return '<span class="badge bg-warning text-dark lansentry-pihole-badge">📱 Dispositivo Móvel</span>';
      case 'Workstations & PCs':
        return '<span class="badge bg-secondary lansentry-pihole-badge">💻 Workstation / PC</span>';
      case 'Kids & Família':
        return '<span class="badge bg-danger lansentry-pihole-badge">👶 Kids & Família</span>';
      case 'LANSENTRY_BLOCKED':
        return '<span class="badge bg-dark text-danger lansentry-pihole-badge">🚫 Bloqueado</span>';
      default:
        return '<span class="badge bg-light text-secondary border lansentry-pihole-badge">⚪ Padrão</span>';
    }
  }

  function getHostIdFromRow(tr) {
    const links = tr.querySelectorAll('a[href*="/host/"]');
    for (const a of links) {
      const match = a.getAttribute('href').match(/\/host\/(\d+)/);
      if (match) return match[1];
    }
    return null;
  }

  async function toggleBlock(id, willBlock, checkbox, tr, nameInput) {
    checkbox.disabled = true;
    try {
      const resp = await fetch(`/api/block_toggle/${id}/${willBlock ? '1' : '0'}`, {
        method: 'POST'
      });
      const data = await resp.json();
      if (data.success) {
        if (tr) {
          if (willBlock) {
            tr.classList.add('lansentry-blocked-row');
          } else {
            tr.classList.remove('lansentry-blocked-row');
          }
        }
        if (nameInput) {
          const currentVal = nameInput.value || '';
          if (willBlock) {
            if (!currentVal.includes('[BLOCK]')) {
              nameInput.value = `[BLOCK] ${currentVal}`.trim();
            }
          } else {
            nameInput.value = currentVal.replace('[BLOCK]', '').trim();
          }
        }
        await loadData();
      } else {
        alert("Falha ao atualizar bloqueio: " + (data.error || "erro desconhecido"));
        checkbox.checked = !willBlock;
      }
    } catch (e) {
      console.error("Erro na chamada de bloqueio:", e);
      checkbox.checked = !willBlock;
    } finally {
      checkbox.disabled = false;
    }
  }

  // 1. Injeta colunas de Grupo Pi-hole e Bloqueio na tabela principal
  function enhanceTable() {
    const thead = document.querySelector('table thead tr');
    if (!thead) return;

    // Cabeçalho Grupo Pi-hole
    if (!thead.querySelector('.lansentry-th-group')) {
      const thGroup = document.createElement('th');
      thGroup.className = 'lansentry-th-group';
      thGroup.style.width = '12em';
      thGroup.innerHTML = '<i class="bi bi-diagram-3-fill text-primary" title="Grupo atribuído no Pi-hole"></i> Grupo Pi-hole';
      thead.appendChild(thGroup);
    }

    // Cabeçalho Bloqueio
    if (!thead.querySelector('.lansentry-th-block')) {
      const thBlock = document.createElement('th');
      thBlock.className = 'lansentry-th-block';
      thBlock.style.width = '6em';
      thBlock.innerHTML = '<i class="bi bi-shield-slash-fill text-danger" title="Bloquear no Pi-hole"></i> Bloquear';
      thead.appendChild(thBlock);
    }

    const rows = document.querySelectorAll('table tbody tr');
    rows.forEach(tr => {
      // Ignora se for tabela da página de host (que tem ID na primeira coluna)
      if (tr.children[0] && tr.children[0].textContent.trim() === 'ID') return;

      const hostId = getHostIdFromRow(tr);
      if (!hostId) return;

      const dev = deviceMap[hostId];
      const mac = dev && dev.Mac ? dev.Mac.toUpperCase().trim() : '';
      const ip = dev && dev.IP ? dev.IP.trim() : '';

      const nameCell = tr.children[1];
      const isBlocked = nameCell && nameCell.textContent.includes('[BLOCK]');

      if (isBlocked) {
        tr.classList.add('lansentry-blocked-row');
      }

      // Injeta célula de Grupo Pi-hole
      if (!tr.querySelector('.lansentry-td-group')) {
        let groupName = 'Default';
        if (piholeData && piholeData.clients) {
          const clientInfo = piholeData.clients[mac] || (ip ? piholeData.clients[ip.toUpperCase()] : null);
          if (clientInfo) {
            groupName = clientInfo.primary_group_name || 'Default';
          }
        }

        const tdGroup = document.createElement('td');
        tdGroup.className = 'lansentry-td-group';
        tdGroup.innerHTML = getGroupBadge(groupName);
        tr.appendChild(tdGroup);
      } else {
        // Atualiza badge se os dados mudaram
        const tdGroup = tr.querySelector('.lansentry-td-group');
        let groupName = 'Default';
        if (piholeData && piholeData.clients) {
          const clientInfo = piholeData.clients[mac] || (ip ? piholeData.clients[ip.toUpperCase()] : null);
          if (clientInfo) {
            groupName = clientInfo.primary_group_name || 'Default';
          }
        }
        tdGroup.innerHTML = getGroupBadge(groupName);
      }

      // Injeta célula de Toggle de Bloqueio
      if (!tr.querySelector('.lansentry-td-block')) {
        const tdBlock = document.createElement('td');
        tdBlock.className = 'lansentry-td-block';
        tdBlock.innerHTML = `
          <div class="form-check form-switch" title="${isBlocked ? 'Dispositivo Bloqueado no Pi-hole' : 'Clique para Bloquear no Pi-hole'}">
            <input class="form-check-input lansentry-block-toggle" type="checkbox" ${isBlocked ? 'checked' : ''} style="cursor: pointer;">
          </div>
        `;

        const switchInput = tdBlock.querySelector('input');
        switchInput.addEventListener('change', (e) => {
          toggleBlock(hostId, e.target.checked, switchInput, tr, null);
        });

        tr.appendChild(tdBlock);
      }
    });
  }

  // 2. Injeta linha de grupo e bloqueio na tela de detalhes do host (/host/:id)
  function enhanceHostPage() {
    const rows = Array.from(document.querySelectorAll('table tbody tr'));
    const idRow = rows.find(r => r.children[0] && r.children[0].textContent.trim() === 'ID');
    if (!idRow) return;

    const hostId = idRow.children[1] ? idRow.children[1].textContent.trim() : null;
    if (!hostId) return;

    const dev = deviceMap[hostId];
    const mac = dev && dev.Mac ? dev.Mac.toUpperCase().trim() : '';
    const ip = dev && dev.IP ? dev.IP.trim() : '';

    const nameRow = rows.find(r => r.children[0] && r.children[0].textContent.trim() === 'Name');
    const nameInput = nameRow ? nameRow.querySelector('input') : null;
    const isBlocked = nameInput ? nameInput.value.includes('[BLOCK]') : false;

    const knownRow = rows.find(r => r.children[0] && r.children[0].textContent.trim() === 'Known');
    const targetRow = knownRow || idRow;

    // Injeta Seletor de Grupo do Pi-hole
    if (!document.querySelector('.lansentry-hostpage-group-row')) {
      let currentGroupId = 0;
      if (piholeData && piholeData.clients) {
        const clientInfo = piholeData.clients[mac] || (ip ? piholeData.clients[ip.toUpperCase()] : null);
        if (clientInfo) {
          currentGroupId = clientInfo.primary_group_id || 0;
        }
      }

      const groups = (piholeData && piholeData.groups && piholeData.groups.length > 0) 
        ? piholeData.groups 
        : [
            { id: 0, name: "Default" },
            { id: 1, name: "Infraestrutura" },
            { id: 2, name: "IoT & Smart Home" },
            { id: 3, name: "Assistentes & Streaming" },
            { id: 4, name: "Dispositivos Móveis" },
            { id: 5, name: "Workstations & PCs" },
            { id: 6, name: "Kids & Família" }
          ];

      const optionsHtml = groups.map(g => 
        `<option value="${g.id}" ${Number(g.id) === Number(currentGroupId) ? 'selected' : ''}>${g.name}</option>`
      ).join('');

      const groupTr = document.createElement('tr');
      groupTr.className = 'lansentry-hostpage-group-row';
      groupTr.innerHTML = `
        <td><strong>Grupo no Pi-hole</strong></td>
        <td>
          <div class="d-flex align-items-center">
            <select class="form-select form-select-sm w-auto me-2 lansentry-group-select" style="min-width: 220px; font-weight: 500;">
              ${optionsHtml}
            </select>
            <span class="badge bg-success d-none lansentry-group-feedback">✓ Atualizado</span>
          </div>
        </td>
      `;

      const selectElem = groupTr.querySelector('.lansentry-group-select');
      const feedbackElem = groupTr.querySelector('.lansentry-group-feedback');

      selectElem.addEventListener('change', async (e) => {
        const newGid = e.target.value;
        selectElem.disabled = true;
        try {
          const resp = await fetch(`/api/pihole/set_group/${hostId}/${newGid}`, { method: 'POST' });
          const res = await resp.json();
          if (res.success) {
            feedbackElem.classList.remove('d-none');
            setTimeout(() => feedbackElem.classList.add('d-none'), 3000);
            await loadData();
          } else {
            alert("Erro ao alterar grupo: " + (res.error || "desconhecido"));
          }
        } catch (err) {
          alert("Erro de rede ao alterar grupo: " + err);
        } finally {
          selectElem.disabled = false;
        }
      });

      targetRow.parentNode.insertBefore(groupTr, targetRow.nextSibling);
    }

    // Injeta Linha de Bloqueio no Host Page
    if (!document.querySelector('.lansentry-hostpage-block-row')) {
      const blockTr = document.createElement('tr');
      blockTr.className = 'lansentry-hostpage-block-row';
      blockTr.innerHTML = `
        <td><strong>Bloquear no Pi-hole</strong></td>
        <td>
          <div class="form-check form-switch d-flex align-items-center">
            <input class="form-check-input lansentry-block-toggle" type="checkbox" ${isBlocked ? 'checked' : ''} style="cursor: pointer;">
            <span class="ms-2 badge bg-danger ${isBlocked ? '' : 'd-none'} lansentry-block-badge">🚫 Acesso Revogado</span>
          </div>
        </td>
      `;

      const switchInput = blockTr.querySelector('input');
      const badge = blockTr.querySelector('.lansentry-block-badge');

      switchInput.addEventListener('change', (e) => {
        const willBlock = e.target.checked;
        toggleBlock(hostId, willBlock, switchInput, null, nameInput);
        if (willBlock) {
          badge.classList.remove('d-none');
        } else {
          badge.classList.add('d-none');
        }
      });

      const groupRow = document.querySelector('.lansentry-hostpage-group-row');
      const insertAnchor = groupRow || targetRow;
      insertAnchor.parentNode.insertBefore(blockTr, insertAnchor.nextSibling);
    }
  }

  function runEnhancements() {
    enhanceTable();
    enhanceHostPage();
  }

  const observer = new MutationObserver(() => {
    runEnhancements();
  });

  observer.observe(document.body, { childList: true, subtree: true });
  setInterval(runEnhancements, 800);
})();
