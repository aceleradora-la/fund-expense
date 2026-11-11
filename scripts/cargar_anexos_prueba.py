# Copyright 2026 aceleradora.la
# License AGPL-3.0 or later (http://www.gnu.org/licenses/agpl.html).
"""Carga Anexos I de prueba para probar la conformidad de rendiciones.

SOLO PARA BASES DE PRUEBA: se niega a correr si la base no está neutralizada
(pre-prod y los builds de prueba de odoo.sh lo están; prod no).

Arma un Anexo por empleado, con empleados de distintas áreas, y los hace
pasar por las aprobaciones como lo harían sus aprobadores reales:

- Cada Anexo tiene de 1 a 3 gastos, con proveedores con CUIT y categorías
  de la base, importes y fechas distintos.
- La mayoría los paga la empresa; uno es un reintegro (pagado por el
  empleado).
- Gerencia AyF les asigna fondos distintos (fondo fijo, caja chica,
  tarjeta) para ver los totales por fondo.
- Firman el responsable del área y Gerencia AyF, con sus usuarios.
- Dos quedan a medio camino, para comprobar que NO entran a la
  conformidad: el último, enviado sin firmas, y otro con dos niveles que
  tiene solo la primera firma (se marcan en el listado).

Los Anexos se llaman «[PRUEBA CONF] ...», para encontrarlos y borrarlos.

Uso, desde la shell de odoo.sh:

    odoo-bin shell --no-http --log-level=warn < cargar_anexos_prueba.py

Por defecto corre en MODO PRUEBA: hace todo, informa y deshace (rollback).

- ANEXOS_GRABAR=1    graba.
- ANEXOS_CANTIDAD=N  cuántos Anexos (por defecto 8, uno por empleado).
- ANEXOS_BORRAR=1    en lugar de cargar, borra los Anexos de prueba que no
  estén en una conformidad ya enviada (con ANEXOS_GRABAR=1 para que quede).
"""

import os
import random
from datetime import date, timedelta

GRABAR = os.environ.get("ANEXOS_GRABAR") == "1"
BORRAR = os.environ.get("ANEXOS_BORRAR") == "1"
CANTIDAD = int(os.environ.get("ANEXOS_CANTIDAD", "8"))
PREFIJO = "[PRUEBA CONF]"
FORZAR = os.environ.get("ANEXOS_FORZAR") == "1"  # solo para bases locales

env = env  # noqa: F821  (lo inyecta `odoo-bin shell`)

neutralized = env["ir.config_parameter"].sudo().get_param("database.is_neutralized")
if not neutralized and not FORZAR:
    raise SystemExit(
        "La base no está neutralizada: este script es solo para bases de prueba."
    )

Sheet = env["hr.expense.sheet"]
company = env.company
rng = random.Random(1111)


def terminar():
    if GRABAR:
        env.cr.commit()
        print("\nGRABADO")
    else:
        env.cr.rollback()
        print("\nMODO PRUEBA: se deshizo todo. Para grabar: ANEXOS_GRABAR=1")


# ---------------------------------------------------------------------------
# Borrado
# ---------------------------------------------------------------------------
if BORRAR:
    sheets = Sheet.search([("name", "=like", f"{PREFIJO}%")])
    borrados, salteados = [], []
    for sheet in sheets:
        nombre = sheet.name
        batch = sheet.fund_batch_id if "fund_batch_id" in sheet._fields else False
        if batch and not batch._fund_batch_is_editable():
            salteados.append(f"{nombre} (en {batch.name}, ya enviada)")
            continue
        try:
            with env.cr.savepoint():
                # Con revisiones abiertas OCA no deja volverla a borrador: en
                # los Anexos de prueba se saltea ese control.
                sheet = sheet.with_context(skip_validation_check=True)
                if sheet.state not in ("draft", "cancel"):
                    sheet.action_reset_expense_sheets()
                sheet.unlink()
            borrados.append(nombre)
        except Exception as error:  # noqa: BLE001
            salteados.append(f"{nombre} ({error})")
    print(f"Borrados: {len(borrados)}")
    for name in salteados:
        print(f"  no se borró: {name}")
    terminar()
    raise SystemExit


