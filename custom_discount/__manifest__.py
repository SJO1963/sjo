# -*- coding: utf-8 -*-
{
    'name': "Vendor Discount",

    'summary': """
         Discount v13.0""",

    'description': """
        
    """,

    'author': "Usman Farzand",
    'website': "https://www.axiomworld.com/",
    'category': 'Sales Management',
    'version': '1.2.0',
    'license': 'LGPL-3',
    'depends': ['base','base_setup','contacts', 'sale', 'purchase', 'sale_management'],

    'data': [
        'views/ks_sale_order.xml',
        'views/ks_account_invoice.xml',
        'views/ks_purchase_order.xml',
        'views/ks_account_invoice_supplier_form.xml',
        'views/ks_account_account.xml',
        'views/res_partner_view.xml',
        'views/ks_report.xml',
        'views/assets.xml',

    ],

       'installable': True,


}
