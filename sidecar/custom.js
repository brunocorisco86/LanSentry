// LanSentry UI Enhancement
// Injeta dinamicamente a coluna e o toggle de bloqueio na tabela inicial e na tela de detalhes do host

(function() {
  console.log("🛡️ LanSentry UI Enhancement carregado!");

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
  `;
  document.head.appendChild(style);

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

  // 1. Injeta coluna de bloqueio na tabela principal
  function enhanceTable() {
    const thead = document.querySelector('table thead tr');
    if (!thead) return;

    if (!thead.querySelector('.lansentry-th-block')) {
      const th = document.createElement('th');
      th.className = 'lansentry-th-block';
      th.style.width = '6em';
      th.innerHTML = '<i class="bi bi-shield-slash-fill text-danger" title="Bloquear no Pi-hole"></i> Bloquear';
      thead.appendChild(th);
    }

    const rows = document.querySelectorAll('table tbody tr');
    rows.forEach(tr => {
      // Ignora se for tabela da página de host (que tem ID na primeira coluna)
      if (tr.children[0] && tr.children[0].textContent.trim() === 'ID') return;
      if (tr.querySelector('.lansentry-td-block')) return;

      const hostId = getHostIdFromRow(tr);
      if (!hostId) return;

      const nameCell = tr.children[1];
      const isBlocked = nameCell && nameCell.textContent.includes('[BLOCK]');

      if (isBlocked) {
        tr.classList.add('lansentry-blocked-row');
      }

      const td = document.createElement('td');
      td.className = 'lansentry-td-block';
      td.innerHTML = `
        <div class="form-check form-switch" title="${isBlocked ? 'Dispositivo Bloqueado no Pi-hole' : 'Clique para Bloquear no Pi-hole'}">
          <input class="form-check-input lansentry-block-toggle" type="checkbox" ${isBlocked ? 'checked' : ''} style="cursor: pointer;">
        </div>
      `;

      const switchInput = td.querySelector('input');
      switchInput.addEventListener('change', (e) => {
        toggleBlock(hostId, e.target.checked, switchInput, tr, null);
      });

      tr.appendChild(td);
    });
  }

  // 2. Injeta linha de bloqueio na tela de detalhes do host (/host/:id)
  function enhanceHostPage() {
    // Procura a linha com ID
    const rows = Array.from(document.querySelectorAll('table tbody tr'));
    const idRow = rows.find(r => r.children[0] && r.children[0].textContent.trim() === 'ID');
    if (!idRow) return;

    // Se já foi injetado nesta tabela, não repete
    if (document.querySelector('.lansentry-hostpage-block-row')) return;

    const hostId = idRow.children[1] ? idRow.children[1].textContent.trim() : null;
    if (!hostId) return;

    const nameRow = rows.find(r => r.children[0] && r.children[0].textContent.trim() === 'Name');
    const nameInput = nameRow ? nameRow.querySelector('input') : null;
    const isBlocked = nameInput ? nameInput.value.includes('[BLOCK]') : false;

    // Procura a linha do Known para inserir logo após
    const knownRow = rows.find(r => r.children[0] && r.children[0].textContent.trim() === 'Known');
    const targetRow = knownRow || idRow;

    const newTr = document.createElement('tr');
    newTr.className = 'lansentry-hostpage-block-row';
    newTr.innerHTML = `
      <td><strong>Bloquear no Pi-hole</strong></td>
      <td>
        <div class="form-check form-switch d-flex align-items-center">
          <input class="form-check-input lansentry-block-toggle" type="checkbox" ${isBlocked ? 'checked' : ''} style="cursor: pointer;">
          <span class="ms-2 badge bg-danger ${isBlocked ? '' : 'd-none'} lansentry-block-badge">🚫 Acesso Revogado</span>
        </div>
      </td>
    `;

    const switchInput = newTr.querySelector('input');
    const badge = newTr.querySelector('.lansentry-block-badge');

    switchInput.addEventListener('change', (e) => {
      const willBlock = e.target.checked;
      toggleBlock(hostId, willBlock, switchInput, null, nameInput);
      if (willBlock) {
        badge.classList.remove('d-none');
      } else {
        badge.classList.add('d-none');
      }
    });

    // Insere logo após a linha do Known
    targetRow.parentNode.insertBefore(newTr, targetRow.nextSibling);
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
