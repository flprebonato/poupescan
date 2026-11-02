-- Registra a última correção da despesa. A data de criação não é alterada.

BEGIN;

-- Despesas já cadastradas começam com a data de atualização igual à de criação.
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM information_schema.columns
        WHERE table_schema = current_schema() AND table_name = 'despesas' AND column_name = 'atualizado_em'
    ) THEN
        ALTER TABLE despesas ADD COLUMN atualizado_em TIMESTAMPTZ;
        UPDATE despesas SET atualizado_em = criado_em;
        ALTER TABLE despesas
            ALTER COLUMN atualizado_em SET DEFAULT CURRENT_TIMESTAMP,
            ALTER COLUMN atualizado_em SET NOT NULL;
    END IF;
END $$;

CREATE OR REPLACE FUNCTION atualizar_data_despesa()
RETURNS TRIGGER AS $$
BEGIN
    NEW.atualizado_em = CURRENT_TIMESTAMP;
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trigger_atualizar_despesa ON despesas;

CREATE TRIGGER trigger_atualizar_despesa
BEFORE UPDATE ON despesas
FOR EACH ROW
EXECUTE FUNCTION atualizar_data_despesa();

COMMIT;
