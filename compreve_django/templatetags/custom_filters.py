from django import template
import ast
import json

register = template.Library()

@register.filter
def split(value, arg):
    return value.split(arg)

@register.filter
def get_range(value):
    """Generate a range of numbers from 1 to value."""
    try:
        value = int(value)
        return range(1, value + 1)
    except (ValueError, TypeError):
        return range(0)

@register.filter
def safe_eval(value):
    """Safely evaluate a string representation of a list."""
    if not value:
        return []
    try:
        return ast.literal_eval(value)
    except (ValueError, SyntaxError):
        return []

@register.filter
def parse_list(value):
    """Convert a string representation of a list into an actual list."""
    if not value:
        return []
    
    # If value is already a list, return it as is
    if isinstance(value, list):
        return value
        
    try:
        # Handle string representation of Python list
        if isinstance(value, str):
            value = value.replace("'", '"')  # Replace single quotes with double quotes
            return json.loads(value)
        return []
    except json.JSONDecodeError:
        return []
