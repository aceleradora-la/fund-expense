# Fund Expense

Módulos de Odoo para la rendición de fondos de la fundación (Anexo I), sobre la app Gastos.

| | |
|---|---|
| **Módulos** | `fund_expense_report`, `fund_expense_batch_approval` |
| **Licencia** | AGPL-3 |
| **Versiones** | 18.0 |
| **Depende de** | `hr_expense`; [`hr_expense_tier_validation`](https://github.com/OCA/hr-expense/tree/18.0/hr_expense_tier_validation) y [`hr_expense_advance_clearing`](https://github.com/OCA/hr-expense/tree/18.0/hr_expense_advance_clearing) (OCA hr-expense) |

- [`fund_expense_report`](fund_expense_report/README.md): el Anexo I, con sus dos firmas, la
  factura del proveedor y el pago.
- [`fund_expense_batch_approval`](fund_expense_batch_approval/README.md): conformidad posterior
  del Gerente sobre los Anexos aprobados del período, con observaciones por Anexo.