# ---------------------------------------------------------------------------
# Datos de la base
# ---------------------------------------------------------------------------
existentes = Sheet.search_count([("name", "=like", f"{PREFIJO}%")])
if existentes:
    raise SystemExit(
        f"Ya hay {existentes} Anexos de prueba. Para empezar de nuevo, primero "
        "borralos con ANEXOS_BORRAR=1 ANEXOS_GRABAR=1."
    )

employees = env["hr.employee"].search(
    [
        ("company_id", "=", company.id),
        ("user_id", "!=", False),
        ("user_id.share", "=", False),
        ("user_id", "!=", env.ref("base.user_admin").id),
        ("department_id", "!=", False),
    ],
    order="department_id, id",
)
# Uno por área primero, para que los totales por área tengan variedad.
by_area, rest = [], []
seen = set()
for employee in employees:
    (rest if employee.department_id in seen else by_area).append(employee)
    seen.add(employee.department_id)
chosen = (by_area + rest)[:CANTIDAD]
if len(chosen) < 3:
    raise SystemExit("Hacen falta al menos 3 empleados con usuario y área.")

advance_product = env.ref(
    "hr_expense_advance_clearing.product_emp_advance", raise_if_not_found=False
)
products = env["product.product"].search(
    [("can_be_expensed", "=", True), ("id", "!=", advance_product.id if advance_product else 0)],
    limit=6,
)
vendors = env["res.partner"].search(
    [("vat", "!=", False), ("supplier_rank", ">", 0), ("is_company", "=", True)],
    limit=12,
)
if not products or not vendors:
    raise SystemExit("Faltan categorías de gasto o proveedores con CUIT.")

afm_group = env.ref("fund_expense_report.group_fund_expense_afm")
afm_user = afm_group.users.filtered(lambda u: not u.share)[:1]
Journal = env["account.journal"]
funds = [
    Journal.search([("company_id", "=", company.id), ("type", "=", kind)], limit=1)
    for kind in ("bank", "cash", "credit")
]
funds = [journal for journal in funds if journal]

print("GRABANDO" if GRABAR else "MODO PRUEBA")
print(f"Empleados: {len(chosen)} · categorías: {len(products)} · proveedores: {len(vendors)}")
print(f"Gerencia AyF: {afm_user.name or '(nadie en el grupo)'}")
print(f"Fondos: {', '.join(funds_j.name for funds_j in funds) or '(ninguno)'}\n")


# ---------------------------------------------------------------------------
# Carga
# ---------------------------------------------------------------------------
def firmar(sheet, niveles=None):
    """Firma con el usuario de cada revisión pendiente, en orden.

    `niveles` limita cuántas firmas se hacen (None: todas). Sin definiciones
    de aprobación, aprueba Gerencia AyF directo.
    """
    admin = env.ref("base.user_admin")
    hechas = 0
    for _ in range(6):
        # Leer de la base: el estado de las revisiones se actualiza al grabar.
        env.flush_all()
        env.invalidate_all()
        if sheet.approval_state != "submit" or (niveles is not None and hechas >= niveles):
            return
        if not sheet.review_ids:
            sheet.with_user(afm_user).action_approve_expense_sheets()
            return
        abiertas = sheet.review_ids.filtered(lambda r: r.status in ("waiting", "pending"))
        # Quien puede firmar ahora (respeta el orden de los niveles). El
        # administrador, solo si no hay otro.
        candidatos = abiertas.reviewer_ids.filtered(lambda u: not u.share).sorted(
            lambda u: u == admin
        )
        firmante = candidatos.filtered(lambda u: sheet.with_user(u).can_review)[:1]
        if not firmante:
            detalle = "; ".join(
                "{}: {} ({})".format(
                    r.name, r.status, ", ".join(r.reviewer_ids.mapped("name")) or "nadie"
                )
                for r in abiertas
            )
            print(f"  {sheet.name}: nadie puede firmar ahora. {detalle}")
            return
        accion = sheet.with_user(firmante).validate_tier()
        # Si el nivel pide comentario, OCA abre el asistente en lugar de firmar.
        if isinstance(accion, dict) and accion.get("res_model") == "comment.wizard":
            env["comment.wizard"].with_user(firmante).with_context(
                **accion["context"]
            ).create({"comment": "Firmado por el script de prueba"}).add_comment()
        hechas += 1


