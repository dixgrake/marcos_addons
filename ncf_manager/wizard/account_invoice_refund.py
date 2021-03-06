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
from openerp import models, fields, api, _, exceptions
from openerp.tools.safe_eval import safe_eval as eval
from openerp.exceptions import UserError
import openerp.addons.decimal_precision as dp
from ..models.tools import is_ncf
import logging
_logger = logging.getLogger(__name__)
try:
    from stdnum.do import ncf
except(ImportError, IOError) as err:
    _logger.debug(err)

class InheritedAccountInvoiceRefund(models.TransientModel):
    _inherit = 'account.invoice.refund'

    refund_ncf = fields.Char(u"NCF nota de crédito", size=19)
    invoice_type = fields.Char(default=lambda s: s._context.get("type", False))

    @api.onchange("refund_ncf")
    def onchange_ncf(self):
        if not ncf.is_valid(self.refund_ncf):
            if not self.refund_ncf[:-8] == 'B04':
                raise exceptions.ValidationError(_(
                    "NCF *{}* NO corresponde con el tipo de documento\n\n"
                    "Verifique lo ha digitado correctamente y que no sea un "
                    "Comprobante Consumidor Final (02)".format(self.refund_ncf)))
            else:
                return

        if self.refund_ncf and len(self.refund_ncf) == 19:
            if not is_ncf(self.refund_ncf, "in_refund"):
                self.refund_ncf = False
                return {
                    'warning': {'title': "Ncf invalido", 'message': "El numero de comprobante fiscal no es valido "
                                                                    "verifique de que no esta digitando un comprobante"
                                                                    "de consumidor final codigo 02 o revise si lo ha "
                                                                    "digitado incorrectamente"}
                }

    # @api.multi
    # def compute_refund(self, mode='refund'):
    #     inv_obj = self.env['account.invoice']
    #     inv_tax_obj = self.env['account.invoice.tax']
    #     inv_line_obj = self.env['account.invoice.line']
    #     context = dict(self._context or {})
    #     xml_id = False
    #
    #     for form in self:
    #         created_inv = []
    #         for inv in inv_obj.browse(context.get('active_ids')):
    #
    #             if inv.state in ['draft', 'proforma2', 'cancel']:
    #                 raise UserError(_('Cannot refund draft/proforma/cancelled invoice.'))
    #             if inv.reconciled and mode in ('cancel', 'modify'):
    #                 raise UserError(_(
    #                     'Cannot refund invoice which is already reconciled, invoice should be unreconciled first. You can only refund this invoice.'))
    #
    #             date = form.date or False
    #             description = form.description or inv.name
    #
    #             refund = inv.refund(form.date_invoice, date, description, inv.journal_id.id)
    #
    #             if mode == "discount":
    #                 product_account_id = refund.journal_id.default_dicount_account_id.id
    #                 if not product_account_id:
    #                     raise exceptions.ValidationError("Para poder aplicar descuentos debe de configurar la Cuenta para descuentos del diario")
    #
    #                 refund.write({"invoice_line_ids": [(5, False, False)]})
    #                 refund.write({"invoice_line_ids": [(0, False, {"name": self.description,
    #                                                                "account_id": product_account_id,
    #                                                                "quantity": 1,
    #                                                                "price_unit": self.amount})]})
    #
    #             refund.compute_taxes()
    #
    #             created_inv.append(refund.id)
    #             if mode in ('cancel', 'modify', "discount"):
    #                 movelines = inv.move_id.line_ids
    #                 to_reconcile_ids = {}
    #                 to_reconcile_lines = self.env['account.move.line']
    #                 for line in movelines:
    #                     if line.account_id.id == inv.account_id.id:
    #                         to_reconcile_lines += line
    #                         to_reconcile_ids.setdefault(line.account_id.id, []).append(line.id)
    #                     if line.reconciled:
    #                         line.remove_move_reconcile()
    #
    #                 refund.move_name = refund.ncf = self.refund_ncf
    #                 refund.signal_workflow('invoice_open')
    #                 for tmpline in refund.move_id.line_ids:
    #                     if tmpline.account_id.id == inv.account_id.id:
    #                         to_reconcile_lines += tmpline
    #                         to_reconcile_lines.reconcile()
    #                 if mode == 'modify':
    #                     invoice = inv.read(
    #                         ['name', 'type', 'number', 'reference',
    #                          'comment', 'date_due', 'partner_id',
    #                          'partner_insite', 'partner_contact',
    #                          'partner_ref', 'payment_term_id', 'account_id',
    #                          'currency_id', 'invoice_line_ids', 'tax_line_ids',
    #                          'journal_id', 'date'])
    #                     invoice = invoice[0]
    #                     del invoice['id']
    #                     invoice_lines = inv_line_obj.browse(invoice['invoice_line_ids'])
    #                     invoice_lines = inv_obj.with_context({"refund_type": "modify"})._refund_cleanup_lines(
    #                         invoice_lines)
    #                     tax_lines = inv_tax_obj.browse(invoice['tax_line_ids'])
    #                     tax_lines = inv_obj.with_context({"refund_type": "modify"})._refund_cleanup_lines(tax_lines)
    #                     invoice.update({
    #                         'type': inv.type,
    #                         'date_invoice': date,
    #                         'state': 'draft',
    #                         'number': False,
    #                         'invoice_line_ids': invoice_lines,
    #                         'tax_line_ids': tax_lines,
    #                         'date': date,
    #                         'name': description,
    #                         'fiscal_position_id': inv.fiscal_position_id.id,
    #                     })
    #                     for field in ('partner_id', 'account_id', 'currency_id',
    #                                   'payment_term_id', 'journal_id'):
    #                         invoice[field] = invoice[field] and invoice[field][0]
    #                     inv_refund = inv_obj.create(invoice)
    #                     if inv_refund.payment_term_id.id:
    #                         inv_refund._onchange_payment_term_date_invoice()
    #                     created_inv.append(inv_refund.id)
    #             xml_id = (inv.type in ['out_refund', 'out_invoice']) and 'action_invoice_tree1' or \
    #                      (inv.type in ['in_refund', 'in_invoice']) and 'action_invoice_tree2'
    #             # Put the reason in the chatter
    #             subject = _("Invoice refund")
    #             body = description
    #             refund.message_post(body=body, subject=subject)
    #     if xml_id:
    #         result = self.env.ref('account.%s' % (xml_id)).read()[0]
    #         invoice_domain = eval(result['domain'])
    #         invoice_domain.append(('id', 'in', created_inv))
    #         result['domain'] = invoice_domain
    #         return result
    #     return True

    @api.multi
    def invoice_refund(self):

        res = super(InheritedAccountInvoiceRefund, self).invoice_refund()
        if self._context.get("type", False) == "in_invoice":
            action_domain = res.get("domain", False)
            if action_domain:
                refund_id = action_domain[1][2][0]
                self.env['account.invoice'].browse(refund_id).write({"move_name": self.refund_ncf, "ncf_required": True})

        return res
