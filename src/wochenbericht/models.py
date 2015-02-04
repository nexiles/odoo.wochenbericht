# -*- coding: utf-8 -*-

import time
import logging
import datetime

from openerp import tools, api, models, fields, osv, _


class Tagesbericht(models.Model):
    _name = "wochenbericht.tagesbericht"

    date = fields.Date(_("Datum"))

# EOF