BEGIN;

ALTER TABLE public.rol
    ADD COLUMN IF NOT EXISTS activo boolean NOT NULL DEFAULT true;

LOCK TABLE public.rol IN ACCESS EXCLUSIVE MODE;
LOCK TABLE public.usuario_rol IN SHARE ROW EXCLUSIVE MODE;

ALTER TABLE public.usuario_rol
    DROP CONSTRAINT IF EXISTS usuario_rol_id_rol_fkey;

DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1
        FROM public.rol
        WHERE codigo = 'ADMINISTRADOR'
    ) THEN
        RAISE EXCEPTION 'No existe el rol ADMINISTRADOR en public.rol.';
    END IF;
END
$$;

CREATE TEMPORARY TABLE rol_id_remap ON COMMIT DROP AS
WITH administrador AS (
    SELECT id_rol
    FROM public.rol
    WHERE codigo = 'ADMINISTRADOR'
)
SELECT
    rol.id_rol AS old_id,
    (-(rol.id_rol::integer + 1000))::smallint AS temporary_id,
    CASE
        WHEN rol.codigo = 'ADMINISTRADOR' THEN 1
        WHEN rol.id_rol = 1 THEN administrador.id_rol
        ELSE rol.id_rol
    END::smallint AS final_id,
    rol.codigo,
    rol.nombre,
    rol.descripcion,
    rol.es_autoridad,
    rol.activo
FROM public.rol AS rol
CROSS JOIN administrador
WHERE rol.codigo = 'ADMINISTRADOR' OR rol.id_rol = 1;

INSERT INTO public.rol (
    id_rol,
    codigo,
    nombre,
    descripcion,
    es_autoridad,
    activo
)
SELECT
    temporary_id,
    '__MIGRACION_' || old_id::text,
    nombre,
    descripcion,
    es_autoridad,
    activo
FROM rol_id_remap
WHERE old_id <> final_id;

UPDATE public.usuario_rol AS usuario_rol
SET id_rol = rol_id_remap.temporary_id
FROM rol_id_remap
WHERE usuario_rol.id_rol = rol_id_remap.old_id
  AND rol_id_remap.old_id <> rol_id_remap.final_id;

DELETE FROM public.rol AS rol
USING rol_id_remap
WHERE rol.id_rol = rol_id_remap.old_id
  AND rol_id_remap.old_id <> rol_id_remap.final_id;

UPDATE public.rol AS rol
SET
    id_rol = rol_id_remap.final_id,
    codigo = rol_id_remap.codigo
FROM rol_id_remap
WHERE rol.id_rol = rol_id_remap.temporary_id;

UPDATE public.usuario_rol AS usuario_rol
SET id_rol = rol_id_remap.final_id
FROM rol_id_remap
WHERE usuario_rol.id_rol = rol_id_remap.temporary_id;

ALTER TABLE public.usuario_rol
    ADD CONSTRAINT usuario_rol_id_rol_fkey
    FOREIGN KEY (id_rol)
    REFERENCES public.rol(id_rol);

SELECT setval(
    pg_get_serial_sequence('public.rol', 'id_rol'),
    COALESCE((SELECT MAX(id_rol) FROM public.rol), 1),
    true
);

COMMIT;
