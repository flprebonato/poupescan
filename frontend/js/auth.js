const authBox = document.querySelector('#auth-box');
const feedbackModal = document.querySelector('#feedback-modal');
const feedbackCard = document.querySelector('#feedback-card');
const feedbackTitle = document.querySelector('#feedback-title');
const feedbackText = document.querySelector('#feedback-text');
const feedbackButton = document.querySelector('#feedback-button');
const feedbackCancel = document.querySelector('#feedback-cancel');
const feedbackClose = document.querySelector('#feedback-close');
const isLiveServer = window.location.pathname.includes('/frontend/');
const backendHost = window.location.hostname === 'localhost' ? 'localhost' : '127.0.0.1';
const apiBaseUrl = isLiveServer ? `http://${backendHost}:8000` : '';
let elementoAntesDaModal = null;
let confirmarModal = fecharModal;
let cancelarModal = fecharModal;

async function lerRespostaJson(response) {
    const contentType = response.headers.get('content-type') || '';

    if (!contentType.includes('application/json')) {
        await response.text();
        const mensagem = response.status >= 500
            ? 'O servidor encontrou um problema. Tente novamente em instantes.'
            : 'O servidor enviou uma resposta inesperada. Tente novamente.';
        throw new Error(mensagem);
    }

    try {
        return await response.json();
    } catch {
        throw new Error('O servidor enviou uma resposta inválida. Tente novamente.');
    }
}

function mostrarCadastro() {
    authBox.classList.add('show-register');
}

function mostrarLogin() {
    authBox.classList.remove('show-register');
}

async function carregarCaptcha() {
    const token = document.querySelector('#captcha-token');
    const resposta = document.querySelector('#captcha-answer');

    resposta.placeholder = 'Carregando verificação...';
    token.value = '';
    resposta.value = '';

    try {
        const response = await fetch(`${apiBaseUrl}/api/auth/captcha`, {
            credentials: 'include',
        });
        const captcha = await lerRespostaJson(response);
        if (!response.ok) throw new Error('Não foi possível carregar a verificação.');
        resposta.placeholder = captcha.pergunta;
        token.value = captcha.token;
    } catch {
        resposta.placeholder = 'Não foi possível carregar a verificação.';
    }
}

document.querySelector('#show-register').addEventListener('click', mostrarCadastro);
document.querySelector('#show-login').addEventListener('click', mostrarLogin);
document.querySelector('#mobile-show-register').addEventListener('click', mostrarCadastro);
document.querySelector('#mobile-show-login').addEventListener('click', mostrarLogin);
document.querySelector('#captcha-refresh').addEventListener('click', carregarCaptcha);

document.querySelectorAll('.password-toggle').forEach((button) => {
    button.addEventListener('click', () => {
        const input = document.querySelector(`#${button.dataset.passwordTarget}`);
        const deveMostrar = input.type === 'password';

        input.type = deveMostrar ? 'text' : 'password';
        button.classList.toggle('is-visible', deveMostrar);
        button.setAttribute('aria-pressed', String(deveMostrar));
        button.setAttribute('aria-label', deveMostrar ? 'Ocultar senha' : 'Mostrar senha');
    });
});

function mensagemValidacao(input) {
    if (input.validity.valueMissing) {
        const mensagens = {
            email: 'Digite seu e-mail.',
            senha: 'Digite sua senha.',
            nome: 'Digite seu nome.',
            captcha_resposta: 'Resolva a verificação.',
        };
        return mensagens[input.name] || 'Preencha este campo.';
    }

    if (input.validity.typeMismatch) return 'Digite um e-mail válido.';
    if (input.validity.tooShort) return `Use pelo menos ${input.minLength} caracteres.`;
    if (input.validity.rangeUnderflow || input.validity.rangeOverflow) {
        return 'Digite um valor dentro do intervalo permitido.';
    }

    return 'Verifique o valor informado.';
}

function atualizarValidacao(input) {
    const group = input.closest('.input-group');
    const error = document.querySelector(`#${input.id}-error`);
    const invalido = !input.validity.valid;

    group.classList.toggle('has-error', invalido);
    input.setAttribute('aria-invalid', String(invalido));
    error.textContent = invalido ? mensagemValidacao(input) : '';
    error.hidden = !invalido;
    return !invalido;
}

function limparValidacao(form) {
    form.querySelectorAll('input:not([type="hidden"])').forEach((input) => {
        input.closest('.input-group').classList.remove('has-error');
        input.setAttribute('aria-invalid', 'false');
        const error = document.querySelector(`#${input.id}-error`);
        error.textContent = '';
        error.hidden = true;
    });
}

function validarFormulario(form) {
    const inputs = [...form.querySelectorAll('input:not([type="hidden"])')];
    let primeiroInvalido = null;

    inputs.forEach((input) => {
        if (!atualizarValidacao(input) && primeiroInvalido === null) primeiroInvalido = input;
    });

    primeiroInvalido?.focus();
    return !primeiroInvalido;
}

