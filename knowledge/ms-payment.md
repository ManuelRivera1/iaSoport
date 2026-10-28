# ms-payment (ejemplo ficticio)

Proyecto: DemoShop
Área: Pagos

Responsabilidad: consultar el estado de pagos de DemoShop.

## Error 504

Significa que la pasarela ficticia no respondió dentro de 10 segundos.
Diagnóstico autorizado de solo lectura: revisar el identificador de correlación
en los logs y consultar el estado de la pasarela.
No reintentar un cobro sin verificar antes su estado e idempotencia.
