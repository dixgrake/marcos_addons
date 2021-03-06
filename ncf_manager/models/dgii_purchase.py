# -*- coding: utf-8 -*-
########################################################################################################################
#  Copyright (c) 2015 - Marcos Organizador de Negocios SRL. (<https://marcos.do/>) 
#  Write by Eneldo Serrata (eneldo@marcos.do)
#  See LICENSE file for full copyright and licensing details.
#
# Odoo Proprietary License v1.0
#
# This software and associated files (the "Software") may only be used
# (nobody can redistribute (or sell) your module once they have bought it, unless you gave them your consent)
# if you have purchased a valid license
# from the authors, typically via Odoo Apps, or if you have received a written
# agreement from the authors of the Software (see the COPYRIGHT file).
#
# You may develop Odoo modules that use the Software as a library (typically
# by depending on it, importing it and using its resources), but without copying
# any source code or material from the Software. You may distribute those
# modules under the license of your choice, provided that this license is
# compatible with the terms of the Odoo Proprietary License (For example:
# LGPL, MIT, or proprietary licenses similar to this one).
#
# It is forbidden to publish, distribute, sublicense, or sell copies of the Software
# or modified copies of the Software.
#
# The above copyright notice and this permission notice must be included in all
# copies or substantial portions of the Software.
#
# THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
# IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
# FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
# IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM,
# DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE,
# ARISING FROM, OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER
# DEALINGS IN THE SOFTWARE.
########################################################################################################################
from openerp import models, fields, api, exceptions
import calendar
import base64
from tools import is_identification, is_ncf
import time
import re


class ResCompany(models.Model):
    _inherit = "res.company"

    payment_tax_on_606 = fields.Boolean("Reportar retenciones del 606 en la fecha del pago")


