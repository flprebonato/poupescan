const isLiveServer = window.location.pathname.includes('/frontend/');
const backendHost = window.location.hostname === 'localhost' ? 'localhost' : '127.0.0.1';
const apiBaseUrl = isLiveServer ? `http://${backendHost}:8000` : '';
const settingsModal = document.querySelector('#settings-modal');
const settingsForm = document.querySelector('#settings-form');
const settingsNotice = document.querySelector('#settings-notice');
const settingsPasswordTrigger = document.querySelector('#settings-password-trigger');
const settingsPasswordFields = document.querySelector('#settings-password-fields');
const accountFeedbackModal = document.querySelector('#account-feedback-modal');
const accountFeedbackText = document.querySelector('#account-feedback-text');
let usuarioAtual = null;
let elementoAntesDoModal = null;
let elementoAntesDoFeedback = null;

async function lerRespostaJson(response) {
    const contentType = response.headers.get('content-type') || '';
    if (!contentType.includes('application/json')) {
        await response.text();
        throw new Error('O servidor encontrou um problema. Tente novamente em instantes.');
    }
    return response.json();
}

function atualizarNomeUsuario(usuario) {
    document.querySelector('#user-name').textContent = usuario.nome.split(' ')[0];
}

async function carregarUsuario() {
    const response = await fetch(`${apiBaseUrl}/api/auth/me`, { credentials: 'include' });
    if (!response.ok) {
        window.location.replace(apiBaseUrl || '/');
        return;
    }

    usuarioAtual = await lerRespostaJson(response);
    atualizarNomeUsuario(usuarioAtual);
}

function limparErro(input) {
    const field = input.closest('.settings-field');
    field.classList.remove('has-error');
    input.setAttribute('aria-invalid', 'false');
    field.querySelector('.settings-error').textContent = '';
}

function mostrarErro(input, mensagem) {
    const field = input.closest('.settings-field');
    field.classList.add('has-error');
    input.setAttribute('aria-invalid', 'true');
    field.querySelector('.settings-error').textContent = mensagem;
}

function limparErros() {
    settingsForm.querySelectorAll('input').forEach(limparErro);
    settingsNotice.hidden = true;
    settingsNotice.className = 'settings-notice';
    settingsNotice.textContent = '';
}

function mostrarAviso(mensagem, tipo = 'error') {
    settingsNotice.textContent = mensagem;
    settingsNotice.className = `settings-notice ${tipo}`;
    settingsNotice.hidden = false;
}

function validarConfiguracoes() {
    limparErros();
    const nome = document.querySelector('#settings-name');
    const email = document.querySelector('#settings-email');
    const novaSenha = document.querySelector('#settings-new-password');
    const confirmarSenha = document.querySelector('#settings-confirm-password');
    const senhaAtual = document.querySelector('#settings-current-password');
    let primeiroInvalido = null;

    const invalidar = (input, mensagem) => {
        mostrarErro(input, mensagem);
        primeiroInvalido ||= input;
    };

    nome.value = nome.value.trim().replace(/\s+/g, ' ');
    if (nome.value.length < 2) invalidar(nome, 'Digite seu nome.');
    if (!email.value) invalidar(email, 'Digite seu e-mail.');
    else if (!email.validity.valid) invalidar(email, 'Digite um e-mail válido.');
    if (novaSenha.value && novaSenha.value.length < 10) {
        invalidar(novaSenha, 'Use pelo menos 10 caracteres.');
    }
    if (novaSenha.value !== confirmarSenha.value) {
        invalidar(confirmarSenha, 'As novas senhas não coincidem.');
    }
    if (!senhaAtual.value) invalidar(senhaAtual, 'Digite sua senha atual.');

    primeiroInvalido?.focus();
    return !primeiroInvalido;
}

function abrirConfiguracoes() {
    if (!usuarioAtual) return;

    elementoAntesDoModal = document.activeElement;
    settingsForm.reset();
    definirAlteracaoSenhaAberta(false);
    limparErros();
    document.querySelector('#settings-name').value = usuarioAtual.nome;
    document.querySelector('#settings-email').value = usuarioAtual.email;
    settingsModal.hidden = false;
    document.body.classList.add('settings-open');
    document.querySelector('#settings-name').focus();
}

function definirAlteracaoSenhaAberta(aberta) {
    settingsPasswordFields.hidden = !aberta;
    settingsPasswordTrigger.setAttribute('aria-expanded', String(aberta));

    if (!aberta) {
        settingsPasswordFields.querySelectorAll('input').forEach((input) => {
            input.value = '';
            limparErro(input);
        });
        settingsPasswordFields.querySelectorAll('.settings-password-toggle').forEach((button) => {
            const input = document.querySelector(`#${button.dataset.passwordTarget}`);
            input.type = 'password';
            button.classList.remove('is-visible');
            button.setAttribute('aria-pressed', 'false');
            button.setAttribute('aria-label', button.getAttribute('aria-label').replace('Ocultar', 'Mostrar'));
        });
    }
}

function ocultarSenhasConfiguracoes() {
    settingsForm.querySelectorAll('.settings-password-toggle').forEach((button) => {
        const input = document.querySelector(`#${button.dataset.passwordTarget}`);
        input.type = 'password';
        button.classList.remove('is-visible');
        button.setAttribute('aria-pressed', 'false');
        button.setAttribute('aria-label', button.getAttribute('aria-label').replace('Ocultar', 'Mostrar'));
    });
}

function fecharConfiguracoes() {
    definirAlteracaoSenhaAberta(false);
    ocultarSenhasConfiguracoes();
    settingsModal.hidden = true;
    document.body.classList.remove('settings-open');
    elementoAntesDoModal?.focus();
}

function mostrarSucessoAtualizacao(mensagem) {
    elementoAntesDoFeedback = document.activeElement;
    accountFeedbackText.textContent = mensagem;
    accountFeedbackModal.hidden = false;
    document.body.classList.add('feedback-open');
    document.querySelector('#account-feedback-button').focus();
}

