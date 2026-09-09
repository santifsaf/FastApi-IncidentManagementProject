# Tests

La suite esta separada por nivel de responsabilidad:

- `test_*_rules.py`: prueban reglas puras, sin base de datos ni FastAPI.
- `test_*_service.py`: prueban casos de uso, validaciones de negocio, auditoria y commit/rollback.
- `test_*_routes.py`: prueban endpoints con `TestClient`: rutas reales, dependencias, permisos HTTP, status codes y serializacion JSON.
- `integration/`: ejecuta services, SQLAlchemy, constraints y Alembic contra una base PostgreSQL separada.
- `conftest.py`: fixtures compartidas para tests HTTP.

Los tests unitarios de tickets reflejan la misma division que los services:

- `test_ticket_service.py`: creacion y consulta del ticket.
- `test_ticket_assignment_service.py`: agente, team, categoria e historiales asociados.
- `test_ticket_lifecycle_service.py`: cambios de estado y archivado.
- `test_ticket_comment_service.py`: comentarios publicos e internos.
- `test_ticket_dependency_service.py`: dependencias y tickets bloqueantes.
- `ticket_service_fakes.py`: sesiones y queries simuladas compartidas; no contiene tests.

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

Los tests de integracion usan `APP_TEST_DATABASE_URL`. Si no esta definida,
derivan el nombre agregando `_test` a la base de desarrollo. Como proteccion,
rechazan la URL de desarrollo y cualquier base cuyo nombre no termine en
`_test`. La base debe existir antes de ejecutar la suite.

Para crearla con las mismas credenciales de PostgreSQL configuradas en `.env`:

```bash
python -m app.scripts.create_test_database
```

Si necesitás validar todas las migraciones nuevamente desde una base vacía:

```bash
python -m app.scripts.create_test_database --recreate
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
