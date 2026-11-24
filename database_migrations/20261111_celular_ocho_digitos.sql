BEGIN;

ALTER TABLE public.persona
    DROP CONSTRAINT IF EXISTS ck_persona_celular;
ALTER TABLE public.persona
    ADD CONSTRAINT ck_persona_celular
    CHECK (celular IS NULL OR celular ~ '^\+591[0-9]{8}$');

ALTER TABLE public.denunciante_externo
    DROP CONSTRAINT IF EXISTS ck_ext_celular;
ALTER TABLE public.denunciante_externo
    ADD CONSTRAINT ck_ext_celular
    CHECK (celular IS NULL OR celular ~ '^\+591[0-9]{8}$');

COMMIT;
