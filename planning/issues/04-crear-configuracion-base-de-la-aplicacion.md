# Crear configuración base de la aplicación

Definir una capa de configuración simple y mantenible.

## Alcance
- Rutas locales.
- Parámetros generales.
- Configuración por defecto.
- Posibilidad de sobrescribir configuración sin versionar secretos.

## Criterios de aceptación
- La configuración está desacoplada del código de negocio.
- Los valores sensibles no se versionan.
- Existe documentación de uso.
- La aplicación puede cargar configuración por defecto.
