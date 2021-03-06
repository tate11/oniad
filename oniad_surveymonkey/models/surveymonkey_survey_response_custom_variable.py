# License AGPL-3.0 or later (https://www.gnu.org/licenses/agpl).

from odoo import fields, models


class SurveymonkeySurveyResponseCustomVariable(models.Model):
    _name = 'surveymonkey.survey.response.custom.variable'
    _description = 'Surveymonkey Survey Response Custom Variable'

    surveymonkey_survey_response_id = fields.Many2one(
        comodel_name='surveymonkey.survey.response',
        string='Surveymonkey Survey Response'
    )
    field = fields.Char(
        string='Survey Id'
    )
    value = fields.Char(
        string='Response Id'
    )
    survey_user_input_line_id = fields.Many2one(
        comodel_name='survey.user_input_line',
        string='Survey User Input Line Id'
    )
