# APIs municipales

Conectores para portales Open Data municipales del intento 3.

Cada script guarda datos raw por municipio en:

```text
api_clients/intento 3/data_lake/bronze/municipios/<ciudad>/
```

La estructura general recomendada de Bronze queda documentada en `../README.md`.

## Ejecucion individual

```powershell
python "api_clients\intento 3\APIS\municipios\api_barcelona.py"
python "api_clients\intento 3\APIS\municipios\api_madrid.py"
python "api_clients\intento 3\APIS\municipios\api_valencia.py"
python "api_clients\intento 3\APIS\municipios\api_malaga.py"
python "api_clients\intento 3\APIS\municipios\api_zaragoza.py"
python "api_clients\intento 3\APIS\municipios\api_bilbao.py"
python "api_clients\intento 3\APIS\municipios\api_sevilla.py"
```

## Ejecucion por lote

```powershell
python "api_clients\intento 3\APIS\municipios\run_municipios.py" barcelona madrid
```

Sin argumentos ejecuta todas las ciudades configuradas.

