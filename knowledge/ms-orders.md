# ms-orders (ejemplo ficticio)

Proyecto: DemoShop
Área: Órdenes

Responsabilidad: consultar órdenes del comercio ficticio DemoShop.
Dependencia: ms-auth valida el token del solicitante.

## Consultar una orden

GET /api/orders/{order_id} devuelve el estado de una orden.
Ejemplo exclusivo del entorno ficticio local:

```sh
curl http://localhost:9001/api/orders/DEMO-001
```

Este comando ilustra documentación; Support AI no lo ejecuta.
