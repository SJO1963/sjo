# # -*- coding: utf-8 -*-
# import pprint
# import logging
# from werkzeug import urls, utils
# from odoo import http, _
# import werkzeug
# from odoo.http import request
# from odoo.addons.payment.controllers.portal import PaymentProcessing
# from odoo.addons.portal.controllers.portal import CustomerPortal
# from odoo.addons.website_sale.controllers.main import WebsiteSale
#
# _logger = logging.getLogger(__name__)
#
# class WebsiteSaleInherit(WebsiteSale):
#
#     @http.route([
#         '''/shop''',
#         '''/shop/page/<int:page>''',
#         '''/shop/category/<model("product.public.category"):category>''',
#         '''/shop/category/<model("product.public.category"):category>/page/<int:page>'''
#     ], type='http', auth="user", website=True, sitemap=WebsiteSale.sitemap_shop)
#     def shop(self, page=0, category=None, search='', ppg=False, **post):
#         print('calling portal user')
#         if request.uid and request.env['res.users'].sudo().search([('id','=',request.uid),('groups_id','not ilike','Portal')]):
#             # only render the template with other operations
#             res = super(WebsiteSaleInherit, self).shop(page=0, category=None, search='', ppg=False, **post)
#             return res
#         else:
#             # values = CustomerPortal._prepare_home_portal_values(self)
#             return request.render("portal.portal_my_home", {})
#
#
#
#     @http.route([
#         '''/order_process'''], type='http', auth="public", website=True, sitemap=WebsiteSale.sitemap_shop)
#     def payment_process(self,**post):
#         order = request.website.sale_get_order()
#
#         order = request.website.sale_get_order()
#         if order:
#             context =  request.context
#             # request.registry['payment.transaction'].form_feedback(order, 'transfer')
#             order.with_context(dict(context, send_email=True)).action_confirm()
#             return werkzeug.utils.redirect('/shop/payment/validate')
#              # return werkzeug.utils.redirect('/payment/process')
#
#     @http.route(['/shop/payment'], type='http', auth="public", website=True, sitemap=False)
#     def payment(self, **post):
#         """ Payment step. This page proposes several payment means based on available
#         payment.acquirer. State at this point :
#
#          - a draft sales order with lines; otherwise, clean context / session and
#            back to the shop
#          - no transaction in context / session, or only a draft one, if the customer
#            did go to a payment.acquirer website but closed the tab without
#            paying / canceling
#         """
#         order = request.website.sale_get_order()
#         redirection = self.checkout_redirection(order)
#         if redirection:
#             return redirection
#
#         render_values = self._get_shop_payment_values(order, **post)
#         render_values['only_services'] = order and order.only_services or False
#
#         if render_values['errors']:
#             render_values.pop('acquirers', '')
#             render_values.pop('tokens', '')
#         if request.env['res.users'].sudo().search([('id', '=', request.uid), ('groups_id', 'not ilike', 'Portal')]):
#             return request.render("website_customization.checkout_for_user", render_values)
#         else:
#             return request.render("website_sale.payment", render_values)
#
#     @http.route('/shop/payment/validate', type='http', auth="public", website=True, sitemap=False)
#     def payment_validate(self, transaction_id=None, sale_order_id=None, **post):
#         """ Method that should be called by the server when receiving an update
#         for a transaction. State at this point :
#
#          - UDPATE ME
#         """
#         if sale_order_id is None:
#             order = request.website.sale_get_order()
#         else:
#             order = request.env['sale.order'].sudo().browse(sale_order_id)
#             assert order.id == request.session.get('sale_last_order_id')
#
#         if transaction_id:
#             tx = request.env['payment.transaction'].sudo().browse(transaction_id)
#             assert tx in order.transaction_ids()
#         elif order:
#             tx = order.get_portal_last_transaction()
#         else:
#             tx = None
#
#         if not order or (order.amount_total and not tx):
#             request.website.sale_reset()
#             return request.redirect('/shop')
#
#         if order and not order.amount_total and not tx:
#             order.with_context(send_email=True).action_confirm()
#             return request.redirect(order.get_portal_url())
#
#         # clean context and session, then redirect to the confirmation page
#         request.website.sale_reset()
#         if tx and tx.state == 'draft':
#             return request.redirect('/shop')
#
#         PaymentProcessing.remove_payment_transaction(tx)
#         return request.redirect('/shop/confirmation')
#
