const isLiveServer = window.location.pathname.includes('/frontend/');
const backendHost = window.location.hostname === 'localhost' ? 'localhost' : '127.0.0.1';
const apiBaseUrl = isLiveServer ? `http://${backendHost}:8000` : '';
const settingsModal = document.querySelector('#settings-modal');
const settingsForm = document.querySelector('#settings-form');
const settingsNotice = document.querySelector('#settings-notice');
let usuarioAtual = null;
let elementoAntesDoModal = null;

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
    if (!senhaAtual.value) invalidar(senhaAtual, 'Digite sua senha atual para salvar.');

    primeiroInvalido?.focus();
    return !primeiroInvalido;
}

function abrirConfiguracoes() {
    if (!usuarioAtual) return;

    elementoAntesDoModal = document.activeElement;
    settingsForm.reset();
    limparErros();
    document.querySelector('#settings-name').value = usuarioAtual.nome;
    document.querySelector('#settings-email').value = usuarioAtual.email;
    settingsModal.hidden = false;
    document.body.classList.add('settings-open');
    document.querySelector('#settings-name').focus();
}

function fecharConfiguracoes() {
    settingsModal.hidden = true;
    document.body.classList.remove('settings-open');
    elementoAntesDoModal?.focus();
}

document.querySelector('#settings-button').addEventListener('click', abrirConfiguracoes);
document.querySelector('#settings-close').addEventListener('click', fecharConfiguracoes);
document.querySelector('#settings-cancel').addEventListener('click', fecharConfiguracoes);
settingsModal.addEventListener('click', (event) => {
    if (event.target === settingsModal) fecharConfiguracoes();
});
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !settingsModal.hidden) fecharConfiguracoes();
});

settingsForm.querySelectorAll('input').forEach((input) => {
    input.addEventListener('input', () => limparErro(input));
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
        mostrarAviso(resultado.mensagem, 'success');
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
