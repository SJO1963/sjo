
# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl.html).

from odoo import fields, models


class ResPartner(models.Model):
    _inherit = "res.partner"

    ks_global_discount_type = fields.Selection([
                                                ('percent', 'Percentage'),
                                                ('amount', 'Amount')],
                                               string='Discount Type',
                                                default='percent')
    ks_global_discount_rate = fields.Float('Discount')
