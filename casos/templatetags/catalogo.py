from django import template

from casos.utils import texto_catalogo


register = template.Library()
register.filter("catalogo", texto_catalogo)
