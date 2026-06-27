# LMlocal

Conexion local entre la web `pag_web` y LM Studio.

## Uso

1. Abre LM Studio y deja cargado un modelo instruct. Recomendado para probar: `qwen/qwen3-14b` si tu equipo lo soporta, o `qwen/qwen3-8b` si necesitas algo mas ligero.
2. Comprueba que el servidor local de LM Studio esta activo en `http://127.0.0.1:1234`.
3. Desde la raiz del proyecto ejecuta:

```powershell
python pag_web\LMlocal\server.py
```

4. Abre la web en:

```text
http://127.0.0.1:5500
```

Tambien puedes abrir los HTML con Live Preview en `http://127.0.0.1:3000`.
Cuando detecta un entorno local, el frontend consulta automaticamente la API en
`http://127.0.0.1:5500`; por tanto, `server.py` debe permanecer iniciado.

## Archivos

- `system_prompt.txt`: prompt de sistema del asistente ISEU.
- `config.json`: URL de LM Studio, modelo y parametros.
- `server.py`: servidor local que sirve la web, expone `/api/chat` y consulta `pag_web/Procesos/Datasets/iseu_datos.sqlite` para preparar el contexto del modelo.

Flujo local:

```text
HTML -> /api/chat -> SQLite -> LM Studio -> respuesta con trazabilidad
```

Esta estructura esta pensada para que despues puedas cambiar el proveedor local por AWS sin modificar la interfaz principal de la web.
