# API Athena de ISEU+

Lambda sin dependencias externas que expone operaciones cerradas sobre la capa
Gold de Athena.

- `GET /health`: disponibilidad, sin API key.
- `GET /dashboard`: payload completo del dashboard, requiere API key.
- `GET /catalog`: resumen de fuentes y variables, requiere API key.
- `POST /indicators`: búsqueda con filtros permitidos, requiere API key.
- `POST /sql`: ejecuta SQL generado por el modelo después de validarlo, requiere
  API key.

`/indicators` acepta listas `terms`, `cities`, `variables`, `categories` y
`sources`, además de `limit` entre 1 y 100. La API no acepta SQL arbitrario.

`/sql` admite exclusivamente una sentencia `SELECT` sobre la tabla lógica
`indicators`, sin comentarios ni sentencias múltiples, y fuerza un máximo de
100 filas. El backend sustituye la tabla lógica por la tabla Glue real.

La API key se utiliza para cuota y control de consumo en API Gateway. No debe
incluirse en JavaScript del navegador; Vercel la conserva como variable de
entorno y llama a AWS desde sus funciones Python.