function fecharFeedbackAtualizacao() {
    accountFeedbackModal.hidden = true;
    document.body.classList.remove('feedback-open');
    elementoAntesDoFeedback?.focus();
}

document.querySelector('#settings-button').addEventListener('click', abrirConfiguracoes);
document.querySelector('#settings-close').addEventListener('click', fecharConfiguracoes);
document.querySelector('#settings-cancel').addEventListener('click', fecharConfiguracoes);
settingsPasswordTrigger.addEventListener('click', () => {
    definirAlteracaoSenhaAberta(settingsPasswordFields.hidden);
    if (!settingsPasswordFields.hidden) document.querySelector('#settings-new-password').focus();
});
settingsModal.addEventListener('click', (event) => {
    if (event.target === settingsModal) fecharConfiguracoes();
});
document.querySelector('#account-feedback-close').addEventListener('click', fecharFeedbackAtualizacao);
document.querySelector('#account-feedback-button').addEventListener('click', fecharFeedbackAtualizacao);
accountFeedbackModal.addEventListener('click', (event) => {
    if (event.target === accountFeedbackModal) fecharFeedbackAtualizacao();
});
document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape') return;
    if (!accountFeedbackModal.hidden) fecharFeedbackAtualizacao();
    else if (!settingsModal.hidden) fecharConfiguracoes();
});

settingsForm.querySelectorAll('input').forEach((input) => {
    input.addEventListener('input', () => limparErro(input));
});

settingsForm.querySelectorAll('.settings-password-toggle').forEach((button) => {
    button.addEventListener('click', () => {
        const input = document.querySelector(`#${button.dataset.passwordTarget}`);
        const deveMostrar = input.type === 'password';

        input.type = deveMostrar ? 'text' : 'password';
        button.classList.toggle('is-visible', deveMostrar);
        button.setAttribute('aria-pressed', String(deveMostrar));
        button.setAttribute('aria-label', deveMostrar
            ? button.getAttribute('aria-label').replace('Mostrar', 'Ocultar')
            : button.getAttribute('aria-label').replace('Ocultar', 'Mostrar'));
    });
});

settingsForm.addEventListener('submit', async (event) => {
    event.preventDefault();
    if (!validarConfiguracoes()) return;

    const button = settingsForm.querySelector('.settings-save');
    const textoOriginal = button.textContent;
    const dados = Object.fromEntries(new FormData(settingsForm));
    delete dados.confirmar_senha;
    if (!dados.nova_senha) delete dados.nova_senha;

    button.disabled = true;
    button.textContent = 'Salvando...';

    try {
        const response = await fetch(`${apiBaseUrl}/api/auth/me`, {
            method: 'PATCH',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados),
        });
        const resultado = await lerRespostaJson(response);

        if (!response.ok) {
            const mensagem = typeof resultado.detail === 'string'
                ? resultado.detail
                : 'Verifique os dados informados.';
            throw new Error(mensagem);
        }

        usuarioAtual = resultado.usuario;
        atualizarNomeUsuario(usuarioAtual);
        document.querySelector('#settings-current-password').value = '';
        document.querySelector('#settings-new-password').value = '';
        document.querySelector('#settings-confirm-password').value = '';
        fecharConfiguracoes();
        mostrarSucessoAtualizacao(resultado.mensagem);
    } catch (error) {
        if (error.message === 'A senha atual está incorreta.') {
            const senhaAtual = document.querySelector('#settings-current-password');
            mostrarErro(senhaAtual, error.message);
            senhaAtual.focus();
        } else if (error.message === 'Este e-mail já está associado a uma conta.') {
            const email = document.querySelector('#settings-email');
            mostrarErro(email, error.message);
            email.focus();
        } else {
            const mensagem = error instanceof TypeError
                ? 'Não foi possível conectar ao servidor.'
                : error.message;
            mostrarAviso(mensagem);
        }
    } finally {
        button.disabled = false;
        button.textContent = textoOriginal;
    }
});

document.querySelector('#logout-button').addEventListener('click', async () => {
    await fetch(`${apiBaseUrl}/api/auth/logout`, { method: 'POST', credentials: 'include' });
    window.location.replace(apiBaseUrl || '/');
});

carregarUsuario().catch(() => window.location.replace(apiBaseUrl || '/'));

