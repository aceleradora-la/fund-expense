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
- **Fondo de pago** (`fund_journal_id`): diario de banco (**fondo fijo**, transferencia) o de
  efectivo (**caja chica**). Solo lo elige el grupo *Gerencia de Administración y Finanzas*,
  también durante la aprobación. Se propone al registrar el pago.
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
   | Responsable del área | Campo → **Responsable del área** | `[("department_manager_user_id", "!=", False)]` | 10 | 2. Responsable del área |
   | Gerencia AyF | Grupo → **Gerencia de Administración y Finanzas** | `[]` | 20 | 3. Gerencia Adm. y Fin. |

   Las dos con *Aprobar en secuencia*.
3. **Departamentos:** cada área con su **responsable**, y ese empleado con su usuario.

## Límites

- El control de proveedor con CUIT aplica a todas las hojas de gastos de la compañía.
- Aprobar el último nivel crea los asientos: si falta configuración contable (diario, cuentas),
  el error aparece al aprobar.