class DgiiPurchaseReport(models.Model):
    _name = "dgii.purchase.report"

    company_id = fields.Many2one('res.company', string='Company', required=True,
                                 default=lambda self: self.env['res.company']._company_default_get(
                                     'dgii.purchase.report'))
    name = fields.Char()
    year = fields.Integer(u"Año", size=4, default=lambda s: int(time.strftime("%Y")))
    month = fields.Integer("Mes", size=2, default=lambda s: int(time.strftime("%m")))
    CANTIDAD_REGISTRO = fields.Integer("Cantidad de registros")
    ITBIS_RETENIDO = fields.Float("TOTAL ITBIS RETENIDO")
    ITBIS_TOTAL = fields.Float("TOTAL ITBIS PAGADO")
    TOTAL_MONTO_FACTURADO = fields.Float("TOTAL FACTURADO")
    RETENCION_RENTA = fields.Float("TOTAL RETENCION RENTA")
    report_lines = fields.One2many("dgii.purchase.report.line", "purchase_report_id")
    txt = fields.Binary("Reporte TXT", readonly=True)
    txt_filename = fields.Char("Nombre del archivo", readonly=True)
    state = fields.Selection([('draft', 'Nuevo'), ('done', 'Generado')], default="draft")

    @api.model
    def create(self, vals):
        vals.update({"name": "{}/{}".format(vals["month"], vals["year"])})
        self = super(DgiiPurchaseReport, self).create(vals)
        self.create_report()
        return self

    def get_date_range(self):
        if self.month > 12 or self.month < 1:
            self.month = False
            raise exceptions.ValidationError("El mes es invalido!")
        last_day = calendar.monthrange(self.year, self.month)[1]
        return ("{}-{}-{}".format(str(self.year), str(self.month).zfill(2), "01"),
                "{}-{}-{}".format(str(self.year), str(self.month).zfill(2), str(last_day).zfill(2)))

    def create_report_lines(self, invoices, tax_account):
        if self._context.get("recreate", False):
            self.report_lines.unlink()
            self.txt = False

        account_tax_ids = tax_account.keys()

        CANTIDAD_REGISTRO = len(invoices)
        ITBIS_RETENIDO = 0
        ITBIS_TOTAL = 0
        TOTAL_MONTO_FACTURADO = 0  # sum([inv.amount_untaxed*inv.rate for inv in invoices])
        RETENCION_RENTA = 0

        lines = []
        line_number = 0
        for inv in invoices:
            line_number += 1
            LINE = line_number

            LINE_ITBIS_TOTAL = 0
            LINE_ITBIS_RETENIDO = 0
            LINE_RETENCION_RENTA = 0
            LINE_TAX_COST = 0
            CURRENCY_RATE = 1

            move_lines = [move_line for move_line in inv.move_id.line_ids if move_line.account_id.id in account_tax_ids]
            cxp_move = [move_line for move_line in inv.move_id.line_ids if move_line.account_id.id == inv.account_id.id]

            if cxp_move:
                if cxp_move[0].amount_currency:
                    CURRENCY_RATE = abs(cxp_move[0].credit + cxp_move[0].debit) / abs(cxp_move[0].amount_currency)

            for move_line in move_lines:

                amount = move_line.debit if move_line.debit > 0 else move_line.credit

                # if move_line.amount_currency:
                #     CURRENCY_RATE = abs(amount)/abs(move_line.amount_currency)

                if tax_account[move_line.account_id.id] == "itbis":
                    if inv.type == "in_invoice":
                        ITBIS_TOTAL += amount
                    else:
                        ITBIS_TOTAL -= amount
                    LINE_ITBIS_TOTAL += amount
                elif tax_account[move_line.account_id.id] == "ritbis" and inv.state == 'paid':
                    if int(max(inv.payment_move_line_ids).date.split("-")[1]) == self.month:
                        ITBIS_RETENIDO += abs(amount)
                        LINE_ITBIS_RETENIDO += amount
                elif tax_account[move_line.account_id.id] == "isr":
                    RETENCION_RENTA += amount
                    LINE_RETENCION_RENTA += amount
                elif tax_account[move_line.account_id.id] == "cost" and move_line.tax_line_id:
                    LINE_TAX_COST += amount
                    if inv.type == "in_invoice":
                        TOTAL_MONTO_FACTURADO += amount
                    else:
                        TOTAL_MONTO_FACTURADO -= amount

            if inv.type == "in_invoice":
                TOTAL_MONTO_FACTURADO += inv.amount_untaxed * CURRENCY_RATE
            else:
                TOTAL_MONTO_FACTURADO -= inv.amount_untaxed * CURRENCY_RATE

            if not inv.partner_id.vat:
                raise exceptions.UserError(
                    u"El número de RNC/Cédula del proveedor {} no es valido para el NCF {}".format(inv.partner_id.name,
                                                                                                   inv.number))

            RNC_CEDULA = re.sub("[^0-9]", "", inv.partner_id.vat.strip())
            TIPO_IDENTIFICACION = "1" if len(RNC_CEDULA.strip()) == 9 else "2"
            TIPO_BIENES_SERVICIOS_COMPRADOS = inv.fiscal_position_id.supplier_fiscal_type

            if not TIPO_BIENES_SERVICIOS_COMPRADOS:
                raise exceptions.UserError(
                    u"Debe de definir el tipo de gasto para la posición fiscal {}! en la factura {}".format(
                        inv.fiscal_position_id.name, inv.number))

            if not is_ncf(inv.number, inv.type):
                raise exceptions.UserError(u"El número de NCF {} no es valido!".format(inv.number))

            NUMERO_COMPROBANTE_MODIFICADO = "".rjust(19)
            affected_nvoice_id = False

            if inv.type == "in_invoice":
                NUMERO_COMPROBANTE_FISCAL = inv.number
            elif inv.type == "in_refund":
                affected_nvoice_id = self.env["account.invoice"].search([('number', '=', inv.origin),('partner_id','=',inv.partner_id.id)])
                if not len(affected_nvoice_id) == 1 and affected_nvoice_id:
                    raise exceptions.ValidationError(u"Una misma nota de crédito no puede afectar dos facturas {}".format([rec.number for rec in affected_nvoice_id]))
                elif not affected_nvoice_id:
                    raise exceptions.ValidationError(u"La nota de crédito {} no tiene el NCF que afecta en el campo origen").format(affected_nvoice_id.number)
                else:
                    affected_nvoice_id = affected_nvoice_id.id

                NUMERO_COMPROBANTE_FISCAL = inv.number
                NUMERO_COMPROBANTE_MODIFICADO = inv.origin

            FECHA_COMPROBANTE = inv.date_invoice
            if inv.payment_move_line_ids:
                FECHA_PAGO = max(inv.payment_move_line_ids).date
            else:
                FECHA_PAGO = False
            lines.append((0, False, {"LINE": LINE,
                                     "invoice_id": inv.id,
                                     "RNC_CEDULA": RNC_CEDULA,
                                     "TIPO_IDENTIFICACION": TIPO_IDENTIFICACION,
                                     "TIPO_BIENES_SERVICIOS_COMPRADOS": TIPO_BIENES_SERVICIOS_COMPRADOS,
                                     "NUMERO_COMPROBANTE_FISCAL": NUMERO_COMPROBANTE_FISCAL,
                                     "NUMERO_COMPROBANTE_MODIFICADO": NUMERO_COMPROBANTE_MODIFICADO,
                                     "affected_nvoice_id": affected_nvoice_id,
                                     "FECHA_COMPROBANTE": FECHA_COMPROBANTE,
                                     "FECHA_PAGO": FECHA_PAGO,
                                     "ITBIS_FACTURADO": LINE_ITBIS_TOTAL,
                                     "ITBIS_RETENIDO": abs(LINE_ITBIS_RETENIDO),
                                     "MONTO_FACTURADO": (inv.amount_untaxed + LINE_TAX_COST) * CURRENCY_RATE,
                                     "RETENCION_RENTA": LINE_RETENCION_RENTA
                                     }))

        self.write({"report_lines": lines,
                    "CANTIDAD_REGISTRO": CANTIDAD_REGISTRO,
                    "ITBIS_RETENIDO": abs(ITBIS_RETENIDO),
                    "ITBIS_TOTAL": ITBIS_TOTAL,
                    "TOTAL_MONTO_FACTURADO": TOTAL_MONTO_FACTURADO,
                    "RETENCION_RENTA": RETENCION_RENTA,
                    "state": "done"})

    def generate_txt(self):

        if not self.company_id.vat:
            raise exceptions.ValidationError(
                u"Para poder generar el 606 primero debe especificar el RNC/Cédula de la compañia.")

        company_fiscal_identificacion = re.sub("[^0-9]", "", self.company_id.vat)

        if not company_fiscal_identificacion or not is_identification(company_fiscal_identificacion):
            raise exceptions.ValidationError("Debe de configurar el RNC de su empresa!")

        path = '/tmp/606{}.txt'.format(company_fiscal_identificacion)
        file = open(path, 'w')
        lines = []

        header = "606"
        header += company_fiscal_identificacion.rjust(11)
        header += str(self.year)
        header += str(self.month).zfill(2)
        header += "{:.2f}".format(self.CANTIDAD_REGISTRO).zfill(12)
        header += "{:.2f}".format(self.TOTAL_MONTO_FACTURADO).zfill(16)
        header += "{:.2f}".format(self.RETENCION_RENTA).zfill(12)
        lines.append(header)

        for line in self.report_lines:
            ln = ""
            ln += line.RNC_CEDULA.rjust(11)
            ln += line.TIPO_IDENTIFICACION
            ln += line.TIPO_BIENES_SERVICIOS_COMPRADOS
            ln += line.NUMERO_COMPROBANTE_FISCAL
            ln += line.NUMERO_COMPROBANTE_MODIFICADO
            ln += line.FECHA_COMPROBANTE.replace("-", "")
            ln += line.FECHA_PAGO.replace("-", "") if line.FECHA_PAGO else "".rjust(8)
            ln += "{:.2f}".format(line.ITBIS_FACTURADO).zfill(12)
            ln += "{:.2f}".format(abs(line.ITBIS_RETENIDO)).zfill(12)
            ln += "{:.2f}".format(line.MONTO_FACTURADO).zfill(12)
            ln += "{:.2f}".format(line.RETENCION_RENTA).zfill(12)
            lines.append(ln)

        for line in lines:
            file.write(line + "\n")

        file.close()
        file = open(path, 'rb')
        report = base64.b64encode(file.read())
        report_name = 'DGII_606_{}_{}{}.TXT'.format(company_fiscal_identificacion, str(self.year),
                                                    str(self.month).zfill(2))
        self.write({'txt': report, 'txt_filename': report_name})

    @api.multi
    def create_report(self):
        start_date, end_date = self.get_date_range()

        taxes = self.env["account.tax"].search(
            [('company_id', '=', self.company_id.id), ('type_tax_use', '=', 'purchase')])
        tax_account = {}
        for tax in taxes:
            if not tax_account.get("tax_id", False) == tax.account_id.id:
                if tax.purchase_tax_type != 'none':
                    tax_account.update({tax.account_id.id: False})

            if tax.purchase_tax_type != 'none':
                tax_account[tax.account_id.id] = tax.purchase_tax_type

        invoices = self.env["account.invoice"].search([('date_invoice', '>=', start_date),
                                                       ('date_invoice', '<=', end_date),
                                                       ('state', 'in', ('open', 'paid')),
                                                       ('journal_id.purchase_type', 'in',
                                                        ('normal', 'minor', 'informal')),
                                                       ('type', 'in', ('in_invoice', 'in_refund'))])

        if self.env.user.company_id.payment_tax_on_606:
            # todo fix 606 when have to place retention paymeny day
            paid_in_period_with_retention_invoices = self.env["account.invoice"].search(
                [('payment_move_line_ids.date', '>=', start_date),
                 ('payment_move_line_ids.date', '<=', end_date),
                 ('journal_id.purchase_type', 'in', ('normal', 'minor', 'informal')),
                 ('reconciled', '=', True),
                 ('type', 'in', ('in_invoice', 'in_refund'))])

            for inv_paid in paid_in_period_with_retention_invoices:
                account_ids = [move_id.account_id.id for move_id in inv_paid.move_id.line_ids]
                for account in account_ids:
                    if tax_account.get(account, "") in ('ritbis', 'isr'):
                        invoices += inv_paid
                        continue

        invoice_ids = [rec.id for rec in invoices]
        invoice_ids = list(set(invoice_ids))
        invoices = self.env["account.invoice"].browse(invoice_ids)
        self.create_report_lines(invoices, tax_account)
        self.generate_txt()
        return True


