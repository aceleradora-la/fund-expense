# Fundación - Rendición de fondos

Lleva a Odoo el **Anexo I: Solicitud de fondos** sobre la app Gastos (`hr_expense`), con
aprobación por niveles (`hr_expense_tier_validation`) y anticipos
(`hr_expense_advance_clearing`) de OCA.

## Qué agrega

- **Responsable del área** en la hoja de gastos (`department_manager_user_id`): el usuario del
  responsable del departamento del empleado. Queda vacío si quien pide es el propio responsable.
- **Al enviar** una hoja:
  - controla que cada comprobante (salvo el renglón de anticipo) tenga **proveedor con CUIT**;
  - **pide las aprobaciones solo**, sin el paso manual de "Solicitar validación".
- **Al aprobarse el último nivel**, la hoja queda **aprobada sola** y se crean sus asientos. Quien
  aprueba no necesita ser aprobador de Gastos. Se mantienen los controles del núcleo y del
  anticipo.
- **Una sola aprobación en pantalla:** mientras la hoja está en niveles, el formulario oculta
  *Aprobar* y *Rechazar* del núcleo, y no se crea la actividad estándar. El campo *Manager* no se
  muestra: el que firma es el Responsable del área.
- **Al rechazar un nivel** se pide siempre el motivo y la hoja pasa a **Rechazado**, con el motivo
  en el historial. Se conservan las firmas hechas, las aprobaciones que faltaban quedan canceladas
  y el empleado la pasa a borrador para corregirla y reenviarla (ahí se piden las firmas de nuevo).
- **Pagado por la empresa** es el caso por defecto. Al aprobarse el último nivel, en lugar de los
  pagos del núcleo se precarga **un borrador de factura por proveedor**, con renglones, cuentas,
  analítica y adjuntos, vinculado al Anexo:
  - Administración completa el comprobante, confirma (entra al Libro IVA) y paga por el circuito
    habitual. La hoja pasa sola a *Contabilizado* y a *Pagado*.
  - **Si la factura llega después**, el botón *Pagar sin factura* del borrador abre el pago al
    proveedor. Al confirmar la factura, ese pago se concilia solo.
  - Rechazar o volver a borrador la hoja borra los borradores. Si hay una factura confirmada o un
    pago hecho, primero hay que anularlos.
- **Pagado por el empleado** queda para reintegros y anticipos, como en el núcleo.
- **Fondo de pago** (`fund_journal_id`): diario de banco (**fondo fijo**, transferencia), de
  efectivo (**caja chica**) o de **tarjeta de crédito**. Solo lo elige el grupo *Gerencia de
  Administración y Finanzas*, también durante la aprobación. Se propone al registrar el pago.
- **Comprobante** en cada gasto: número, proveedor (siempre visible) y CUIT.
- **Aprobadores:** quien tiene que aprobar una rendición la ve y la aprueba aunque no tenga
  permisos de Gastos.
- **PDF "Anexo I - Solicitud de fondos"** (*Imprimir* en la hoja), con las tres firmas tomadas
  de las aprobaciones y el recuadro de fondos.
- En las **definiciones de aprobación**, el campo *Firma en el Anexo I* indica qué firma
  representa cada nivel.
- Las rendiciones aparecen en la app **Mis aprobaciones**
  ([tier-validation-apps](https://github.com/aceleradora-la/tier-validation-apps)) sin
  configuración extra.

## Configuración después de instalar

1. **Grupo:** asignar *Gastos → Gerencia de Administración y Finanzas* a quienes firman el
   nivel 3. Incluye *Gastos / Administrador*.
2. **Definiciones de aprobación** del modelo *Informe de gastos*:

   | Nivel | Validado por | Dominio | Secuencia | Firma en el Anexo I |
   |---|---|---|---|---|
   | Responsable del área | Campo → **Responsable del área** | `[("department_manager_user_id", "!=", False)]` | **20** | 2. Responsable del área |
   | Gerencia AyF | Grupo → **Gerencia de Administración y Finanzas** | `[]` | **10** | 3. Gerencia Adm. y Fin. |

   Las dos con *Aprobar en secuencia*. **Ojo con el orden:** en `base_tier_validation` 18 firma
   primero la definición de **mayor** secuencia (`request_validation` las recorre en orden
   descendente y numera las revisiones 1, 2, ...).
3. **Departamentos:** cada área con su **responsable**, y ese empleado con su usuario.
4. **Diario de gastos de empleados** (*Ajustes → Gastos*): un diario de compras propio (p. ej.
   "Rendiciones de gastos") **sin "Usa documentos"**. Con la localización argentina, un diario de
   compras con documentos exige tipo y número de comprobante fiscal al contabilizar la hoja, y el
   reintegro al empleado no es una factura: los comprobantes de terceros van en cada renglón.
5. **Facturas de proveedor:** un diario de compras con documentos, distinto del anterior. Las
   facturas del Anexo van a ese diario.
6. **Tarjeta de crédito:** para que el Anexo tilde *Tarjeta*, el diario tiene que ser de tipo
   *Tarjeta de crédito*. Un diario de tipo banco se muestra como *Fondo fijo*.
7. **Con la aprobación de pago de facturas** (`account_move_payment_tier_validation`): sumar
   `("fund_expense_sheet_id", "=", False)` al dominio de su definición, para que las facturas de
   un Anexo no pidan una segunda aprobación.

## Límites

- El control de proveedor con CUIT aplica a todas las hojas de gastos de la compañía.
- Aprobar el último nivel crea los asientos o las facturas: si falta configuración contable
  (diario, cuentas), el error aparece al aprobar.
- Pagar antes de la factura se concilia solo si el pago tiene asiento. Si la factura está
  bloqueada por otra aprobación, se concilia a mano desde sus créditos pendientes.