document.querySelectorAll('.form-panel form').forEach((form) => {
    form.noValidate = true;

    form.querySelectorAll('input:not([type="hidden"])').forEach((input) => {
        const error = document.createElement('span');
        error.className = 'field-error';
        error.id = `${input.id}-error`;
        error.setAttribute('aria-live', 'polite');
        error.hidden = true;
        input.closest('.input-group').insertAdjacentElement('afterend', error);
        input.setAttribute('aria-describedby', error.id);
        input.setAttribute('aria-invalid', 'false');

        input.addEventListener('blur', () => {
            if (input.value || input.getAttribute('aria-invalid') === 'true') atualizarValidacao(input);
        });
        input.addEventListener('input', () => {
            if (input.getAttribute('aria-invalid') === 'true') atualizarValidacao(input);
        });
    });

    form.addEventListener('reset', () => limparValidacao(form));
});

function ocultarSenha(form) {
    const input = form.querySelector('input[name="senha"]');
    const button = form.querySelector('.password-toggle');

    input.type = 'password';
    button.classList.remove('is-visible');
    button.setAttribute('aria-pressed', 'false');
    button.setAttribute('aria-label', 'Mostrar senha');
}

function fecharModal() {
    feedbackModal.hidden = true;
    document.body.classList.remove('modal-open');
    elementoAntesDaModal?.focus();
}

function mostrarMensagem(texto, tipo, elementoRetorno = document.activeElement) {
    feedbackTitle.textContent = tipo === 'success' ? 'Tudo certo!' : 'Não foi possível continuar';
    feedbackText.textContent = texto;
    feedbackCard.className = `feedback-card ${tipo}`;
    feedbackButton.textContent = 'Entendi';
    feedbackCancel.hidden = true;
    elementoAntesDaModal = elementoRetorno;
    confirmarModal = fecharModal;
    cancelarModal = fecharModal;
    feedbackModal.hidden = false;
    document.body.classList.add('modal-open');
    feedbackButton.focus();
}

feedbackButton.addEventListener('click', () => confirmarModal());
feedbackCancel.addEventListener('click', () => cancelarModal());
feedbackClose.addEventListener('click', () => cancelarModal());
feedbackModal.addEventListener('click', (event) => {
    if (event.target === feedbackModal) cancelarModal();
});
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape' && !feedbackModal.hidden) cancelarModal();
});

function mostrarSucessoCadastro(form, email) {
    mostrarMensagem('Deseja acessar o sistema agora?', 'success');
    feedbackTitle.textContent = 'Conta criada com sucesso!';
    feedbackButton.textContent = 'Acessar agora';
    feedbackCancel.hidden = false;

    confirmarModal = () => {
        window.location.href = `${apiBaseUrl}/app`;
    };

    cancelarModal = async () => {
        await fetch(`${apiBaseUrl}/api/auth/logout`, {
            method: 'POST',
            credentials: 'include',
        });

        fecharModal();
        form.reset();
        ocultarSenha(form);
        mostrarLogin();
        carregarCaptcha();

        const loginEmail = document.querySelector('#login-email');
        loginEmail.value = email;
        loginEmail.focus();
    };
}

async function enviarFormulario(form, url) {
    const button = form.querySelector('.primary-button');
    const textoOriginal = button.textContent;
    const dados = Object.fromEntries(new FormData(form));

    button.disabled = true;
    button.textContent = 'Aguarde...';
    if (!feedbackModal.hidden) fecharModal();

    try {
        const response = await fetch(`${apiBaseUrl}${url}`, {
            method: 'POST',
            credentials: 'include',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(dados),
        });

        const resultado = await lerRespostaJson(response);

        if (!response.ok) {
            const erro = typeof resultado.detail === 'string'
                ? resultado.detail
                : 'Verifique os dados informados.';
            throw new Error(erro);
        }

        if (form.id === 'login-form') {
            window.location.href = `${apiBaseUrl}/app`;
            return;
        }

        mostrarSucessoCadastro(form, dados.email);
    } catch (error) {
        let campoParaFocar = button;

        if (form.id === 'login-form') {
            form.reset();
            ocultarSenha(form);
            campoParaFocar = form.querySelector('input');
        }

        const mensagem = error instanceof TypeError
            ? 'Não foi possível conectar ao servidor. Verifique se a aplicação está em execução.'
            : error.message;
        mostrarMensagem(mensagem, 'error', campoParaFocar);
        button.disabled = false;
        button.textContent = textoOriginal;
        if (form.id === 'register-form') carregarCaptcha();
    }
}

document.querySelector('#login-form').addEventListener('submit', (event) => {
    event.preventDefault();
    if (!validarFormulario(event.currentTarget)) return;
    enviarFormulario(event.currentTarget, '/api/auth/login');
});

document.querySelector('#register-form').addEventListener('submit', (event) => {
    event.preventDefault();
    if (!validarFormulario(event.currentTarget)) return;
    enviarFormulario(event.currentTarget, '/api/auth/cadastro');
});

carregarCaptcha();
