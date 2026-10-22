# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    "name": "Fundación - Rendición de fondos",
    "summary": "Anexo I: solicitud y rendición de fondos sobre Gastos, con aprobación "
    "por niveles, fondo fijo o caja chica y proveedor con CUIT",
    "version": "18.0.1.0.0",
    "category": "Human Resources/Expenses",
    "website": "https://github.com/aceleradora-la/fund-expense",
    "author": "aceleradora.la",
    "license": "AGPL-3",
    "installable": True,
    "depends": [
        "hr_expense",
        "hr_expense_tier_validation",
        "hr_expense_advance_clearing",
    ],
    "data": [
        "security/fund_expense_security.xml",
        "views/hr_expense_views.xml",
        "views/hr_expense_sheet_views.xml",
        "views/tier_definition_views.xml",
        "report/fund_expense_report_templates.xml",
    ],
}