(() => {
    'use strict';
    const $ = (selector) => document.querySelector(selector);
    const form = $('#expense-review');
    const fields = [...form.querySelectorAll('[data-field]')];
    const itemBody = $('#expense-items');
    const money = new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL' });
    let file = null;
    let previewUrl = null;
    let busy = false;
    let hasRead = false;
    let storeRegistration = null;
    let cnpjTimer = null;
    let cnpjController = null;
    let cnpjVersion = 0;
    let cnpjPending = false;
    let dirty = false;
    let currentRoute = '';
    let detailId = null;
    let historyOffset = 0;
    let historyLoading = false;
    let historyVersion = 0;
    let selectionVersion = 0;
    let savedMessage = '';
    let totalsMismatch = false;
    let editId = null;
    let savedStore = null;

    function notice(id, text, kind = '') {
        const el = $(id);
        el.textContent = text;
        el.className = `expense-notice ${kind}`;
        el.hidden = !text;
        if (id === '#expense-notice' && text) el.scrollIntoView({ block: 'center' });
    }

    async function request(path, options = {}) {
        const response = await fetch(`${apiBaseUrl}${path}`, { credentials: 'include', ...options });
        if (response.status === 401) {
            window.location.replace(apiBaseUrl || '/');
            throw new Error('Sua sessão expirou. Faça login novamente.');
        }
        if (response.status === 204) return null;
        const result = await lerRespostaJson(response);
        if (!response.ok) {
            const detail = result.detail;
            const error = new Error(typeof detail === 'string' ? detail : detail?.mensagem || 'Não foi possível concluir. Tente novamente.');
            error.fields = detail?.campos || [];
            throw error;
        }
        return result;
    }

    function currentCnpj() {
        return $('#exp-cnpj').value.replace(/[./\s-]/g, '');
    }

    function registrationReady() {
        return storeRegistration?.cnpj === currentCnpj() && storeRegistration?.validado === true;
    }

    // Na correção, o estabelecimento salvo continua válido enquanto o CNPJ não for trocado.
    function storeReady() {
        return registrationReady() || savedStore?.cnpj === currentCnpj();
    }

    function updateRegistrationControls() {
        $('#expense-save').disabled = busy || cnpjPending || !storeReady() || totalsMismatch;
        $('#cnpj-retry').disabled = busy || cnpjPending;
        $('#store-card').setAttribute('aria-busy', String(cnpjPending));
    }

    function resetRegistration() {
        clearTimeout(cnpjTimer);
        cnpjController?.abort();
        cnpjVersion++;
        cnpjPending = false;
        storeRegistration = null;
        $('#exp-estabelecimento').value = '';
        form.querySelectorAll('[data-address]').forEach(input => { input.value = ''; });
        $('#cnpj-retry').hidden = true;
        updateRegistrationControls();
    }

    function applyRegistration(registration = {}) {
        const valid = registration.status === 'sucesso' && registration.validado === true
            && registration.cnpj === currentCnpj() && Boolean(registration.razao_social);
        const saved = !valid && savedStore?.cnpj === currentCnpj();
        storeRegistration = valid ? registration : null;
        $('#exp-estabelecimento').value = valid ? registration.razao_social : saved ? savedStore.nome : '';
        form.querySelectorAll('[data-address]').forEach(input => {
            input.value = valid ? (registration.endereco_campos?.[input.dataset.address] ?? '') : '';
        });
        const statusLabels = {
            nao_identificado: 'Informe o CNPJ para preencher o estabelecimento.',
            cnpj_invalido: 'CNPJ inválido. Confira os dígitos.',
            desativada: 'A consulta de CNPJ está desativada. Ative-a para confirmar o estabelecimento.',
            indisponivel: 'Não foi possível consultar o CNPJ. Tente novamente.',
            nao_encontrado: 'CNPJ não encontrado no cadastro. Confira o número informado.',
        };
        notice('#cnpj-status', valid
            ? ['Dados preenchidos pelo cadastro do CNPJ', registration.situacao_cadastral].filter(Boolean).join(' · ')
            : saved ? `Não foi possível consultar o CNPJ agora. A despesa manterá o estabelecimento salvo${savedStore.endereco ? `, em ${savedStore.endereco}` : ''}.`
            : statusLabels[registration.status] || 'Consulte um CNPJ válido antes de salvar.', valid || saved ? 'info' : 'warning');
        $('#cnpj-retry').hidden = valid || !/^[0-9]{14}$/.test(currentCnpj());
        if (valid) inputError($('#exp-cnpj'), '');
        updateRegistrationControls();
    }

    function scheduleRegistration(immediate = false) {
        if (busy) return;
        if (!immediate && registrationReady()) return; // Alterar só a máscara não muda o cadastro.
        resetRegistration();
        const cnpj = currentCnpj();
        inputError($('#exp-cnpj'), '');
        if (!/^[0-9]{14}$/.test(cnpj)) {
            applyRegistration({ status: cnpj ? 'cnpj_invalido' : 'nao_identificado' });
            return;
        }
        const version = cnpjVersion;
        cnpjPending = true;
        notice('#cnpj-status', 'Consultando o CNPJ…', 'info');
        updateRegistrationControls();
        cnpjTimer = setTimeout(async () => {
            cnpjController = new AbortController();
            try {
                const registration = await request(`/api/estabelecimentos/cnpj/${cnpj}`, { signal: cnpjController.signal });
                if (version !== cnpjVersion || cnpj !== currentCnpj()) return;
                applyRegistration(registration);
            } catch (error) {
                if (version !== cnpjVersion || error.name === 'AbortError') return;
                applyRegistration({ status: 'indisponivel' });
            } finally {
                if (version === cnpjVersion) { cnpjPending = false; updateRegistrationControls(); }
            }
        }, immediate ? 0 : 450);
    }

    $('#cnpj-retry').addEventListener('click', () => scheduleRegistration(true));

    function setStep(step) {
        document.querySelectorAll('.expense-steps li').forEach((el, i) => {
            el.classList.toggle('complete', i < step - 1);
            if (i === step - 1) el.setAttribute('aria-current', 'step');
            else el.removeAttribute('aria-current');
        });
    }

    function setBusy(value, saving = false) {
        busy = value;
        $('#expense-create').setAttribute('aria-busy', String(value));
        $('#expense-create').querySelectorAll('button, input').forEach(el => { el.disabled = value; });
        $('#receipt-scan').disabled = value || !file;
        $('#scan-progress').hidden = !value || saving;
        $('#receipt-scan').textContent = value && !saving ? 'Processando…' : 'Enviar';
        const saveLabel = editId === null ? 'despesa' : 'alterações';
        $('#expense-save').textContent = value && saving ? `Salvando ${saveLabel}…` : `Salvar ${saveLabel}`;
        updateRegistrationControls();
        if (saving) setStep(value ? 3 : 2);
    }

    const receiptModal = $('#receipt-modal');
    const receiptContent = $('#receipt-modal-content');
    let receiptTrigger = null;
    const receiptUrl = id => `${apiBaseUrl}/api/despesas/${id}/imagem`;

    function openReceipt(src, trigger) {
        if (!src) return;
        receiptTrigger = trigger;
        $('#review-preview').src = src;
        receiptContent.classList.remove('is-zoomed');
        $('#receipt-zoom').setAttribute('aria-pressed', 'false');
        $('#receipt-zoom').setAttribute('aria-label', 'Ampliar imagem');
        $('#receipt-zoom').title = 'Ampliar imagem';
        receiptModal.showModal();
        receiptContent.scrollTo(0, 0);
        document.body.classList.add('receipt-modal-open');
    }

    $('#receipt-view').addEventListener('click', event => openReceipt(editId === null ? previewUrl : receiptUrl(editId), event.currentTarget));
    $('#receipt-modal-close').addEventListener('click', () => receiptModal.close());
    receiptModal.addEventListener('click', event => {
        if (event.target !== receiptModal) return;
        const bounds = receiptModal.getBoundingClientRect();
        if (event.clientX < bounds.left || event.clientX > bounds.right
            || event.clientY < bounds.top || event.clientY > bounds.bottom) receiptModal.close();
    });
    receiptModal.addEventListener('close', () => {
        document.body.classList.remove('receipt-modal-open');
        $('#review-preview').removeAttribute('src');
        receiptTrigger?.focus();
        receiptTrigger = null;
    });
    $('#receipt-zoom').addEventListener('click', () => {
        const zoomed = receiptContent.classList.toggle('is-zoomed');
        $('#receipt-zoom').setAttribute('aria-pressed', String(zoomed));
        const label = zoomed ? 'Ajustar à tela' : 'Ampliar imagem';
        $('#receipt-zoom').setAttribute('aria-label', label);
        $('#receipt-zoom').title = label;
        receiptContent.scrollTo(0, 0);
    });

    // A mesma tela confere a leitura de um novo comprovante e corrige despesas salvas.
    function setEditMode(id) {
        editId = id;
        const editing = id !== null;
        $('#create-title').textContent = editing ? 'Editar despesa' : 'Nova despesa';
        $('#create-subtitle').textContent = editing
            ? 'Você está corrigindo uma despesa já cadastrada. Ao salvar, as alterações substituem os dados atuais.'
            : 'Envie a imagem e confira os dados antes de salvar.';
        $('.expense-steps').hidden = editing;
        $('#receipt-upload').hidden = editing;
        $('#receipt-back').hidden = editing;
        $('#edit-cancel').hidden = !editing;
        $('#save-note').textContent = editing ? 'A imagem original do comprovante será mantida.' : 'A imagem será salva junto com a despesa após sua confirmação.';
        $('#expense-save').textContent = editing ? 'Salvar alterações' : 'Salvar despesa';
    }

    function clearFile() {
        if (receiptModal.open) receiptModal.close();
        resetRegistration();
        if (previewUrl) URL.revokeObjectURL(previewUrl);
        file = previewUrl = savedStore = null;
        hasRead = dirty = false;
        setEditMode(null);
        $('#receipt-file').value = '';
        $('#receipt-selection').hidden = true;
        $('#receipt-drop').hidden = false;
        $('#receipt-preview').removeAttribute('src');
        $('#review-preview').removeAttribute('src');
        $('#receipt-scan').disabled = true;
        $('#receipt-upload').hidden = false;
        form.hidden = true;
        form.reset();
        form.querySelectorAll('[data-calculated]').forEach(input => { delete input.dataset.calculated; });
        itemBody.replaceChildren();
        updateTotals();
        setStep(1);
    }

    async function selectFile(files) {
        if (busy) return;
        const version = ++selectionVersion;
        notice('#expense-notice', '');
        if (files.length !== 1) return notice('#expense-notice', 'Selecione somente uma imagem.');
        const candidate = files[0];
        if (!['image/jpeg', 'image/png'].includes(candidate.type)) return notice('#expense-notice', 'Formato não suportado. Envie uma imagem JPG ou PNG.');
        if (!candidate.size) return notice('#expense-notice', 'O arquivo está vazio. Selecione outra imagem.');
        if (candidate.size > 10 * 1024 * 1024) return notice('#expense-notice', 'O arquivo deve ter no máximo 10 MB.');
        const url = URL.createObjectURL(candidate);
        const image = new Image();
        image.src = url;
        try {
            await image.decode();
            if (image.naturalWidth * image.naturalHeight > 25000000) throw new Error('large');
        } catch (error) {
            URL.revokeObjectURL(url);
            return notice('#expense-notice', error.message === 'large' ? 'Reduza a imagem para até 25 megapixels.' : 'A imagem está corrompida ou não pôde ser aberta.');
        }
        if (version !== selectionVersion || busy) { URL.revokeObjectURL(url); return; }
        clearFile();
        file = candidate;
        previewUrl = url;
        dirty = true;
        $('#receipt-preview').src = url;
        $('#receipt-filename').textContent = candidate.name;
        $('#receipt-filesize').textContent = `${(candidate.size / (1024 * 1024)).toLocaleString('pt-BR', { maximumFractionDigits: 2 })} MB`;
        $('#receipt-selection').hidden = false;
        $('#receipt-drop').hidden = true;
        $('#receipt-scan').disabled = false;
    }

    $('#receipt-file').addEventListener('change', event => {
        if (event.target.files.length) selectFile(event.target.files);
        event.target.value = '';
    });
    $('#receipt-replace').addEventListener('click', () => $('#receipt-file').click());
    $('#receipt-remove').addEventListener('click', () => { clearFile(); notice('#expense-notice', ''); });
    const drop = $('#receipt-drop');
    ['dragenter', 'dragover'].forEach(type => drop.addEventListener(type, event => { event.preventDefault(); if (!busy) drop.classList.add('dragging'); }));
    ['dragleave', 'drop'].forEach(type => drop.addEventListener(type, event => { event.preventDefault(); drop.classList.remove('dragging'); }));
    drop.addEventListener('drop', event => selectFile(event.dataTransfer.files));

    function inputError(input, text) {
        input.setAttribute('aria-invalid', String(Boolean(text)));
        const error = input.closest('.expense-field')?.querySelector('.expense-error');
        if (error) error.textContent = text;
        input.setCustomValidity(text);
    }

    function markMissing(input) {
        const needsReview = !input.value || !input.validity.valid || Boolean(input.dataset.money && monetaryValue(input) === null);
        input.classList.toggle('needs-review', needsReview);
        input.classList.toggle('is-calculated', Boolean(input.dataset.calculated));
        input.title = input.dataset.calculated ? 'Calculado a partir dos outros valores. Confira com o comprovante.'
            : needsReview ? 'Não identificado ou inválido. Confira na imagem.' : '';
    }

    const columns = [
        ['codigo', 'Código', 'text', false, 80], ['descricao', 'Descrição', 'text', true, 500],
        ['quantidade', 'Quantidade', 'number', true],
        ['unidade', 'Unidade', 'text', false, 20], ['preco_unitario', 'Preço unitário', 'number', true],
        ['desconto', 'Desconto', 'number', false], ['preco_total', 'Total após desconto', 'number', false],
    ];

    function itemInput(key, label, type, required, max, value) {
        const input = document.createElement('input');
        input.dataset.itemField = key;
        input.setAttribute('aria-label', label);
        input.type = type;
        input.required = required;
        if (max) input.maxLength = max;
        if (type === 'number') {
            input.min = key === 'quantidade' ? '0.0001' : '0';
            input.step = ['quantidade', 'preco_unitario'].includes(key) ? '0.0001' : '0.01';
        }
        if (['preco_unitario', 'desconto', 'preco_total'].includes(key)) {
            input.type = 'text';
            input.inputMode = 'decimal';
            input.dataset.money = key === 'preco_unitario' ? '4' : '2';
        }
        setValue(input, value);
        markMissing(input);
        return input;
    }

    function addItem(item = {}, update = true) {
        const row = document.createElement('tr');
        row.dataset.id = item.id ?? '';
        row.dataset.original = item.descricao_original ?? item.descricao ?? '';
        row.dataset.apresentacao = item.apresentacao ?? '';
        columns.forEach(([key, label, type, required, max]) => {
            const td = document.createElement('td');
            td.append(itemInput(key, label, type, required, max, item[key]));
            row.append(td);
        });
        const actions = document.createElement('td');
        const remove = document.createElement('button');
        remove.type = 'button'; remove.className = 'expense-button item-remove'; remove.textContent = '×';
        remove.setAttribute('aria-label', 'Remover item');
        remove.addEventListener('click', () => { row.remove(); dirty = true; updateTotals(); });
        actions.append(remove); row.append(actions); itemBody.append(row);
        if (update) updateTotals();
        return row;
    }

    $('#item-add').addEventListener('click', () => { dirty = true; addItem().querySelector('[data-item-field="descricao"]').focus(); });
    $('#receipt-back').addEventListener('click', () => {
        if (hasRead && !window.confirm('Trocar o comprovante descarta os dados desta revisão. Continuar?')) return;
        clearFile(); notice('#expense-notice', ''); $('#receipt-file').focus();
    });

    $('#receipt-scan').addEventListener('click', async () => {
        if (busy || !file) return;
        notice('#expense-notice', ''); setBusy(true);
        const body = new FormData(); body.append('imagem', file);
        try {
            const data = await request('/api/scan', { method: 'POST', body });
            notice('#expense-notice', (data.avisos_leitura || []).join(' '), 'warning');
            fields.forEach(input => {
                delete input.dataset.calculated;
                setValue(input, data[input.dataset.field]);
                inputError(input, ''); markMissing(input);
            });
            applyRegistration(data.cadastro_cnpj);
            itemBody.replaceChildren();
            (data.itens || []).forEach(item => addItem(item, false));
            (data.campos_calculados || []).forEach(path => {
                const parts = path.split('.');
                const input = parts[0] === 'itens'
                    ? itemBody.children[Number(parts[1])]?.querySelector(`[data-item-field="${parts[2]}"]`)
                    : fields.find(field => field.dataset.field === path);
                if (input) input.dataset.calculated = 'true';
            });
            $('#receipt-upload').hidden = true; form.hidden = false; hasRead = true; setStep(2);
            updateTotals();
            $('#exp-cnpj').focus();
        } catch (error) { notice('#expense-notice', error.message || 'Falha na leitura. Tente novamente.'); }
        finally { setBusy(false); if (hasRead) $('#exp-cnpj').focus(); }
    });

    function serializeItems() {
        return [...itemBody.children].map(row => {
            const item = { descricao_original: row.dataset.original || null, apresentacao: row.dataset.apresentacao || null };
            if (row.dataset.id) item.id = Number(row.dataset.id);
            row.querySelectorAll('input').forEach(input => { item[input.dataset.itemField] = serializedValue(input); });
            return item;
        });
    }

    function cents(value) {
        return Math.round((value + Number.EPSILON) * 100);
    }

    function monetaryValue(input) {
        const text = input.value.trim().replace(/^R\$\s*/, '');
        if (!text) return null;
        const digits = Number(input.dataset.money);
        const pattern = new RegExp(`^(?:[0-9]+|[0-9]{1,3}(?:\\.[0-9]{3})+)(?:,[0-9]{1,${digits}})?$`);
        if (!pattern.test(text)) return null;
        const value = Number(text.replace(/\./g, '').replace(',', '.'));
        return Number.isFinite(value) && value <= 999999999999.99 ? value : null;
    }

    function setValue(input, value) {
        input.value = value === null || value === undefined || value === '' ? ''
            : input.dataset.money
                ? new Intl.NumberFormat('pt-BR', { style: 'currency', currency: 'BRL',
                    minimumFractionDigits: 2, maximumFractionDigits: Number(input.dataset.money) }).format(Number(value))
                : String(value);
    }

    function serializedValue(input) {
        return input.dataset.money ? monetaryValue(input) : input.value.trim() || null;
    }

    function amount(input) {
        if (input.dataset.money) return monetaryValue(input);
        return input.value !== '' && input.validity.valid ? Number(input.value) : null;
    }

    function calculated(input, value) {
        if (input.value !== '' || value === null || !Number.isFinite(value) || value < 0 || value > 999999999999.99) return;
        setValue(input, cents(value) / 100);
        input.dataset.calculated = 'true';
        inputError(input, '');
        markMissing(input);
    }

    function updateTotals() {
        // Recalcula os descontos a partir dos totais disponíveis.
        form.querySelectorAll('[data-calculated]').forEach(input => {
            input.value = '';
            delete input.dataset.calculated;
            inputError(input, '');
            markMissing(input);
        });
        const rows = [...itemBody.children];
        const totalValue = amount($('#exp-valor_total'));
        const paidValue = amount($('#exp-valor_pago'));
        const readDiscount = amount($('#exp-desconto_total'));
        const globalDiscount = readDiscount !== null ? cents(readDiscount)
            : totalValue !== null && paidValue !== null ? cents(totalValue) - cents(paidValue) : 0;
        const identifiedDiscounts = rows.reduce((sum, row) => {
            const input = key => row.querySelector(`[data-item-field="${key}"]`);
            const discount = amount(input('desconto'));
            if (discount !== null) return sum + cents(discount);
            const quantity = amount(input('quantidade')), unit = amount(input('preco_unitario')), net = amount(input('preco_total'));
            const weighted = ['KG', 'G', 'GR', 'L', 'LT', 'ML'].includes(input('unidade').value.trim().toUpperCase());
            return sum + (!weighted && quantity !== null && unit !== null && net !== null ? Math.max(0, cents(quantity * unit) - cents(net)) : 0);
        }, 0);
        const pendingDiscount = globalDiscount > identifiedDiscounts + 1;
        let complete = rows.length > 0;
        let sum = 0;
        let discounts = 0;
        let allDiscounts = true;
        let warning = '';
        rows.forEach((row, index) => {
            const input = key => row.querySelector(`[data-item-field="${key}"]`);
            const quantity = amount(input('quantidade'));
            const unit = amount(input('preco_unitario'));
            if (quantity === null || quantity <= 0 || unit === null) { complete = false; return; }
            const gross = cents(quantity * unit);
            sum += gross;
            const netInput = input('preco_total');
            const discountInput = input('desconto');
            const net = amount(netInput);
            const discount = amount(discountInput);
            const weighted = ['KG', 'G', 'GR', 'L', 'LT', 'ML'].includes(input('unidade').value.trim().toUpperCase());
            if (weighted && net !== null && discount === null && gross !== cents(net)) {
                warning ||= `Item ${index + 1}: confira o peso e o preço por unidade. A diferença não será tratada como desconto.`;
            } else if (net !== null && discount === null && (gross !== cents(net) || !pendingDiscount)) calculated(discountInput, (gross - cents(net)) / 100);
            else if (discount !== null) calculated(netInput, (gross - cents(discount)) / 100);
            const finalNet = amount(netInput);
            const finalDiscount = amount(discountInput);
            if (finalDiscount === null) allDiscounts = false;
            discounts += finalDiscount === null ? 0 : cents(finalDiscount);
            if ((finalNet !== null && cents(finalNet) > gross + 1)
                || (finalDiscount !== null && cents(finalDiscount) > gross)
                || (finalNet !== null && finalDiscount !== null && Math.abs(gross - cents(finalDiscount) - cents(finalNet)) > 1)) {
                warning ||= `Item ${index + 1}: quantidade × preço unitário, desconto e preço total não conferem. Corrija os valores para salvar.`;
            }
        });
        $('#items-empty').hidden = rows.length > 0;
        const totalInput = $('#exp-valor_total');
        const discountInput = $('#exp-desconto_total');
        const paidInput = $('#exp-valor_pago');
        if (complete && !warning) {
            calculated(totalInput, sum / 100);
            const total = amount(totalInput);
            if (total !== null && Math.abs(sum - cents(total)) <= 1) {
                const paid = amount(paidInput);
                if (paid !== null) calculated(discountInput, (cents(total) - cents(paid)) / 100);
                else if (allDiscounts) calculated(discountInput, discounts / 100);
                const discount = amount(discountInput);
                if (discount !== null && cents(discount) + 1 >= discounts) {
                    calculated(paidInput, (cents(total) - cents(discount)) / 100);
                }
            } else if (total !== null) {
                warning = `A soma dos itens antes dos descontos (${money.format(sum / 100)}) difere do valor total (${money.format(total)}). Corrija os valores para salvar.`;
            }
        }
        const total = amount(totalInput);
        const paid = amount(paidInput);
        if (complete && !warning && total !== null && paid !== null) calculated(discountInput, (cents(total) - cents(paid)) / 100);
        const discount = amount(discountInput);
        if (total !== null && discount !== null) {
            if (cents(discount) > cents(total) || cents(discount) + 1 < discounts) {
                warning ||= 'O desconto total deve incluir os descontos dos itens e não superar o valor total.';
            } else if (paid !== null && Math.abs(cents(total) - cents(discount) - cents(paid)) > 1) {
                warning ||= 'O valor a pagar deve ser o valor total menos o desconto total. Corrija os valores para salvar.';
            }
        }
        totalsMismatch = Boolean(warning);
        notice('#items-warning', warning, 'warning');
        notice('#calculation-notice', discount !== null && cents(discount) > discounts + 1
            ? 'Há desconto no total que não foi identificado nos itens. Confira as linhas de desconto no comprovante. Os valores não serão distribuídos entre os produtos.'
            : form.querySelector('[data-calculated]')
            ? 'Campos em azul foram calculados a partir dos valores disponíveis. Confira os descontos e o valor a pagar com o comprovante; você pode editar as sugestões.' : '', 'info');
        updateRegistrationControls();
    }

    form.addEventListener('input', event => {
        if (!event.target.matches('input')) return;
        delete event.target.dataset.calculated;
        if (event.target.id === 'exp-desconto_total') {
            $('#exp-valor_pago').value = '';
            delete $('#exp-valor_pago').dataset.calculated;
        }
        if (event.target.dataset.itemField === 'desconto') {
            const net = event.target.closest('tr').querySelector('[data-item-field="preco_total"]');
            net.value = '';
            delete net.dataset.calculated;
        }
        if (event.target.dataset.itemField === 'preco_total') {
            const discount = event.target.closest('tr').querySelector('[data-item-field="desconto"]');
            discount.value = '';
            delete discount.dataset.calculated;
        }
        dirty = true; inputError(event.target, ''); markMissing(event.target);
        if (event.target.id === 'exp-cnpj') scheduleRegistration();
        updateTotals();
    });

    form.addEventListener('focusin', event => {
        const input = event.target;
        if (!input.dataset.money) return;
        const value = monetaryValue(input);
        if (value !== null) input.value = new Intl.NumberFormat('pt-BR', {
            useGrouping: false, minimumFractionDigits: 2,
            maximumFractionDigits: Number(input.dataset.money),
        }).format(value);
    });

    form.addEventListener('focusout', event => {
        const input = event.target;
        if (!input.dataset.money) return;
        const value = monetaryValue(input);
        if (value !== null) setValue(input, value);
        inputError(input, input.value.trim() && value === null ? 'Informe um valor válido, como R$ 1.234,56.' : '');
        markMissing(input);
    });

    function validate() {
        updateTotals();
        if (cnpjPending || !storeReady()) {
            inputError($('#exp-cnpj'), cnpjPending ? 'Aguarde a consulta do CNPJ.' : 'Consulte um CNPJ válido antes de salvar.');
            $('#exp-cnpj').focus();
            return false;
        }
        let first = null;
        form.querySelectorAll('input').forEach(input => {
            inputError(input, '');
            if (!input.checkValidity() || (input.required && !input.value.trim())
                || (input.dataset.money && input.value.trim() && monetaryValue(input) === null)) {
                inputError(input, input.validity.rangeUnderflow ? 'Informe um valor permitido, sem números negativos.' : 'Preencha este campo com um valor válido.');
                first ||= input;
            }
        });
        if (!itemBody.children.length) { $('#items-empty').hidden = false; $('#item-add').focus(); return false; }
        first?.focus();
        if (first) return false;
        if (totalsMismatch) {
            $('#items-warning').scrollIntoView({ block: 'center' });
            $('#exp-valor_total').focus();
            return false;
        }
        return true;
    }

    function showServerErrors(error) {
        for (const entry of error.fields || []) {
            let input;
            const parts = entry.campo.split('.');
            if (parts[0] === 'itens') {
                input = itemBody.children[Number(parts[1])]?.querySelector(parts[2] ? `[data-item-field="${parts[2]}"]` : '[data-item-field="preco_total"]');
                if (!input) notice('#items-warning', entry.mensagem.replace(/^Value error, /, ''), 'warning');
            }
            else if (parts[0] === 'estabelecimento') input = $(`#exp-${parts[1] === 'nome' ? 'estabelecimento' : parts[1]}`);
            else input = fields.find(el => el.dataset.field === entry.campo);
            if (input) inputError(input, entry.mensagem.replace(/^Value error, /, ''));
        }
        form.querySelector('[aria-invalid="true"]')?.focus();
    }

    form.addEventListener('submit', async event => {
        event.preventDefault();
        if (busy || (!file && editId === null) || !validate()) return;
        notice('#expense-notice', '');
        const data = {};
        fields.forEach(input => { data[input.dataset.field] = serializedValue(input); });
        data.estabelecimento = { cnpj: currentCnpj() };
        delete data.cnpj;
        data.itens = serializeItems();
        let path = '/api/despesas';
        let options;
        if (editId === null) {
            const body = new FormData(); body.append('imagem', file); body.append('dados', JSON.stringify(data));
            options = { method: 'POST', body };
        } else {
            path += `/${editId}`;
            options = { method: 'PUT', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data) };
        }
        setBusy(true, true);
        try {
            const result = await request(path, options);
            dirty = false;
            setBusy(false, true);
            clearFile();
            window.location.hash = `despesa/${result.id}`;
            savedMessage = result.mensagem;
        } catch (error) {
            notice('#expense-notice', error.message || 'Não foi possível salvar. Tente novamente.');
            if ((error.fields || []).some(entry => entry.campo === 'estabelecimento.cnpj')) {
                resetRegistration();
                applyRegistration({ status: 'indisponivel' });
            }
            setBusy(false, true); showServerErrors(error);
        }
    });

    function formattedDate(value) {
        return new Intl.DateTimeFormat('pt-BR').format(new Date(`${value}T12:00:00`));
    }

    async function loadHistory(more = false) {
        if (more && historyLoading) return;
        const version = ++historyVersion;
        historyLoading = true;
        if (!more) { historyOffset = 0; $('#history-list').replaceChildren(); }
        $('#history-more').disabled = true; $('#history-retry').hidden = true;
        notice('#history-notice', 'Carregando despesas…', 'info');
        try {
            const result = await request(`/api/despesas?offset=${historyOffset}`);
            if (version !== historyVersion) return;
            result.despesas.forEach(expense => {
                const row = document.createElement('a'); row.className = 'history-row'; row.href = `#despesa/${expense.id}`;
                const store = document.createElement('div'); store.className = 'history-store';
                const name = document.createElement('strong'); name.textContent = expense.estabelecimento.nome;
                const date = document.createElement('small'); date.textContent = `${formattedDate(expense.data_despesa)} · ${expense.quantidade_itens} item(ns)`;
                store.append(name, date);
                const value = document.createElement('span'); value.className = 'history-value'; value.textContent = money.format(expense.valor_total);
                row.append(store, value); $('#history-list').append(row);
            });
            historyOffset += result.despesas.length;
            if (!historyOffset) {
                const empty = document.createElement('p'); empty.className = 'history-empty'; empty.textContent = 'Seu histórico começa com o primeiro comprovante. Clique em Nova despesa para começar.'; $('#history-list').append(empty);
            }
            $('#history-more').hidden = !result.tem_mais; notice('#history-notice', '');
        } catch (error) { if (version === historyVersion) { notice('#history-notice', error.message); $('#history-retry').hidden = false; } }
        finally { if (version === historyVersion) { historyLoading = false; $('#history-more').disabled = false; } }
    }

    $('#history-more').addEventListener('click', () => loadHistory(true));
    $('#history-retry').addEventListener('click', () => loadHistory());

    async function loadDetail(id) {
        detailId = id;
        $('#detail-content').replaceChildren(); $('#expense-delete').disabled = true; $('#expense-edit').hidden = true;
        try {
            const expense = await request(`/api/despesas/${id}`);
            if (detailId !== id || currentRoute !== `#despesa/${id}`) return;
            const grid = document.createElement('dl'); grid.className = 'detail-grid';
            const values = [
                ['Estabelecimento', expense.estabelecimento.nome], ['CNPJ', expense.estabelecimento.cnpj], ['Endereço', expense.estabelecimento.endereco],
                ['Data', formattedDate(expense.data_despesa)], ['Hora', expense.hora_despesa], ['Total antes dos descontos', money.format(expense.valor_total)],
                ['Desconto total', expense.desconto_total === null ? null : money.format(expense.desconto_total)], ['Valor a pagar / pago', expense.valor_pago === null ? null : money.format(expense.valor_pago)],
                ['Pagamento', expense.forma_pagamento], ['Documento', expense.documento_tipo], ['Chave de acesso', expense.documento_chave],
            ];
            values.forEach(([label, value]) => { const div = document.createElement('div'); const dt = document.createElement('dt'); dt.textContent = label; const dd = document.createElement('dd'); dd.textContent = value ?? 'Não informado'; div.append(dt, dd); grid.append(div); });
            const scroll = document.createElement('div'); scroll.className = 'expense-table-scroll'; scroll.tabIndex = 0;
            const table = document.createElement('table'); table.className = 'expense-table';
            const head = table.createTHead().insertRow();
            ['Código', 'Descrição', 'Quantidade', 'Unidade', 'Preço unitário', 'Desconto', 'Total após desconto'].forEach(label => { const th = document.createElement('th'); th.textContent = label; head.append(th); });
            const body = table.createTBody();
            expense.itens.forEach(item => {
                const row = body.insertRow();
                [ item.codigo, item.descricao, item.quantidade, item.unidade,
                    money.format(item.preco_unitario), item.desconto === null ? null : money.format(item.desconto), item.preco_total === null ? null : money.format(item.preco_total),
                ].forEach(value => { row.insertCell().textContent = value ?? '—'; });
                if (item.descricao_original !== item.descricao) { const original = document.createElement('small'); original.className = 'original-description'; original.textContent = `Na leitura: ${item.descricao_original}`; row.cells[1].append(original); }
            });
            scroll.append(table);
            const imageButton = document.createElement('button');
            imageButton.type = 'button'; imageButton.className = 'receipt-view';
            imageButton.textContent = 'Clique aqui para ver a imagem do comprovante enviado';
            imageButton.setAttribute('aria-haspopup', 'dialog');
            imageButton.setAttribute('aria-controls', 'receipt-modal');
            imageButton.addEventListener('click', () => openReceipt(receiptUrl(id), imageButton));
            $('#detail-content').append(grid, scroll, imageButton); $('#expense-delete').disabled = false;
            $('#expense-edit').href = `#despesa/${id}/editar`; $('#expense-edit').hidden = false;
        } catch (error) { if (detailId === id) notice('#detail-notice', error.message); }
    }

    async function loadEdit(id) {
        clearFile();
        setEditMode(id);
        notice('#expense-notice', 'Carregando a despesa…', 'info');
        try {
            const expense = await request(`/api/despesas/${id}`);
            if (editId !== id) return;
            savedStore = expense.estabelecimento;
            fields.forEach(input => {
                setValue(input, input.dataset.field === 'cnpj' ? savedStore.cnpj : expense[input.dataset.field]);
                inputError(input, ''); markMissing(input);
            });
            expense.itens.forEach(item => addItem(item, false));
            notice('#expense-notice', '');
            form.hidden = false;
            updateTotals();
            // Preenche o endereço pelo cadastro; se a consulta falhar, o estabelecimento salvo é mantido.
            scheduleRegistration(true);
        } catch (error) { if (editId === id) notice('#expense-notice', error.message); }
    }

    $('#edit-cancel').addEventListener('click', () => { window.location.hash = `despesa/${editId}`; });

    $('#expense-delete').addEventListener('click', async () => {
        if (!detailId || !window.confirm('Excluir esta despesa, seus itens e a imagem do comprovante?')) return;
        $('#expense-delete').disabled = true;
        try {
            await request(`/api/despesas/${detailId}`, { method: 'DELETE' });
            window.location.hash = 'despesas';
        } catch (error) { notice('#detail-notice', error.message); $('#expense-delete').disabled = false; }
    });

    function route() {
        if (receiptModal.open) receiptModal.close();
        const hash = window.location.hash || '#despesas';
        if (busy && hash !== currentRoute) { history.replaceState(null, '', currentRoute); return; }
        const create = hash === '#nova-despesa';
        const detail = hash.match(/^#despesa\/(\d+)$/);
        const edit = hash.match(/^#despesa\/(\d+)\/editar$/);
        const editTarget = edit ? Number(edit[1]) : null;
        if (editId !== null && editTarget !== editId) {
            if (dirty && !window.confirm('Descartar as alterações não salvas desta despesa?')) { history.replaceState(null, '', currentRoute); return; }
            clearFile();
        } else if (edit && editId === null && file && !window.confirm('Descartar a nova despesa em andamento para editar esta despesa?')) {
            history.replaceState(null, '', currentRoute); return;
        }
        currentRoute = hash;
        $('#expense-create').hidden = !create && !edit;
        $('#expense-history').hidden = create || Boolean(detail) || Boolean(edit);
        $('.dashboard-welcome').hidden = create || Boolean(detail) || Boolean(edit);
        $('#expense-detail').hidden = !detail;
        if (create) { $('#create-title').focus(); }
        else if (edit) { if (editId !== editTarget) loadEdit(editTarget); $('#create-title').focus(); }
        else if (detail) { notice('#detail-notice', savedMessage, 'success'); savedMessage = ''; loadDetail(Number(detail[1])); $('#detail-title').focus(); }
        else { detailId = null; loadHistory(); }
        window.scrollTo(0, 0);
    }
    window.addEventListener('hashchange', route);
    window.addEventListener('beforeunload', event => { if (dirty || busy) { event.preventDefault(); event.returnValue = ''; } });
    route();
})();
