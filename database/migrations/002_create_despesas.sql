-- Despesas confirmadas e seus cadastros. A imagem é armazenada na própria despesa.

BEGIN;

CREATE TABLE IF NOT EXISTS produtos (
	id SERIAL NOT NULL, 
	nome VARCHAR(500) NOT NULL, 
	gtin VARCHAR(14), 
	PRIMARY KEY (id), 
	UNIQUE (gtin)
);

CREATE TABLE IF NOT EXISTS estabelecimentos (
	id SERIAL NOT NULL, 
	usuario_id INTEGER NOT NULL, 
	identidade VARCHAR(64) NOT NULL, 
	nome VARCHAR(255) NOT NULL, 
	cnpj VARCHAR(14), 
	endereco VARCHAR(500), 
	PRIMARY KEY (id), 
	CONSTRAINT uq_estabelecimento_usuario UNIQUE (usuario_id, identidade), 
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE
);

CREATE INDEX IF NOT EXISTS ix_estabelecimentos_usuario_id ON estabelecimentos (usuario_id);

CREATE TABLE IF NOT EXISTS despesas (
	id SERIAL NOT NULL, 
	usuario_id INTEGER NOT NULL, 
	estabelecimento_id INTEGER NOT NULL, 
	data_despesa DATE NOT NULL, 
	hora_despesa TIME WITHOUT TIME ZONE, 
	valor_total NUMERIC(14, 2) NOT NULL, 
	desconto_total NUMERIC(14, 2), 
	valor_pago NUMERIC(14, 2), 
	quantidade_itens INTEGER NOT NULL, 
	forma_pagamento VARCHAR(80), 
	documento_tipo VARCHAR(50), 
	documento_chave VARCHAR(44), 
	qrcode_identificado BOOLEAN NOT NULL, 
	arquivo_nome VARCHAR(255) NOT NULL, 
	arquivo_mime VARCHAR(20) NOT NULL, 
	arquivo_tamanho INTEGER NOT NULL, 
	arquivo_dados BYTEA NOT NULL, 
	criado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_despesa_usuario_chave UNIQUE (usuario_id, documento_chave), 
	CONSTRAINT ck_despesa_valores CHECK (valor_total >= 0 AND (desconto_total IS NULL OR desconto_total >= 0) AND (valor_pago IS NULL OR valor_pago >= 0)), 
	CONSTRAINT ck_despesa_itens CHECK (quantidade_itens > 0), 
	CONSTRAINT ck_despesa_arquivo CHECK (arquivo_tamanho > 0 AND arquivo_tamanho <= 10485760), 
	FOREIGN KEY(usuario_id) REFERENCES usuarios (id) ON DELETE CASCADE, 
	FOREIGN KEY(estabelecimento_id) REFERENCES estabelecimentos (id)
);

CREATE INDEX IF NOT EXISTS ix_despesas_usuario_id ON despesas (usuario_id);

CREATE INDEX IF NOT EXISTS ix_despesas_data_despesa ON despesas (data_despesa);

CREATE TABLE IF NOT EXISTS produtos_estabelecimento (
	id SERIAL NOT NULL, 
	estabelecimento_id INTEGER NOT NULL, 
	produto_id INTEGER NOT NULL, 
	codigo VARCHAR(80) NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT uq_produto_codigo_local UNIQUE (estabelecimento_id, codigo), 
	FOREIGN KEY(estabelecimento_id) REFERENCES estabelecimentos (id) ON DELETE CASCADE, 
	FOREIGN KEY(produto_id) REFERENCES produtos (id)
);

CREATE TABLE IF NOT EXISTS itens_despesa (
	id SERIAL NOT NULL, 
	despesa_id INTEGER NOT NULL, 
	produto_id INTEGER NOT NULL, 
	codigo VARCHAR(80), 
	descricao_original VARCHAR(500) NOT NULL, 
	descricao VARCHAR(500) NOT NULL, 
	apresentacao VARCHAR(100), 
	quantidade NUMERIC(14, 4) NOT NULL, 
	unidade VARCHAR(20), 
	preco_unitario NUMERIC(14, 4) NOT NULL, 
	desconto NUMERIC(14, 2), 
	preco_total NUMERIC(14, 2), 
	criado_em TIMESTAMP WITH TIME ZONE DEFAULT now() NOT NULL, 
	PRIMARY KEY (id), 
	CONSTRAINT ck_item_quantidade CHECK (quantidade > 0), 
	CONSTRAINT ck_item_valores CHECK (preco_unitario >= 0 AND (desconto IS NULL OR desconto >= 0) AND (preco_total IS NULL OR preco_total >= 0)), 
	FOREIGN KEY(despesa_id) REFERENCES despesas (id) ON DELETE CASCADE, 
	FOREIGN KEY(produto_id) REFERENCES produtos (id)
);

CREATE INDEX IF NOT EXISTS ix_itens_despesa_despesa_id ON itens_despesa (despesa_id);

COMMIT;
