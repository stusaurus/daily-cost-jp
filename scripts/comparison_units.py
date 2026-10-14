"""Units with explicit title evidence; never infer ply, mass/volume or dosage."""
import math
import re
from sale_quantity import normalize, ambiguous_quantity

LABELS = {'box':'1箱','roll':'1ロール','pack':'1パック','sheet':'1枚','piece':'1本','100g':'100g','100ml':'100ml','1L':'1L'}


def comparison_unit(category_id, item):
    name = normalize(item.get('name', ''))
    try:
        value = float(item['unit_price'])
    except (KeyError, ValueError, TypeError):
        return None
    if not math.isfinite(value) or value <= 0 or ambiguous_quantity(name):
        return None
    metric = item.get('metric')
    if category_id == 'tissue':
        groups = {int(n) for n in re.findall(r'(\d+)\s*組', name)}
        if metric != 'box' or len(groups) != 1 or min(groups) <= 0:
            return None
        return '100組', value / min(groups) * 100
    if category_id == 'toilet-paper':
        lengths = {float(n) for n in re.findall(r'(?<![\d.])(\d+(?:\.\d+)?)\s*m(?![a-z])', name, re.I)}
        ply = [p for p in ('シングル', 'ダブル') if p in name]
        if metric != 'roll' or len(lengths) != 1 or min(lengths) <= 0 or len(ply) != 1:
            return None
        return ply[0] + '10m', value / min(lengths) * 10
    return (LABELS[metric], value) if metric in LABELS else None


def quantity_label(item):
    try:
        count = float(item['price']) / float(item['unit_price'])
    except (KeyError, ValueError, TypeError, ZeroDivisionError):
        return '数量は商品ページで確認'
    metric = item.get('metric')
    if metric in ('box','roll','pack','sheet','piece'):
        if abs(count-round(count)) > .001:
            return '数量は商品ページで確認'
        return f'{round(count):,}' + {'box':'箱','roll':'ロール','pack':'パック','sheet':'枚','piece':'本'}[metric]
    if metric == '100g': return f'{count*100:,.0f}g'
    if metric == '100ml': return f'{count*100:,.0f}ml'
    if metric == '1L': return f'{count:,.2f}L'
    return '数量は商品ページで確認'
