# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
{
    "name": "Fundación - Conformidad de rendiciones",
    "summary": "Conformidad periódica del Gerente sobre los Anexos I aprobados, "
    "con observaciones por Anexo",
    "version": "18.0.1.2.0",
    "category": "Human Resources/Expenses",
    "website": "https://github.com/aceleradora-la/fund-expense",
    "author": "aceleradora.la",
    "license": "AGPL-3",
    "installable": True,
    "depends": ["fund_expense_report"],
    "data": [
        "security/fund_expense_batch_security.xml",
        "security/ir.model.access.csv",
        "data/ir_sequence_data.xml",
        "data/tier_definition_data.xml",
        "data/ir_cron_data.xml",
        "report/fund_expense_batch_report.xml",
        "wizards/fund_expense_batch_observe_views.xml",
        "views/fund_expense_batch_views.xml",
        "views/hr_expense_sheet_views.xml",
        "views/res_config_settings_views.xml",
    ],
}
