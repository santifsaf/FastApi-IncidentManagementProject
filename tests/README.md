# Tests

La suite esta separada por nivel de responsabilidad:

- `test_*_rules.py`: prueban reglas puras, sin base de datos ni FastAPI.
- `test_*_service.py`: prueban casos de uso, validaciones de negocio, auditoria y commit/rollback.
- `test_*_routes.py`: prueban endpoints con `TestClient`: rutas reales, dependencias, permisos HTTP, status codes y serializacion JSON.
- `conftest.py`: fixtures compartidas para tests HTTP.

La idea es no duplicar todo en todos los niveles. Si una regla ya esta cubierta
en un service, el test HTTP solo valida que el endpoint conecte bien esa regla
con FastAPI.

## Como correrlos

Instalar dependencias de desarrollo:

```bash
python -m pip install -r requirements-dev.txt
```

Ejecutar la suite:

```bash
python -m pytest tests -q
```

## TestClient

`TestClient` permite llamar endpoints sin levantar uvicorn:

```python
response = client.get("/tickets/")
```

En estos tests se reemplazan dependencias con `dependency_overrides`:

- `get_current_active_user`: evita generar JWTs para cada caso.
- `get_db`: evita usar PostgreSQL real en tests HTTP livianos.

Los tests de service siguen siendo necesarios porque validan la logica interna
con mas detalle que un test HTTP.