def tiene_dos_niveles(employee):
    manager = employee.department_id.manager_id
    return bool(manager.user_id) and manager != employee


# El último queda enviado sin firmas; el que queda con una sola firma tiene
# que ser uno con dos niveles (si no, esa firma lo aprueba del todo).
sin_firmas = len(chosen) - 1
una_firma = next(
    (i for i in range(sin_firmas - 1, -1, -1) if tiene_dos_niveles(chosen[i])), None
)

resultado = []
today = date.today()
for index, employee in enumerate(chosen):
    reintegro = index == 1
    lines = []
    for line_index in range(rng.randint(1, 3)):
        product = products[(index + line_index) % len(products)]
        vendor = vendors[(index * 3 + line_index) % len(vendors)]
        lines.append(
            (
                0,
                0,
                {
                    "name": f"{product.name} - prueba {index + 1}.{line_index + 1}",
                    "employee_id": employee.id,
                    "product_id": product.id,
                    "total_amount_currency": rng.randrange(3000, 90000, 500),
                    "date": today - timedelta(days=rng.randint(0, 14)),
                    "vendor_id": vendor.id,
                    "receipt_number": f"0001-{rng.randint(1000, 99999):08d}",
                    "payment_mode": "own_account" if reintegro else "company_account",
                    "company_id": company.id,
                },
            )
        )
    sheet = Sheet.create(
        {
            "name": f"{PREFIJO} {employee.name} {index + 1}",
            "employee_id": employee.id,
            "company_id": company.id,
            "expense_line_ids": lines,
        }
    )
    try:
        with env.cr.savepoint():
            sheet.with_user(employee.user_id).action_submit_sheet()
            if funds and afm_user:
                sheet.with_user(afm_user).fund_journal_id = funds[index % len(funds)]
            if index == sin_firmas:
                pass  # enviado, sin firmas
            elif index == una_firma:
                firmar(sheet, niveles=1)  # solo la primera firma
            else:
                firmar(sheet)
        estado = dict(sheet._fields["state"]._description_selection(env))[sheet.state]
    except Exception as error:  # noqa: BLE001
        estado = f"ERROR: {error}"
    firmas = ", ".join(
        f"{r.name}: {r.done_by.name or r.status}" for r in sheet.review_ids.sorted("sequence")
    )
    resultado.append(
        (
            sheet.name,
            employee.department_id.name,
            sheet.total_amount,
            "reintegro" if reintegro else "empresa",
            sheet.fund_journal_id.name or "-",
            estado
            + (" [sin firmas]" if index == sin_firmas else "")
            + (" [una firma]" if index == una_firma else ""),
            firmas or "(sin niveles)",
            sheet.approval_state,
        )
    )

print(f"{'Anexo':<48} {'Área':<28} {'Total':>12}  {'Paga':<9} {'Fondo':<18} Estado / firmas")
for name, area, total, paga, fondo, estado, firmas, _approval in resultado:
    print(f"{name[:48]:<48} {(area or '')[:28]:<28} {total:>12,.2f}  {paga:<9} {fondo[:18]:<18} {estado} · {firmas}")

aprobados = sum(1 for row in resultado if row[7] == "approve")
print(f"\nAprobados (entran a la conformidad): {aprobados} de {len(resultado)}")
print("No tienen que entrar: el «sin firmas» y el de «una firma».")
terminar()
