# coding: utf-8
from odoo import models, fields, api, _
from werkzeug import urls
import logging
import requests
import pprint
import  json


class ConfigSetting(models.TransientModel):

    _inherit = 'res.config.settings'

    discount_payment_account_id = fields.Many2one('account.account', 'Discount Received Account')

    @api.model
    def get_values(self):
        res = super(ConfigSetting, self).get_values()
        val = self.env['ir.config_parameter'].sudo().get_param('discount_account.discount_payment_account_id')

        res.update(discount_payment_account_id=int(val))

        return res

    def set_values(self):
        super(ConfigSetting, self).set_values()
        param = self.env['ir.config_parameter'].sudo()

        param.set_param('discount_account.discount_payment_account_id', self.discount_payment_account_id.id)
        return param

   




    

