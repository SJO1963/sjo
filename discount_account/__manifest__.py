# -*- coding: utf-8 -*-

{
    'name': "Discount Received Account For Vendor",

    'summary': """
            Discount Received Account For Vendor
            """,

    'description': """
	Discount Received Account For Vendor
    """,
    'author': "Wajahat Ali",
    'website': "https://axiomworld.net/",
    'category': 'account',
    'price': 0,
    'currency': 'EUR',
    'version': '13.0.0.3.5',
    'license' : 'OPL-1',
    'depends': ['sale_management', 'account_accountant','l10n_us_check_printing'],

    # always loaded
     'data': [
        'views/res_config.xml',
        'views/views.xml',
        'views/report.xml',
        'views/checks_report.xml',

    ],
    # only loaded in demonstration mode
    'demo': [
        'demo/demo.xml',
    ],
}