class DgiiPurchaseReportline(models.Model):
    _name = "dgii.purchase.report.line"

    purchase_report_id = fields.Many2one("dgii.purchase.report")
    LINE = fields.Integer("Linea")
    invoice_id = fields.Many2one("account.invoice", "NCF")
    inv_partner = fields.Many2one("res.partner", related="invoice_id.partner_id", string="Relacionado")
    RNC_CEDULA = fields.Char(u"RNC", size=11)
    TIPO_IDENTIFICACION = fields.Char("Tipo ID", size=1)
    TIPO_BIENES_SERVICIOS_COMPRADOS = fields.Char("Tipo", size=2)
    NUMERO_COMPROBANTE_FISCAL = fields.Char("NCF STRING", size=19)
    NUMERO_COMPROBANTE_MODIFICADO = fields.Char("Afecta", size=19)
    affected_nvoice_id = fields.Many2one("account.invoice", "Afecta")
    FECHA_COMPROBANTE = fields.Date("Fecha")
    FECHA_PAGO = fields.Date("Pagado")
    ITBIS_FACTURADO = fields.Float("ITBIS Facturado")
    ITBIS_RETENIDO = fields.Float("ITBIS Retenido")
    MONTO_FACTURADO = fields.Float("Monto Facturado")
    RETENCION_RENTA = fields.Float(u"Retención Renta")
